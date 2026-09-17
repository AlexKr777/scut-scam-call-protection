"""Evidence-preserving summaries and finalist deployment-cost reporting.

This module performs no model loading. Its inputs are persisted TRAIN-OOF
evidence or measured finalist metadata, keeping reporting incapable of
accidentally reading validation, TEST, or fresh-holdout data for selection.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable, Mapping

import numpy as np

from scripts.championship_metrics import confusion, semantic_metrics


LAPTOP_CAVEAT = "FINAL TUF F17 LATENCY MUST STILL BE BENCHMARKED ON THE ACTUAL DEMO LAPTOP."
_FIT_STATES = ("COMPLETED", "PENDING", "TECHNICALLY_EXCLUDED")
_CPU_BUCKETS = ("short", "medium", "long_384")


def _fit_state(record: Mapping[str, Any] | None) -> str:
    if record is None:
        return "PENDING"
    state = str(record.get("status", "PENDING"))
    if state not in _FIT_STATES:
        raise ValueError(f"unknown championship fit state: {state}")
    return state


def build_screening_summary(
    expected_fits: list[dict[str, Any]],
    completed: Iterable[dict[str, Any] | None],
    ranking: list[dict[str, Any]],
    *,
    important_labels: Iterable[str] = (),
    oof_breakdowns: Mapping[str, Any] | None = None,
    exclusions: Iterable[dict[str, Any]] = (),
    protocol_sha256: str | None = None,
    data_hashes: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Enumerate every frozen Phase-1 fit, including incomplete states."""
    expected_ids = [str(fit["fit_id"]) for fit in expected_fits]
    if len(expected_ids) != len(set(expected_ids)):
        raise ValueError("duplicate expected fit ID in frozen screening matrix")
    records = [record for record in completed if record is not None]
    by_id = {str(record["fit_id"]): record for record in records}
    if len(by_id) != len(records) or not set(by_id).issubset(expected_ids):
        raise ValueError("completed fit records do not match the frozen screening matrix")

    entries = []
    states = {state: [] for state in _FIT_STATES}
    for fit in expected_fits:
        fit_id = str(fit["fit_id"])
        record = by_id.get(fit_id)
        state = _fit_state(record)
        states[state].append(fit_id)
        entries.append({
            "fit_id": fit_id,
            "candidate": fit.get("candidate"),
            "depth": fit.get("depth"),
            "fold": fit.get("fold"),
            "seed": fit.get("seed"),
            "status": state,
            "oof_complete": bool(record and record.get("oof_complete")),
            "oof_npz": record.get("oof_npz") if record else None,
            "npz_sha256": record.get("npz_sha256") if record else None,
        })
    finalists = [item["id"] for item in ranking[:2] if item.get("id")]
    report: dict[str, Any] = {
        "expected_fits": entries,
        "fit_states": states,
        "completed_count": len(states["COMPLETED"]),
        "expected_count": len(expected_fits),
        "ranking": ranking,
        "finalists": finalists,
        "important_labels": sorted(set(important_labels)),
        "selection_policy": "safety-first lexicographic; deployment cost last",
        "technical_exclusions": list(exclusions),
    }
    if oof_breakdowns is not None:
        report["oof_breakdowns"] = dict(oof_breakdowns)
    if protocol_sha256 is not None:
        report["protocol_sha256"] = protocol_sha256
    if data_hashes is not None:
        report["data_hashes"] = dict(data_hashes)
    return report


def build_stability_summary(
    seed_folds: Iterable[dict[str, Any]],
    *,
    aggregates: Mapping[str, Any] | None = None,
    protocol_sha256: str | None = None,
) -> dict[str, Any]:
    """Record every stability coordinate and the already-computed seed evidence."""
    folds = [dict(fit) for fit in seed_folds]
    report: dict[str, Any] = {
        "seed_folds": folds,
        "expected_count": len(folds),
        "completed_count": sum(_fit_state(fit) == "COMPLETED" for fit in folds),
        "aggregates": dict(aggregates or {}),
    }
    if protocol_sha256 is not None:
        report["protocol_sha256"] = protocol_sha256
    return report


def _is_asr(row: Mapping[str, Any]) -> bool:
    value = str(row.get("variant_type", row.get("variant", ""))).lower()
    return bool(row.get("is_asr")) or "asr" in value


def _pair_id(row: Mapping[str, Any]) -> str | None:
    for key in ("minimal_pair_id", "pair_id", "minimal_pair_group"):
        value = row.get(key)
        if value is not None:
            return str(value)
    return None


def _slice_metrics(action_prediction, action_targets, semantic_prediction, semantic_targets, labels, indices):
    return {
        "record_count": int(np.sum(indices)),
        "action": confusion(action_prediction[indices], action_targets[indices]),
        "semantic": semantic_metrics(semantic_prediction[indices], semantic_targets[indices], labels),
    }


def build_oof_breakdowns(
    *, action_probabilities: np.ndarray, action_targets: np.ndarray,
    semantic_probabilities: np.ndarray, semantic_targets: np.ndarray,
    labels: list[str], rows: list[dict[str, Any]], action_threshold: float,
    semantic_thresholds: Mapping[str, float], important_labels: Iterable[str] = (),
) -> dict[str, Any]:
    """Compute report-only OOF strata from a single candidate/depth pool."""
    action_probabilities = np.asarray(action_probabilities).reshape(-1)
    action_targets = np.asarray(action_targets, dtype=bool).reshape(-1)
    semantic_probabilities = np.asarray(semantic_probabilities)
    semantic_targets = np.asarray(semantic_targets, dtype=bool)
    if len(rows) != len(action_targets) or semantic_probabilities.shape != semantic_targets.shape:
        raise ValueError("OOF arrays and reporting rows have incompatible shapes")
    if semantic_probabilities.ndim != 2 or semantic_probabilities.shape[1] != len(labels):
        raise ValueError("semantic OOF label dimension does not match labels")
    action_prediction = action_probabilities >= action_threshold
    thresholds = np.array([semantic_thresholds.get(label, semantic_thresholds["__global__"]) for label in labels])
    semantic_prediction = semantic_probabilities >= thresholds
    language = {}
    for value in sorted({str(row.get("language", "unknown")) for row in rows}):
        indices = np.array([str(row.get("language", "unknown")) == value for row in rows])
        language[value] = _slice_metrics(action_prediction, action_targets, semantic_prediction, semantic_targets, labels, indices)
    asr_vs_clean = {}
    for name, desired in (("clean", False), ("asr", True)):
        indices = np.array([_is_asr(row) == desired for row in rows])
        asr_vs_clean[name] = _slice_metrics(action_prediction, action_targets, semantic_prediction, semantic_targets, labels, indices)
    groups: dict[str, list[int]] = defaultdict(list)
    for index, row in enumerate(rows):
        pair = _pair_id(row)
        if pair is not None:
            groups[pair].append(index)
    minimal_pairs = {
        pair: {
            "record_ids": [str(rows[index].get("id", index)) for index in indices],
            **_slice_metrics(action_prediction, action_targets, semantic_prediction, semantic_targets, labels, np.isin(np.arange(len(rows)), indices)),
        }
        for pair, indices in sorted(groups.items())
    }
    per_label = semantic_metrics(semantic_prediction, semantic_targets, labels)["per_label"]
    selected_labels = list(important_labels) or labels
    return {
        "language": language,
        "asr_vs_clean": asr_vs_clean,
        "minimal_pairs": minimal_pairs,
        "important_labels": {label: per_label[label] for label in selected_labels if label in per_label},
    }


def benchmark_finalists(finalists: list[dict[str, Any]]) -> dict[str, Any]:
    """Normalize measured deployment evidence; never manufacture a measurement."""
    normalized = []
    for finalist in finalists:
        cpu = dict(finalist.get("cpu_proxy_ms") or {})
        normalized.append({
            "id": finalist.get("id"), "total_parameters": finalist.get("total_parameters"),
            "active_parameters": finalist.get("active_parameters"), "checkpoint_bytes": finalist.get("checkpoint_bytes"),
            "checkpoint_sha256": finalist.get("checkpoint_sha256"), "peak_training_vram": finalist.get("peak_training_vram"),
            "gpu_inference_ms": {"p50": finalist.get("gpu_p50_ms"), "p95": finalist.get("gpu_p95_ms")},
            "inference_memory": finalist.get("inference_memory"),
            "cpu_proxy_ms": {bucket: cpu.get(bucket) for bucket in _CPU_BUCKETS},
        })
    representative = normalized[0]["cpu_proxy_ms"] if len(normalized) == 1 else {bucket: None for bucket in _CPU_BUCKETS}
    return {"finalists": normalized, "cpu_proxy_ms": representative, "caveat": LAPTOP_CAVEAT,
            "measurement_scope": "per-finalist values are preserved in finalists[].cpu_proxy_ms"}


def _mark_unassessed_validation(value: Any) -> Any:
    if isinstance(value, dict):
        updated = {key: _mark_unassessed_validation(item) for key, item in value.items()}
        if updated.get("support") == 0:
            updated["status"] = "UNASSESSED_ON_VALIDATION"
        return updated
    if isinstance(value, list):
        return [_mark_unassessed_validation(item) for item in value]
    return value


def build_champion_manifest(champion: dict[str, Any], runner_up: dict[str, Any] | None, validation: dict[str, Any]) -> dict[str, Any]:
    """Create the final confirmatory-only manifest without re-ranking anything."""
    winner = dict(champion)
    second = dict(runner_up) if runner_up is not None else None
    if second is not None:
        second.setdefault("loss_reason", "lower safety-first lexicographic ranking")
    return {
        "champion": winner, "runner_up": second, "validation": _mark_unassessed_validation(validation),
        "validation_is_confirmatory_only": True, "checkpoint_sha256": winner.get("checkpoint_sha256"),
        "thresholds": winner.get("thresholds", winner.get("selection", {}).get("thresholds")),
        "reproducibility": {key: winner[key] for key in ("protocol_sha256", "revision", "data_hashes") if key in winner},
    }
