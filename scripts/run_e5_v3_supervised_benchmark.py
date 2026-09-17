"""Train and frozen-evaluate the local E5 v3 multi-label semantic experiment.

This is experimental-only: it reads the immutable v3 corpus and never imports
or modifies production risk-policy code.
"""
from __future__ import annotations

import json, os, platform, random, sys, time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import psutil
import torch
from torch import nn
from transformers import AutoModel, AutoTokenizer, __version__ as transformers_version

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "experiments" / "semantic_corpus_v3.json"
MODEL = ROOT / ".local" / "models" / "multilingual-e5-base"
OUT = ROOT / "output" / "scut_e5_v3_supervised"
REPORT = ROOT / "reports" / "scut_e5_v3_supervised_benchmark.json"
SEEDS = (17, 23, 41)
ACTION = {"CREDENTIAL_DISCLOSURE", "MONEY_OR_ASSET_MOVEMENT", "REMOTE_DEVICE_ACCESS",
          "AUTHORIZATION_OR_APPROVAL", "LINK_OR_QR_ACTION", "CASH_OR_COURIER_HANDOFF",
          "LOAN_OR_CREDIT_ACTION", "CRYPTO_OR_GIFT_VALUE_TRANSFER", "PERSONAL_DATA_DISCLOSURE"}


def transcript(row):
    return "query: " + " ".join(f"[{speaker}] {text}" for speaker, text in row["turns"])


def score_counts(pred, truth):
    tp = int(np.logical_and(pred, truth).sum()); fp = int(np.logical_and(pred, ~truth).sum())
    fn = int(np.logical_and(~pred, truth).sum())
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"tp": tp, "fp": fp, "fn": fn, "precision": precision, "recall": recall, "f1": f1}


def metric_bundle(pred, truth, labels):
    micro = score_counts(pred, truth)
    per_label = {}
    values = []
    for index, label in enumerate(labels):
        item = score_counts(pred[:, index], truth[:, index])
        item["support"] = int(truth[:, index].sum())
        item["predicted"] = int(pred[:, index].sum())
        per_label[label] = item
        values.append(item)
    macro = {name: float(np.mean([item[name] for item in values])) for name in ("precision", "recall", "f1")}
    return {"micro": micro, "macro": macro, "subset_accuracy": float(np.all(pred == truth, axis=1).mean()),
            "per_label": per_label, "records": int(len(truth))}


def encode(model, tokenizer, rows, device, batch_size=4):
    vectors = []; model.eval()
    with torch.no_grad():
        for start in range(0, len(rows), batch_size):
            tokens = tokenizer([transcript(row) for row in rows[start:start + batch_size]],
                               padding=True, truncation=True, max_length=256, return_tensors="pt").to(device)
            hidden = model(**tokens).last_hidden_state
            mask = tokens["attention_mask"].unsqueeze(-1)
            pooled = (hidden * mask).sum(1) / mask.sum(1).clamp(min=1)
            vectors.append(nn.functional.normalize(pooled, p=2, dim=1).cpu())
    return torch.cat(vectors).numpy()


def train_head(train_x, train_y, validation_x, validation_y, seed, labels, device):
    random.seed(seed); np.random.seed(seed); torch.manual_seed(seed)
    head = nn.Sequential(nn.Dropout(0.10), nn.Linear(train_x.shape[1], train_y.shape[1])).to(device)
    train_x = torch.tensor(train_x, dtype=torch.float32, device=device)
    train_y = torch.tensor(train_y, dtype=torch.float32, device=device)
    val_x = torch.tensor(validation_x, dtype=torch.float32, device=device)
    positives = train_y.sum(0).cpu().numpy()
    weights = torch.tensor(np.clip((len(train_y) - positives) / np.maximum(positives, 1), 1, 20),
                           dtype=torch.float32, device=device)
    loss_fn = nn.BCEWithLogitsLoss(pos_weight=weights)
    optimizer = torch.optim.AdamW(head.parameters(), lr=2e-3, weight_decay=1e-3)
    history = []; best = None; stale = 0
    for epoch in range(1, 61):
        head.train(); optimizer.zero_grad()
        loss = loss_fn(head(train_x), train_y); loss.backward(); optimizer.step()
        head.eval()
        with torch.no_grad():
            probabilities = torch.sigmoid(head(val_x)).cpu().numpy()
        thresholded = probabilities >= 0.5
        val_metrics = metric_bundle(thresholded, validation_y.astype(bool), labels)
        entry = {"epoch": epoch, "loss": float(loss.item()), "validation_macro_f1_at_0_5": val_metrics["macro"]["f1"]}
        history.append(entry)
        if best is None or entry["validation_macro_f1_at_0_5"] > best["score"]:
            best = {"score": entry["validation_macro_f1_at_0_5"], "epoch": epoch,
                    "state": {key: value.detach().cpu().clone() for key, value in head.state_dict().items()}}
            stale = 0
        else:
            stale += 1
        if stale >= 8:
            break
    head.load_state_dict(best["state"])
    head.eval()
    with torch.no_grad():
        probabilities = torch.sigmoid(head(val_x)).cpu().numpy()
    thresholds = np.full(len(labels), 0.5)
    for index in range(len(labels)):
        if positives[index] == 0:
            thresholds[index] = 1.1
        elif validation_y[:, index].sum():
            thresholds[index] = max((0.20, 0.35, 0.50, 0.65, 0.80),
                                    key=lambda value: score_counts(probabilities[:, index] >= value,
                                                                   validation_y[:, index].astype(bool))["f1"])
    return head, best, history, probabilities, thresholds


def labeled_rows(corpus, labels):
    rows = corpus["bases"] + corpus["variants"]
    base = {row["id"]: row for row in corpus["bases"]}
    seen = set()
    for row in rows:
        if row["id"] in seen:
            raise ValueError(f"duplicate id: {row['id']}")
        seen.add(row["id"])
        if row in corpus["variants"]:
            source = base.get(row["base_scenario_id"])
            if source is None or any(row[key] != source[key] for key in ("split", "language", "labels")):
                raise ValueError(f"lineage leakage: {row['id']}")
    mapping = {label: index for index, label in enumerate(labels)}
    y = np.zeros((len(rows), len(labels)), dtype=np.float32)
    for index, row in enumerate(rows):
        for label in row["labels"]:
            y[index, mapping[label]] = 1
    return rows, y


def safety(rows, pred, truth, labels):
    action_indices = [labels.index(label) for label in ACTION]
    expected_action = truth[:, action_indices].any(1)
    predicted_action = pred[:, action_indices].any(1)
    dangerous = np.array([row.get("kind") == "dangerous" for row in rows])
    protective = np.array([row.get("kind") == "protective" for row in rows])
    legitimate = np.array([row.get("kind") == "legitimate" for row in rows])
    manipulation_only = np.array([bool(set(row["labels"]) - ACTION) and not bool(set(row["labels"]) & ACTION) and
                                  bool(set(row["labels"]) & {"ISOLATION", "URGENCY_OR_TIME_PRESSURE", "FEAR_OR_THREAT",
                                                             "AUTHORITY_PRESSURE", "SECRECY", "DISCOURAGE_VERIFICATION",
                                                             "KEEP_CALL_ACTIVE", "EMOTIONAL_OR_FAMILY_PRESSURE",
                                                             "TRUST_OR_COMPLIANCE_MANIPULATION"}) for row in rows])
    rate = lambda numerator, denominator: float(numerator / denominator) if denominator else None
    return {"dangerous_action_recall": rate((predicted_action & expected_action).sum(), expected_action.sum()),
            "dangerous_false_negatives": int((expected_action & ~predicted_action).sum()),
            "protective_false_positive_rate": rate((predicted_action & protective).sum(), protective.sum()),
            "legitimate_false_positive_rate": rate((predicted_action & legitimate).sum(), legitimate.sum()),
            "manipulation_only_predicted_action_rate": rate((predicted_action & manipulation_only).sum(), manipulation_only.sum()),
            "counts": {"dangerous": int(dangerous.sum()), "protective": int(protective.sum()),
                       "legitimate": int(legitimate.sum()), "manipulation_only": int(manipulation_only.sum())}}


def json_dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    started = time.perf_counter(); OUT.mkdir(parents=True, exist_ok=True)
    corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
    labels = sorted({label for row in corpus["bases"] for label in row["labels"]})
    rows, y = labeled_rows(corpus, labels)
    grouped = {split: [index for index, row in enumerate(rows) if row["split"] == split]
               for split in ("train", "validation", "test")}
    if set(row["base_scenario_id"] for row in rows if row["split"] == "train") & set(row["base_scenario_id"] for row in rows if row["split"] != "train"):
        raise ValueError("base scenario appears in train and non-train split")
    device = "cuda" if torch.cuda.is_available() else "cpu"
    config = {"base_encoder": "intfloat/multilingual-e5-base", "local_model_path": str(MODEL),
              "encoder_frozen": True, "head": "dropout(0.10)+linear multi-label", "loss": "BCEWithLogitsLoss(pos_weight)",
              "optimizer": "AdamW", "learning_rate": 0.002, "weight_decay": 0.001, "batch_size_encoding": 4,
              "max_epochs": 60, "early_stopping_patience": 8, "threshold_grid": [0.20, 0.35, 0.50, 0.65, 0.80],
              "seeds": list(SEEDS), "device": device, "labels": labels,
              "record_counts": {split: len(indices) for split, indices in grouped.items()},
              "base_counts": {split: sum(row["split"] == split for row in corpus["bases"]) for split in grouped}}
    json_dump(OUT / "training_config.json", config)
    model_load_started = time.perf_counter()
    tokenizer = AutoTokenizer.from_pretrained(MODEL, local_files_only=True)
    encoder = AutoModel.from_pretrained(MODEL, local_files_only=True).to(device)
    model_load_seconds = time.perf_counter() - model_load_started
    train_rows = [rows[index] for index in grouped["train"]]; val_rows = [rows[index] for index in grouped["validation"]]
    train_x = encode(encoder, tokenizer, train_rows, device); val_x = encode(encoder, tokenizer, val_rows, device)
    runs = []
    for seed in SEEDS:
        head, best, history, val_prob, thresholds = train_head(train_x, y[grouped["train"]], val_x, y[grouped["validation"]],
                                                               seed, labels, device)
        run = {"seed": seed, "best_epoch": best["epoch"], "validation_macro_f1_at_0_5": best["score"],
               "validation_metrics_selected_thresholds": metric_bundle(val_prob >= thresholds, y[grouped["validation"]].astype(bool), labels),
               "thresholds": {label: float(thresholds[index]) for index, label in enumerate(labels)},
               "history": history}
        json_dump(OUT / f"history_seed_{seed}.json", run)
        runs.append((run, {key: value.cpu() for key, value in head.state_dict().items()}))
    selected, selected_state = max(runs, key=lambda item: item[0]["validation_metrics_selected_thresholds"]["macro"]["f1"])
    checkpoint = OUT / "selected_head.pt"
    torch.save({"state_dict": selected_state, "labels": labels, "thresholds": selected["thresholds"], "seed": selected["seed"],
                "best_epoch": selected["best_epoch"]}, checkpoint)
    json_dump(OUT / "validation_selection.json", selected)
    # Test features and predictions are deliberately generated only after the
    # selected validation configuration has been persisted.
    test_rows = [rows[index] for index in grouped["test"]]
    test_x = encode(encoder, tokenizer, test_rows, device)
    head = nn.Sequential(nn.Dropout(0.10), nn.Linear(test_x.shape[1], len(labels))).to(device)
    head.load_state_dict(selected_state); head.eval()
    with torch.no_grad():
        probabilities = torch.sigmoid(head(torch.tensor(test_x, dtype=torch.float32, device=device))).cpu().numpy()
    thresholds = np.array([selected["thresholds"][label] for label in labels])
    pred = probabilities >= thresholds; truth = y[grouped["test"]].astype(bool)
    predictions = []
    for index, row in enumerate(test_rows):
        expected = [label for col, label in enumerate(labels) if truth[index, col]]
        predicted = [label for col, label in enumerate(labels) if pred[index, col]]
        predictions.append({"case_id": row["id"], "base_scenario_id": row["base_scenario_id"], "split": row["split"],
                            "language": row["language"], "variant_type": row.get("variant_type", "base"),
                            "expected_labels": expected, "predicted_labels": predicted,
                            "scores": {label: float(probabilities[index, col]) for col, label in enumerate(labels)},
                            "exact_match": expected == predicted})
    json_dump(OUT / "frozen_test_predictions.json", predictions)
    clean = np.array([row.get("variant_type") != "asr_corrupted" for row in test_rows])
    asr = ~clean
    metrics = {"clean_test": metric_bundle(pred[clean], truth[clean], labels),
               "asr_test": metric_bundle(pred[asr], truth[asr], labels) if asr.any() else None,
               "all_test_records": metric_bundle(pred, truth, labels),
               "safety_clean": safety([row for row, keep in zip(test_rows, clean) if keep], pred[clean], truth[clean], labels),
               "by_language": {}}
    for language in ("ru", "ro", "en"):
        mask = clean & np.array([row["language"] == language for row in test_rows])
        metrics["by_language"][language] = metric_bundle(pred[mask], truth[mask], labels) if mask.any() else None
    mixed = clean & np.array([row["language"].startswith("mixed-") for row in test_rows])
    metrics["by_language"]["mixed"] = metric_bundle(pred[mixed], truth[mixed], labels) if mixed.any() else None
    json_dump(OUT / "final_test_metrics.json", metrics)
    errors = []
    for item in predictions:
        expected, predicted = set(item["expected_labels"]), set(item["predicted_labels"])
        if expected != predicted:
            category = "ASR corruption" if item["variant_type"] == "asr_corrupted" else (
                "protective speech" if "PROTECTIVE_ADVICE" in expected else
                "manipulation-only" if expected & {"ISOLATION", "DISCOURAGE_VERIFICATION", "KEEP_CALL_ACTIVE"} and not expected & ACTION else
                "semantic label mismatch")
            errors.append({**item, "false_negatives": sorted(expected - predicted), "false_positives": sorted(predicted - expected),
                           "failure_category": category})
    json_dump(OUT / "error_analysis.json", {"error_count": len(errors), "errors": errors})
    latency_rows = train_rows[:10] + val_rows[:10] + test_rows[:10]
    warm = []
    for row in latency_rows:
        before = time.perf_counter(); encode(encoder, tokenizer, [row], device, batch_size=1); warm.append((time.perf_counter() - before) * 1000)
    latency = {"model_load_seconds": model_load_seconds, "warm_inference_ms": {"p50": float(np.percentile(warm, 50)),
               "p95": float(np.percentile(warm, 95)), "max": float(max(warm))}, "samples": len(warm),
               "process_rss_mb": psutil.Process().memory_info().rss / 1048576, "device": device}
    json_dump(OUT / "latency_benchmark.json", latency)
    metadata = {"timestamp_utc": datetime.now(timezone.utc).isoformat(), "python": sys.version, "torch": torch.__version__,
                "transformers": transformers_version, "platform": platform.platform(), "pid": os.getpid(),
                "duration_seconds": time.perf_counter() - started, "checkpoint": str(checkpoint)}
    json_dump(OUT / "run_metadata.json", metadata)
    final = {"config": config, "selected_validation_run": selected, "metrics": metrics, "latency": latency,
             "error_count": len(errors), "artifacts": {name: str(OUT / name) for name in (
                 "training_config.json", "validation_selection.json", "selected_head.pt", "frozen_test_predictions.json",
                 "final_test_metrics.json", "error_analysis.json", "latency_benchmark.json", "run_metadata.json")}}
    json_dump(REPORT, final)
    print(json.dumps({"report": str(REPORT), "checkpoint": str(checkpoint), "duration_seconds": metadata["duration_seconds"],
                      "selected_seed": selected["seed"], "test_records": len(test_rows)}, indent=2))


if __name__ == "__main__":
    main()
