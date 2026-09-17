"""Preflight and immutable protocol generation for the SCUT championship."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any

from sklearn.model_selection import GroupKFold

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.championship_backbones import CANDIDATES
from scripts.championship_backbones import ScutModel, TechnicalExclusion, build_adapter
from scripts.championship_common import atomic_json_write, configure_ml_caches, load_train_records, write_observed_validation_status
from scripts.tail_aware_encoder import dangerous_action_target, pack_turns

FROZEN = {"semantic_pos_weight_cap": 4.0, "kind_weight_clip": [0.5, 3.0], "action_pos_weight_cap": 4.0,
          "loss_weights": {"semantic": 1.0, "kind": .35, "action": .50}, "head_lr": 3e-4,
          "encoder_lr": {"top_2": 7e-6, "top_4": 4e-6}, "weight_decay": .01, "gradient_clip": 1.0,
          "effective_batch_size": 16, "micro_batch_probe_order": [8, 4, 2, 1], "warmup_epochs": 1,
          "fine_tuning_epochs": 4, "final_warmup_epochs": 1, "final_fine_tuning_epochs": 4,
          "action_threshold_grid": [.2, .3, .4, .5, .6, .7, .8], "semantic_threshold_grid": [.35, .45, .5, .6, .7],
          "mixed_precision": "bf16_if_supported_and_finite_else_fp16_gradscaler_else_fail"}

def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()

def compute_fold_assignments(train: list[dict[str, Any]]) -> dict[str, int]:
    groups = [row["base_scenario_id"] for row in train]
    # group-only split is intentional; labels never influence assignments.
    folds = {}
    for fold, (_, validation_indices) in enumerate(GroupKFold(n_splits=3).split(train, groups=groups)):
        for index in validation_indices: folds[str(train[index]["id"])] = fold
    if len(folds) != len(train): raise RuntimeError("incomplete grouped fold assignment")
    return folds

def audit_remote_code(files: list[Path]) -> list[dict[str, Any]]:
    needles = ("subprocess", "os.system", "socket", "requests", "urllib", "shutil.rmtree", "unlink(")
    return [{"file": str(file), "findings": [needle for needle in needles if needle in file.read_text(encoding="utf-8", errors="replace")]} for file in files]

def resolve_candidates(*, real: bool = False) -> dict[str, dict[str, Any]]:
    result = {}
    if not real:
        return {key: {"model_id": value["model_id"], "revision": "UNRESOLVED_DRY_RUN"} for key, value in CANDIDATES.items()}
    from huggingface_hub import HfApi
    api = HfApi()
    for key, value in CANDIDATES.items():
        info = api.model_info(value["model_id"])
        if not info.sha: raise RuntimeError(f"Hub did not return immutable SHA for {key}")
        result[key] = {"model_id": value["model_id"], "revision": info.sha, "trust_remote_code": value["trust_remote_code"]}
    return result

def _remote_code_audit(candidate: str, resolved: dict[str, Any]) -> list[dict[str, Any]]:
    if not resolved["trust_remote_code"]:
        return []
    from huggingface_hub import snapshot_download
    snapshot = Path(snapshot_download(resolved["model_id"], revision=resolved["revision"], cache_dir=str(ROOT / ".local" / "ml-cache" / "hf-cache"), allow_patterns=["*.py"]))
    files = sorted(snapshot.rglob("*.py"))
    return [{"file": str(path.relative_to(snapshot)), "sha256": sha256_file(path), "findings": audit_remote_code([path])[0]["findings"]} for path in files]


def run_candidate_smoke(candidate: str, resolved: dict[str, Any], train: list[dict[str, Any]], labels: list[str]) -> dict[str, Any]:
    """Actual one-candidate CUDA forward/backward/step and memory probe."""
    import torch
    if not torch.cuda.is_available(): raise RuntimeError("CUDA mandatory; refusing CPU fallback")
    adapter = build_adapter(candidate, resolved["revision"], cache_dir=str(ROOT / ".local" / "ml-cache" / "hf-cache"))
    import transformers
    try: embedding=adapter.encoder.get_input_embeddings()
    except (NotImplementedError, AttributeError): embedding=None
    diagnostic={"model_id":resolved["model_id"],"revision":resolved["revision"],"transformers_version":transformers.__version__,"torch_version":torch.__version__,"tokenizer_class":type(adapter.tokenizer).__name__,"model_class":type(adapter.encoder).__name__,"config_vocab_size":getattr(adapter.encoder.config,"vocab_size",None),"tokenizer_length":len(adapter.tokenizer),"embedding_table_size":getattr(embedding,"num_embeddings",None),"special_token_ids":dict(getattr(adapter.tokenizer,"special_tokens_map_extended",{}))}
    malicious = [("CALLER", "x " * 1000), ("CALLER", "read the OTP")]
    text = pack_turns(malicious, adapter.tokenizer, 384, "query: " if candidate == "e5_base" else "")
    if "read the OTP" not in text or "[CONTEXT_OMITTED]" not in text: raise TechnicalExclusion("tail-aware final-turn packing regression")
    model = ScutModel(adapter, len(labels)).cuda(); proof = adapter.configure_trainable_layers(2)
    kinds = {"dangerous": 0, "protective": 1, "legitimate": 2}
    probes=[]
    precision = "bf16" if torch.cuda.is_bf16_supported() else "fp16"
    for size in FROZEN["micro_batch_probe_order"]:
        selected = train[:size]
        try:
            encoded = adapter.tokenizer([pack_turns(row["turns"], adapter.tokenizer, 384, "query: " if candidate == "e5_base" else "") for row in selected], padding=True, truncation=True, max_length=384, return_tensors="pt")
            diagnostic.update({"input_ids_min":int(encoded["input_ids"].min()),"input_ids_max":int(encoded["input_ids"].max()),"sequence_length":int(encoded["input_ids"].shape[1]),"max_position_embeddings":getattr(adapter.encoder.config,"max_position_embeddings",None),"token_type_ids_present":"token_type_ids" in encoded,"attention_mask_shape":list(encoded["attention_mask"].shape),"attention_mask_min":int(encoded["attention_mask"].min()),"attention_mask_max":int(encoded["attention_mask"].max()),"device":"cuda","dtype":"input_ids:int64"})
            batch = {key: value.cuda() for key, value in encoded.items()}; y = torch.tensor([[label in row["labels"] for label in labels] for row in selected], device="cuda", dtype=torch.float32)
            k=torch.tensor([kinds[row["kind"]] for row in selected],device="cuda"); a=torch.tensor([dangerous_action_target(row) for row in selected],device="cuda",dtype=torch.float32)
            torch.cuda.empty_cache(); torch.cuda.reset_peak_memory_stats(); opt=torch.optim.AdamW([p for p in model.parameters() if p.requires_grad],lr=1e-5)
            scaler = torch.amp.GradScaler("cuda", enabled=precision == "fp16")
            opt.zero_grad()
            with torch.autocast("cuda", dtype=torch.bfloat16 if precision == "bf16" else torch.float16):
                s,kind,action=model(batch); loss=torch.nn.functional.binary_cross_entropy_with_logits(s,y)+.35*torch.nn.functional.cross_entropy(kind,k)+.5*torch.nn.functional.binary_cross_entropy_with_logits(action.squeeze(-1),a)
            if not torch.isfinite(loss): raise TechnicalExclusion("non-finite smoke loss")
            scaler.scale(loss).backward(); scaler.unscale_(opt)
            gradient=float(sum(p.grad.abs().sum().item() for p in adapter.encoder.parameters() if p.requires_grad and p.grad is not None))
            if not torch.isfinite(torch.tensor(gradient)) or gradient <= 0: raise TechnicalExclusion("encoder gradient was zero or non-finite")
            scaler.step(opt); scaler.update()
            probes.append({"micro_batch":size,"status":"PASSED","peak_vram_bytes":int(torch.cuda.max_memory_allocated()),"encoder_gradient_l1":gradient,"finite_loss":True})
        except Exception as exc:
            probes.append({"micro_batch":size,"status":"FAILED","reason":f"{type(exc).__name__}: {exc}"})
        finally:
            for name in ("batch", "y", "k", "a", "opt"):
                if name in locals(): del locals()[name]
            torch.cuda.empty_cache()
    successful=[probe for probe in probes if probe["status"] == "PASSED"]
    if not successful: raise TechnicalExclusion(f"all memory probes failed: {probes}")
    selected_probe=successful[0]
    evidence={"status":"PASSED","revision":resolved["revision"],"model_id":resolved["model_id"],"tokenizer_revision":resolved["revision"],"tokenizer_config_sha256":sha256_file(Path(adapter.tokenizer.init_kwargs.get('tokenizer_file'))) if adapter.tokenizer.init_kwargs.get('tokenizer_file') and Path(adapter.tokenizer.init_kwargs['tokenizer_file']).is_file() else None,"trainable_blocks":proof.block_ids,"architecture_path":adapter.architecture_path,"encoder_gradient_l1":selected_probe["encoder_gradient_l1"],"peak_vram_bytes":selected_probe["peak_vram_bytes"],"micro_batch":selected_probe["micro_batch"],"gradient_accumulation":16//selected_probe["micro_batch"],"precision":precision,"memory_probes":probes,"remote_code":_remote_code_audit(candidate,resolved),"diagnostic":diagnostic}
    del model, adapter; torch.cuda.empty_cache()
    return evidence

def build_protocol(candidates: dict[str, dict[str, Any]], lineage: dict[str, Any], fold_assignments: dict[str, int] | None = None, deviations: dict[str, Any] | None = None) -> dict[str, Any]:
    excluded = set((deviations or {}).get("excluded", ()))
    fits = []
    for candidate in CANDIDATES:
        if candidate in excluded: continue
        for depth in (2, 4):
            for fold in range(3): fits.append({"fit_id": f"{candidate}-top_{depth}-fold_{fold}-seed_17", "candidate": candidate, "depth": depth, "fold": fold, "seed": 17})
    expected = (len(CANDIDATES) - len(excluded)) * 6
    if len(fits) != expected: raise RuntimeError("phase-1 matrix was shortened unexpectedly")
    return {"schema": 1, "candidates": candidates, "lineage": lineage, "fold_assignments": fold_assignments or {}, "constants": FROZEN,
            "phase1_fits": fits, "phase1_expected_fit_count": expected, "seeds": [17, 29, 43],
            "seed_selection": "rank all seeds by safety-first tuple; choose middle; exact ties ascending seed", "deviations": deviations or {}}

def write_protocol(directory: Path, protocol: dict[str, Any]) -> tuple[Path, str]:
    directory.mkdir(parents=True, exist_ok=True); path = directory / "championship_protocol.json"
    atomic_json_write(path, protocol); digest = sha256_file(path)
    (directory / "championship_protocol.sha256").write_text(digest + "\n", encoding="ascii")
    return path, digest

def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--dry-run", action="store_true"); parser.add_argument("--real", action="store_true"); parser.add_argument("--candidate", choices=tuple(CANDIDATES)); parser.add_argument("--freeze-protocol", action="store_true"); parser.add_argument("--check-integrity", action="store_true"); parser.add_argument("--check-cache-paths", action="store_true")
    args = parser.parse_args(); root = ROOT; cache_paths = configure_ml_caches(ROOT / ".local" / "ml-cache")
    train, _labels, lineage = load_train_records(root)
    if args.check_integrity or args.check_cache_paths:
        import torch
        if not torch.cuda.is_available(): raise RuntimeError("CUDA mandatory; refusing CPU fallback")
        device = torch.cuda.get_device_name(0)
        if "RTX 5070" not in device.upper(): raise RuntimeError(f"expected RTX 5070, got {device}")
        print(json.dumps({"integrity": "ok", "cache_paths": {key: str(value) for key, value in cache_paths.items()}, "cuda_device": device}))
        return
    report = root / "reports" / "scut_brain_championship_v2_pc5070"; report.mkdir(parents=True, exist_ok=True); write_observed_validation_status(report)
    candidates = resolve_candidates(real=args.real)
    deviations: dict[str, Any] = {"excluded": [], "records": {}}
    if args.real:
        labels=sorted({label for row in train for label in row["labels"]}); evidence={}
        # Keep a CUDA fault in one remote-code candidate from poisoning the
        # diagnostic evidence for the other candidate still under test.
        for candidate in ((args.candidate,) if args.candidate else ("e5_base", "xlmr_base", "nomic_v2_moe", "gte_mlm_base")):
            resolved = candidates[candidate]
            try: evidence[candidate]=run_candidate_smoke(candidate,resolved,train,labels)
            except Exception as exc: evidence[candidate]={"status":"TECHNICALLY_EXCLUDED","reason":f"{type(exc).__name__}: {exc}"}
        for candidate, item in evidence.items():
            if item["status"] != "PASSED":
                deviations["excluded"].append(candidate); deviations["records"][candidate] = item
        atomic_json_write(report/"preflight.json", {"candidates": evidence, "cache_paths": {key: str(value) for key, value in cache_paths.items()}, "cuda_device": __import__('torch').cuda.get_device_name(0), "completed_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
        candidates = {candidate: resolved for candidate, resolved in candidates.items() if candidate not in deviations["excluded"]}
        if not candidates: raise RuntimeError("all championship candidates were technically excluded")
        print(json.dumps({"real_preflight": "completed", "passed": sorted(candidates), "excluded": deviations["excluded"]}))
    elif args.freeze_protocol:
        preflight_path = report / "preflight.json"
        if not preflight_path.is_file(): raise RuntimeError("real preflight evidence missing")
        evidence = json.loads(preflight_path.read_text(encoding="utf-8"))["candidates"]
        candidates = {candidate: {"model_id": CANDIDATES[candidate]["model_id"], "revision": item["revision"], "trust_remote_code": CANDIDATES[candidate]["trust_remote_code"], "micro_batch": item["micro_batch"]} for candidate, item in evidence.items() if item["status"] == "PASSED"}
        deviations = {"excluded": sorted(candidate for candidate, item in evidence.items() if item["status"] != "PASSED"), "records": {candidate: item for candidate, item in evidence.items() if item["status"] != "PASSED"}}
        if not candidates: raise RuntimeError("no preflight-passed candidate available for protocol")
    protocol = build_protocol(candidates, lineage, compute_fold_assignments(train), deviations)
    if args.freeze_protocol: print(write_protocol(report, protocol)[1])
    elif not args.real: print(json.dumps({"dry_run": True, "fit_count": len(protocol["phase1_fits"])}))
if __name__ == "__main__": main()
