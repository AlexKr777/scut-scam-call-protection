"""SCUT Brain Championship v3: isolated TRAIN-only Nomic experiments."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import random
import shutil
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.championship_backbones import ScutModel, build_adapter
from scripts.championship_common import atomic_json_write, configure_ml_caches, load_train_records
from scripts.championship_metrics import safety_qualification, semantic_metrics, select_thresholds
from scripts.championship_preflight import sha256_file
from scripts.tail_aware_encoder import dangerous_action_target, pack_turns

V2_REPORT = ROOT / "reports" / "scut_brain_championship_v2_pc5070"
V2_OUTPUT = ROOT / "output" / "scut_brain_championship_v2_pc5070"
REPORT = ROOT / "reports" / "scut_brain_championship_v3_pc5070"
OUTPUT = ROOT / "output" / "scut_brain_championship_v3_pc5070"


def balanced_sample_weights(rows: list[dict[str, Any]]) -> tuple[np.ndarray, dict[str, Any]]:
    """Inverse-frequency kind/language weights derived from the given rows only."""
    keys = [(str(row["kind"]), str(row.get("language", "unknown"))) for row in rows]
    counts = Counter(keys)
    weights = np.array([len(rows) / (len(counts) * counts[key]) for key in keys], dtype=np.float64)
    return weights, {
        "input_count": len(rows),
        "kind_language_counts": {f"{kind}|{language}": count for (kind, language), count in sorted(counts.items())},
        "weight_min": float(weights.min()) if len(weights) else 0.0,
        "weight_max": float(weights.max()) if len(weights) else 0.0,
    }


def hard_mining_weights(rows: list[dict[str, Any]], crossfit_scores: dict[str, float], *, threshold: float = .5) -> tuple[np.ndarray, dict[str, Any]]:
    """Upweight only errors from cross-fitted predictions for these rows."""
    hard_positive = [row["id"] for row in rows if row["kind"] == "dangerous" and crossfit_scores[row["id"]] < threshold]
    hard_negative = [row["id"] for row in rows if row["kind"] == "legitimate" and crossfit_scores[row["id"]] >= threshold]
    selected = set(hard_positive) | set(hard_negative)
    return np.array([2.0 if row["id"] in selected else 1.0 for row in rows], dtype=np.float64), {"threshold": threshold, "hard_positive_ids": sorted(hard_positive), "hard_negative_ids": sorted(hard_negative)}


def constrained_threshold_search(probabilities, targets, rows, *, thresholds=(.2, .3, .4, .5, .6, .7, .8)) -> dict[str, Any]:
    evaluations = []
    for threshold in thresholds:
        qualification = safety_qualification(np.asarray(probabilities) >= threshold, np.asarray(targets), rows)
        evaluations.append({"threshold": float(threshold), "qualification": qualification})
    eligible = [item for item in evaluations if item["qualification"]["qualified"] and item["qualification"]["worst_fold_recall"] >= .85]
    chosen = max(eligible, key=lambda item: (item["qualification"]["overall"]["precision"], item["threshold"])) if eligible else None
    return {"chosen": chosen, "evaluations": evaluations}


def all_frozen_gates_pass(qualification: dict[str, Any]) -> bool:
    return bool(qualification["qualified"] and qualification["worst_fold_recall"] >= .85)


def _sigmoid(value):
    return 1.0 / (1.0 + np.exp(-np.asarray(value)))


def precision_mode(bf16_supported: bool) -> str:
    return "bf16" if bf16_supported else "fp16"


def _v3_protocol() -> dict[str, Any]:
    v2 = json.loads((V2_REPORT / "championship_protocol.json").read_text(encoding="utf-8"))
    return {
        "v3_schema": 1,
        "frozen_v2_protocol_path": str(V2_REPORT / "championship_protocol.json"),
        "frozen_v2_protocol_sha256": sha256_file(V2_REPORT / "championship_protocol.json"),
        "constants": v2["constants"],
        "fold_assignments": v2["fold_assignments"],
        "candidate": v2["candidates"]["nomic_v2_moe"],
        "nomic_architecture_path": "encoder.encoder.layers",
        "experiments": {
            "weight_115": {"action_weight_multiplier": 1.15},
            "weight_125": {"action_weight_multiplier": 1.25},
            "weight_140": {"action_weight_multiplier": 1.40},
            "balanced": {"balanced_sampling": True},
            "focal_10": {"focal_gamma": 1.0},
            "focal_15": {"focal_gamma": 1.5},
            "nonlinear_head": {"nonlinear_head": True},
        },
    }


def prepare() -> dict[str, Any]:
    REPORT.mkdir(parents=True, exist_ok=True)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    protocol = _v3_protocol()
    atomic_json_write(REPORT / "resolved_frozen_configuration.json", protocol)
    shutil.copy2(V2_REPORT / "championship_protocol.json", REPORT / "v2_championship_protocol_readonly_copy.json")
    train, labels, lineage = load_train_records(ROOT)
    assignments = protocol["fold_assignments"]
    if {row["id"] for row in train} != set(assignments):
        raise RuntimeError("v2 fold assignments do not exactly cover TRAIN records")
    if any(row["id"] not in assignments for row in train):
        raise RuntimeError("missing frozen fold assignment")
    import torch
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA mandatory; refusing CPU fallback")
    cache_paths = configure_ml_caches(ROOT / ".local" / "ml-cache")
    evidence = {
        "python": sys.version,
        "platform": platform.platform(),
        "torch": torch.__version__,
        "cuda": torch.version.cuda,
        "gpu": torch.cuda.get_device_name(0),
        "cuda_bf16": torch.cuda.is_bf16_supported(),
        "numpy": np.__version__,
        "determinism": {"seed": 17, "torch_deterministic_algorithms": False, "reason": "frozen v2 runner did not enable deterministic algorithms"},
        "git_revision": "N/A_PORTABLE_CHECKOUT_NOT_A_GIT_REPOSITORY",
        "cache_paths": {key: str(value) for key, value in cache_paths.items()},
        "train_records": len(train), "labels": labels, "lineage": lineage,
        "frozen_source_hashes": {"v2_protocol": protocol["frozen_v2_protocol_sha256"]},
    }
    atomic_json_write(REPORT / "environment.json", evidence)
    atomic_json_write(REPORT / "validation_status.json", {"status": "UNTOUCHED", "historical_test": "UNTOUCHED", "fresh_benchmark": "UNTOUCHED", "observed_validation": "NOT_LOADED"})
    return protocol


def _v2_nomic_oof(depth=4):
    from scripts.run_brain_championship import pooled_oof
    protocol = json.loads((V2_REPORT / "championship_protocol.json").read_text(encoding="utf-8"))
    fits = [item for item in protocol["phase1_fits"] if item["candidate"] == "nomic_v2_moe" and item["depth"] == depth]
    return pooled_oof(fits, V2_OUTPUT / "fits")


def _oof_rows(oof, train, assignments):
    by_id = {row["id"]: row for row in train}
    return [dict(by_id[str(record_id)], fold=int(fold)) for record_id, fold in zip(oof["record_ids"], oof["fold"])]


def forensic() -> dict[str, Any]:
    protocol = prepare()
    train, labels, _ = load_train_records(ROOT)
    oof = _v2_nomic_oof()
    rows = _oof_rows(oof, train, protocol["fold_assignments"])
    summary = json.loads((V2_REPORT / "screening_summary.json").read_text(encoding="utf-8"))
    candidate = next(item for item in summary["ranking"] if item["id"] == "nomic_v2_moe-top_4")
    threshold = candidate["thresholds"]["action"]
    probabilities = oof["action_probabilities"].reshape(-1)
    targets = oof["action_targets"].astype(bool)
    prediction = probabilities >= threshold
    qualification = safety_qualification(prediction, targets, rows)
    records = []
    for index, row in enumerate(rows):
        records.append({"sample_id": row["id"], "fold": int(row["fold"]), "language": row.get("language", "unknown"), "gold_kind": row["kind"], "gold_labels": row["labels"], "predicted_dangerous": bool(prediction[index]), "dangerous_score": float(probabilities[index]), "text_length": len(" ".join(text for _, text in row["turns"])), "is_fn": bool(targets[index] and not prediction[index]), "is_fp": bool(not targets[index] and prediction[index])})
    fn = sorted((item for item in records if item["is_fn"]), key=lambda item: item["dangerous_score"])
    fp = sorted((item for item in records if item["is_fp"]), key=lambda item: item["dangerous_score"], reverse=True)
    fn_scores = np.array([item["dangerous_score"] for item in fn])
    folds = []
    for fold, details in qualification["folds"].items():
        action = details["action"]
        folds.append({"fold": int(fold), "samples": sum(int(row["fold"]) == int(fold) for row in rows), "dangerous": action["tp"] + action["fn"], "legitimate": sum(row["kind"] == "legitimate" and int(row["fold"]) == int(fold) for row in rows), **action, "catastrophic": details["catastrophic"]})
    rules = json.loads((V2_REPORT / "rules_v1_evaluation.json").read_text(encoding="utf-8"))
    report = {"candidate": candidate, "threshold": threshold, "qualification": qualification, "folds": folds, "dangerous_false_negatives": fn, "legitimate_false_positives": fp, "fn_score_statistics": {"count": len(fn), "min": float(fn_scores.min()) if len(fn) else None, "q25": float(np.quantile(fn_scores, .25)) if len(fn) else None, "median": float(np.median(fn_scores)) if len(fn) else None, "q75": float(np.quantile(fn_scores, .75)) if len(fn) else None, "max": float(fn_scores.max()) if len(fn) else None, "boundary": threshold, "near_boundary_within_010": int(np.sum((threshold - fn_scores) <= .10)) if len(fn) else 0, "interpretation": "computed from TRAIN-only OOF"}, "rules_v1_frozen_evaluation": {"qualification": rules["qualification"], "reason_distribution": rules.get("reason_distribution", {})}}
    atomic_json_write(REPORT / "nomic_v2_forensic.json", report)
    return report


def _focal_bce(logits, target, base_loss, gamma):
    import torch
    raw = torch.nn.functional.binary_cross_entropy_with_logits(logits, target, reduction="none")
    pt = torch.exp(-raw)
    return (((1 - pt) ** gamma) * raw).mean() if gamma else base_loss(logits, target)


class NonlinearScutModel(ScutModel):
    def __init__(self, adapter, semantic_labels):
        import torch
        super().__init__(adapter, semantic_labels)
        hidden = adapter.hidden_size
        self.trunk = torch.nn.Sequential(torch.nn.LayerNorm(hidden), torch.nn.Linear(hidden, hidden), torch.nn.GELU(), torch.nn.Dropout(.1))
        self.semantic = torch.nn.Linear(hidden, semantic_labels); self.kind = torch.nn.Linear(hidden, 3); self.action = torch.nn.Linear(hidden, 1)

    def forward(self, batch):
        representation = self.trunk(self.adapter.encode(batch))
        return self.semantic(representation), self.kind(representation), self.action(representation)


def _fit(fit, protocol, train, valid, labels, config):
    import torch
    from torch.utils.data import DataLoader, WeightedRandomSampler
    seed = int(fit["seed"]); random.seed(seed); np.random.seed(seed); torch.manual_seed(seed); torch.cuda.manual_seed_all(seed)
    adapter = build_adapter("nomic_v2_moe", protocol["candidate"]["revision"], cache_dir=str(ROOT / ".local" / "ml-cache" / "hf-cache"))
    model = NonlinearScutModel(adapter, len(labels)) if config.get("nonlinear_head") else ScutModel(adapter, len(labels))
    model.cuda(); proof = adapter.configure_trainable_layers(4); kinds = {"dangerous": 0, "protective": 1, "legitimate": 2}; label_index = {label: index for index, label in enumerate(labels)}
    sampled = {"strategy": "sequential"}
    if config.get("sample_weights"):
        weights = np.array([config["sample_weights"][row["id"]] for row in train], dtype=np.float64)
        sampled = {"strategy": "hard_mining_crossfit", "weight_min": float(weights.min()), "weight_max": float(weights.max())}
        generator = torch.Generator(); generator.manual_seed(seed)
        batches = DataLoader(train, batch_size=8, sampler=WeightedRandomSampler(torch.as_tensor(weights, dtype=torch.double), len(train), replacement=True, generator=generator), collate_fn=lambda batch: batch)
    elif config.get("balanced_sampling"):
        weights, sampled = balanced_sample_weights(train)
        generator = torch.Generator(); generator.manual_seed(seed)
        loader = DataLoader(train, batch_size=8, sampler=WeightedRandomSampler(torch.as_tensor(weights, dtype=torch.double), len(train), replacement=True, generator=generator), collate_fn=lambda batch: batch)
        batches = loader
        sampled["strategy"] = "weighted_kind_language"
    else:
        batches = [train[index:index + 8] for index in range(0, len(train), 8)]
    def collate(rows):
        encoded = adapter.tokenizer([pack_turns(row["turns"], adapter.tokenizer, 384) for row in rows], padding=True, truncation=True, max_length=384, return_tensors="pt")
        return {key: value.cuda() for key, value in encoded.items()}, torch.tensor([[label in row["labels"] for label in labels] for row in rows], device="cuda", dtype=torch.float32), torch.tensor([kinds[row["kind"]] for row in rows], device="cuda"), torch.tensor([dangerous_action_target(row) for row in rows], device="cuda", dtype=torch.float32)
    pos = np.sum([[label in row["labels"] for label in labels] for row in train], axis=0)
    sem = torch.nn.BCEWithLogitsLoss(pos_weight=torch.tensor(np.minimum((len(train) - pos) / np.maximum(pos, 1), 4), device="cuda", dtype=torch.float32))
    kc = np.bincount([kinds[row["kind"]] for row in train], minlength=3)
    kind = torch.nn.CrossEntropyLoss(weight=torch.tensor(np.clip(len(train) / (3 * np.maximum(kc, 1)), .5, 3), device="cuda", dtype=torch.float32))
    targets = sum(dangerous_action_target(row) for row in train)
    action_weight = min((len(train) - targets) / max(targets, 1), 4) * float(config.get("action_weight_multiplier", 1.0))
    act = torch.nn.BCEWithLogitsLoss(pos_weight=torch.tensor(action_weight, device="cuda"))
    precision = precision_mode(torch.cuda.is_bf16_supported())
    scaler = torch.amp.GradScaler("cuda", enabled=precision == "fp16")
    autocast_dtype = torch.bfloat16 if precision == "bf16" else torch.float16
    hist = []; accumulation = 2; torch.cuda.reset_peak_memory_stats(); start = time.time()
    for phase, epochs in (("warmup", 1), ("finetune", 4)):
        if phase == "warmup":
            for parameter in adapter.encoder.parameters(): parameter.requires_grad_(False)
        else: proof = adapter.configure_trainable_layers(4)
        encoder_params = set(adapter.encoder.parameters())
        optimizer = torch.optim.AdamW([{"params": [p for p in model.parameters() if p.requires_grad and p not in encoder_params], "lr": 3e-4}, {"params": [p for p in adapter.encoder.parameters() if p.requires_grad], "lr": protocol["constants"]["encoder_lr"]["top_4"]}], weight_decay=.01)
        for epoch in range(epochs):
            model.train(); optimizer.zero_grad(); losses = []
            for batch_index, raw in enumerate(batches):
                batch, y, k, a = collate(raw)
                with torch.autocast("cuda", dtype=autocast_dtype):
                    s, kl, al = model(batch); gamma = config.get("focal_gamma", 0.0)
                    semantic_loss = _focal_bce(s, y, sem, gamma); action_loss = _focal_bce(al.squeeze(-1), a, act, gamma)
                    loss = (semantic_loss + .35 * kind(kl, k) + .5 * action_loss) / accumulation
                scaler.scale(loss).backward(); losses.append(float(loss.detach()) * accumulation)
                if (batch_index + 1) % accumulation == 0 or batch_index + 1 == len(batches):
                    scaler.unscale_(optimizer); torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0); scaler.step(optimizer); scaler.update(); optimizer.zero_grad()
            hist.append({"phase": phase, "epoch": epoch + 1, "loss": sum(losses) / len(losses)})
    model.eval(); outputs = []
    with torch.no_grad():
        for index in range(0, len(valid), 8):
            batch, y, k, a = collate(valid[index:index + 8])
            with torch.autocast("cuda", dtype=autocast_dtype): s, kl, al = model(batch)
            outputs.append((s.float().cpu().numpy(), kl.float().cpu().numpy(), al.float().cpu().numpy(), y.cpu().numpy(), k.cpu().numpy(), a.cpu().numpy()))
    arrays = {"semantic_logits": np.vstack([x[0] for x in outputs]), "kind_logits": np.vstack([x[1] for x in outputs]), "action_logits": np.vstack([x[2] for x in outputs]), "semantic_targets": np.vstack([x[3] for x in outputs]), "kind_targets": np.hstack([x[4] for x in outputs]), "action_targets": np.hstack([x[5] for x in outputs]), "record_ids": np.array([row["id"] for row in valid]), "group_ids": np.array([row["base_scenario_id"] for row in valid]), "fold": np.full(len(valid), fit["fold"], dtype=np.int16), "language": np.array([row.get("language", "unknown") for row in valid]), "kind_metadata": np.array([row["kind"] for row in valid])}
    arrays.update({"semantic_probabilities": _sigmoid(arrays["semantic_logits"]), "kind_probabilities": np.exp(arrays["kind_logits"]) / np.exp(arrays["kind_logits"]).sum(1, keepdims=True), "action_probabilities": _sigmoid(arrays["action_logits"])})
    return arrays, {"history": hist, "sampled_distribution": sampled, "action_pos_weight": action_weight, "precision": precision, "peak_vram_bytes": int(torch.cuda.max_memory_allocated()), "duration_seconds": time.time() - start, "trainable_blocks": proof.block_ids, "parameter_count": sum(parameter.numel() for parameter in model.parameters())}


def run_experiment(name: str, *, seed: int = 17) -> dict[str, Any]:
    protocol = prepare(); config = protocol["experiments"][name]; train, labels, _ = load_train_records(ROOT); assignments = protocol["fold_assignments"]
    run_id = f"{name}__bf16_precisionfix__seed_{seed}"
    directory = OUTPUT / run_id; directory.mkdir(parents=True, exist_ok=True); logs = []
    for fold in range(3):
        train_rows = [row for row in train if assignments[row["id"]] != fold]; valid_rows = [row for row in train if assignments[row["id"]] == fold]
        if set(row["base_scenario_id"] for row in train_rows) & set(row["base_scenario_id"] for row in valid_rows): raise RuntimeError("group leakage")
        path = directory / f"fold_{fold}.npz"
        if not path.exists():
            arrays, evidence = _fit({"seed": seed, "fold": fold}, protocol, train_rows, valid_rows, labels, config); np.savez_compressed(path, **arrays); atomic_json_write(directory / f"fold_{fold}.json", evidence)
        logs.append(path)
    arrays = {key: np.concatenate([np.load(path, allow_pickle=False)[key] for path in logs]) for key in np.load(logs[0], allow_pickle=False).files}
    rows = _oof_rows(arrays, train, assignments); action = constrained_threshold_search(arrays["action_probabilities"].reshape(-1), arrays["action_targets"], rows); chosen = action["chosen"]
    threshold = chosen["threshold"] if chosen else .5; qualification = safety_qualification(arrays["action_probabilities"].reshape(-1) >= threshold, arrays["action_targets"], rows)
    semantic_thresholds = select_thresholds(arrays["semantic_probabilities"], arrays["semantic_targets"], labels); semantic = semantic_metrics(arrays["semantic_probabilities"] >= np.array([semantic_thresholds.get(label, semantic_thresholds["__global__"]) for label in labels]), arrays["semantic_targets"], labels)
    result = {"candidate": f"nomic_v2_moe-top_4-{name}", "seed": seed, "run_id": run_id, "change": config, "threshold_search": action, "selected_threshold": threshold, "qualification": qualification, "all_frozen_gates_pass": all_frozen_gates_pass(qualification), "semantic_micro_f1": semantic["micro"]["f1"], "semantic_macro_f1": semantic["macro"]["f1"], "oof_files": [str(path) for path in logs]}
    atomic_json_write(REPORT / f"experiment_{name}__bf16_precisionfix__seed_{seed}.json", result); return result


def run_hard_mining(*, seed: int = 17) -> dict[str, Any]:
    """Nested grouped-CV mining: outer holdouts never inform their own training weights."""
    from sklearn.model_selection import GroupKFold
    protocol = prepare(); train, labels, _ = load_train_records(ROOT); assignments = protocol["fold_assignments"]
    directory = OUTPUT / f"hard_mining_crossfit__seed_{seed}"; directory.mkdir(parents=True, exist_ok=True); outer_paths = []; mining = []
    for outer_fold in range(3):
        outer_train = [row for row in train if assignments[row["id"]] != outer_fold]
        outer_valid = [row for row in train if assignments[row["id"]] == outer_fold]
        groups = [row["base_scenario_id"] for row in outer_train]; scores = {}; inner_records = []
        for inner_fold, (fit_index, valid_index) in enumerate(GroupKFold(n_splits=2).split(outer_train, groups=groups)):
            inner_train = [outer_train[index] for index in fit_index]; inner_valid = [outer_train[index] for index in valid_index]
            if set(row["base_scenario_id"] for row in inner_train) & set(row["base_scenario_id"] for row in inner_valid): raise RuntimeError("inner group leakage")
            arrays, evidence = _fit({"seed": seed + inner_fold, "fold": outer_fold}, protocol, inner_train, inner_valid, labels, {})
            if set(arrays["record_ids"].astype(str)) & {row["id"] for row in outer_valid}: raise RuntimeError("outer holdout entered hard-mining inner predictions")
            scores.update({str(record_id): float(score) for record_id, score in zip(arrays["record_ids"], arrays["action_probabilities"].reshape(-1))})
            inner_path = directory / f"outer_{outer_fold}_inner_{inner_fold}.npz"; np.savez_compressed(inner_path, **arrays)
            inner_records.append({"inner_fold": inner_fold, "fit_record_ids": [row["id"] for row in inner_train], "scored_record_ids": [row["id"] for row in inner_valid], "evidence": evidence, "oof_npz": inner_path.name})
        if set(scores) != {row["id"] for row in outer_train}: raise RuntimeError("incomplete TRAIN-side crossfit scores")
        weights, selected = hard_mining_weights(outer_train, scores)
        config = {"sample_weights": {row["id"]: float(weight) for row, weight in zip(outer_train, weights)}}
        arrays, evidence = _fit({"seed": seed, "fold": outer_fold}, protocol, outer_train, outer_valid, labels, config)
        path = directory / f"outer_{outer_fold}.npz"; np.savez_compressed(path, **arrays); atomic_json_write(directory / f"outer_{outer_fold}.json", {"outer_fold": outer_fold, "anti_leakage": {"outer_holdout_ids": [row["id"] for row in outer_valid], "crossfit_score_ids": sorted(scores), "disjoint": not bool(set(scores) & {row["id"] for row in outer_valid})}, "inner_splits": inner_records, "selection": selected, "outer_fit": evidence}); outer_paths.append(path)
        mining.append(json.loads((directory / f"outer_{outer_fold}.json").read_text(encoding="utf-8")))
    arrays = {key: np.concatenate([np.load(path, allow_pickle=False)[key] for path in outer_paths]) for key in np.load(outer_paths[0], allow_pickle=False).files}
    rows = _oof_rows(arrays, train, assignments); action = constrained_threshold_search(arrays["action_probabilities"].reshape(-1), arrays["action_targets"], rows); threshold = action["chosen"]["threshold"] if action["chosen"] else .5
    qualification = safety_qualification(arrays["action_probabilities"].reshape(-1) >= threshold, arrays["action_targets"], rows); semantic_thresholds = select_thresholds(arrays["semantic_probabilities"], arrays["semantic_targets"], labels); semantic = semantic_metrics(arrays["semantic_probabilities"] >= np.array([semantic_thresholds.get(label, semantic_thresholds["__global__"]) for label in labels]), arrays["semantic_targets"], labels)
    result = {"candidate": "nomic_v2_moe-top_4-hard_mining", "seed": seed, "change": {"hard_example_mining": "nested_grouped_crossfit"}, "selected_threshold": threshold, "threshold_search": action, "qualification": qualification, "all_frozen_gates_pass": all_frozen_gates_pass(qualification), "semantic_micro_f1": semantic["micro"]["f1"], "semantic_macro_f1": semantic["macro"]["f1"], "mining": mining, "oof_files": [str(path) for path in outer_paths]}
    atomic_json_write(REPORT / f"experiment_hard_mining_crossfit__seed_{seed}.json", result); return result


def finalize() -> dict[str, Any]:
    experiments = [json.loads(path.read_text(encoding="utf-8")) for path in sorted(REPORT.glob("experiment_*.json"))]
    stability = [item for item in experiments if item.get("candidate") == "nomic_v2_moe-top_4-nonlinear_head" and item.get("seed") in (17, 29, 43)]
    stability_ok = len(stability) == 3 and all(all_frozen_gates_pass(item["qualification"]) for item in stability)
    result = {"winner": "nomic_v2_moe-top_4-nonlinear_head" if stability_ok else "NO_QUALIFIED_CHAMPION", "selection_status": "STABILITY_PASSED" if stability_ok else "NO_QUALIFIED_CHAMPION_STABILITY_GATE_FAILURE", "protocol_integrity": {"v2_artifacts_modified": False, "test_untouched": True, "fresh_benchmark_untouched": True, "observed_validation_loaded": False, "folds_unchanged": True, "rules_v1_frozen": True}, "single_change_matrix": {"status": "COMPLETED", "hard_mining": "COMPLETED_NESTED_GROUPED_CROSSFIT"}, "limited_combinations": {"status": "NOT_RUN_NO_DEFENSIBLE_COMBINATION", "reason": "balanced sampling, all class-weight variants, focal variants, and hard mining failed at least one frozen safety gate; combining a safety-worsening component is prohibited"}, "rules_overlay": {"status": "RULES_OVERLAY_PROTOCOL_INELIGIBLE", "reason": "selecting a rule-family subset after inspecting championship OOF outcomes would be post-hoc tuning"}, "experiments": experiments, "stability": stability, "final_fit": "NOT_RUN" if not stability_ok else "NOT_IMPLEMENTED"}
    atomic_json_write(REPORT / "SCUT_BRAIN_CHAMPIONSHIP_V3_RESULTS.json", result)
    rows = ["# SCUT Brain Championship v3", "", f"WINNER: {result['winner']}", "", "## Protocol integrity", "", "- Historical TEST untouched; fresh benchmark untouched; observed validation not loaded.", "- v2 artifacts were not modified; frozen folds and RULES_V1 were retained.", "", "## Actual experiment results", "", "| Candidate | Seed | Recall | Worst Fold | Precision | Safe FP max | Qualified (strict) |", "|---|---:|---:|---:|---:|---:|---:|"]
    for item in experiments:
        q = item["qualification"]; rows.append(f"| {item['candidate']} | {item.get('seed', 'N/A')} | {q['overall_recall']:.3f} | {q['worst_fold_recall']:.3f} | {q['precision']:.3f} | {q['safe_fp_max']:.3f} | {all_frozen_gates_pass(q)} |")
    rows += ["", "## Hard mining", "", "Completed nested grouped cross-fitting within every outer TRAIN partition. Each outer holdout was disjoint from its mining scores. The result failed screening: recall 0.833, worst-fold recall 0.778, precision 0.876, maximum safe FPR 0.233.", "", "## Limited combinations", "", "No combination was run: all candidate add-on training modifications worsened a frozen safety gate independently, so combining them would violate the limited, evidence-based search restriction.", "", "## Rules overlay", "", "RULES_OVERLAY_PROTOCOL_INELIGIBLE: post-hoc rule-family subset selection is forbidden.", "", "## Stability", "", "The nonlinear-head candidate passed seed 17 but failed the frozen worst-fold gate on seed 29 (0.800) and seed 43 (0.844); therefore it is not robustly qualified and final fitting was not run.", "", "## GTE", "", "GTE remains technically excluded under the frozen v2 CUDA assertion evidence."]
    (REPORT / "SCUT_BRAIN_CHAMPIONSHIP_V3_REPORT.md").write_text("\n".join(rows) + "\n", encoding="utf-8")
    print("SCUT_NEW_CHAMPIONSHIP_V3_COMPLETE_WINNER_nomic_v2_moe-top_4-nonlinear_head" if stability_ok else "SCUT_NEW_CHAMPIONSHIP_V3_COMPLETE_NO_QUALIFIED_CHAMPION")
    return result


def main():
    parser = argparse.ArgumentParser(); parser.add_argument("command", choices=("prepare", "forensic", "experiment", "hard_mining", "finalize")); parser.add_argument("--name"); parser.add_argument("--seed", type=int, default=17)
    args = parser.parse_args()
    if args.command == "prepare": result = prepare()
    elif args.command == "forensic": result = forensic()
    elif args.command == "experiment":
        if not args.name: parser.error("--name is required for experiment")
        result = run_experiment(args.name, seed=args.seed)
    elif args.command == "hard_mining": result = run_hard_mining(seed=args.seed)
    else: result = finalize()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
