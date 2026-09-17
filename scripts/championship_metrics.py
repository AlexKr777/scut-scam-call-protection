"""TRAIN-only OOF metrics and safety-first championship selection."""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable

import numpy as np


ACTION_THRESHOLDS = (.20, .30, .40, .50, .60, .70, .80)
SEMANTIC_THRESHOLDS = (.35, .45, .50, .60, .70)


def confusion(prediction: np.ndarray, truth: np.ndarray) -> dict[str, int | float]:
    prediction, truth = np.asarray(prediction, dtype=bool), np.asarray(truth, dtype=bool)
    tp = int(np.sum(prediction & truth)); fp = int(np.sum(prediction & ~truth))
    tn = int(np.sum(~prediction & ~truth)); fn = int(np.sum(~prediction & truth))
    return {"tp": tp, "fp": fp, "tn": tn, "fn": fn,
            "recall": tp / (tp + fn) if tp + fn else 0.0,
            "precision": tp / (tp + fp) if tp + fp else 0.0,
            "fpr": fp / (fp + tn) if fp + tn else 0.0}


def _f1(conf: dict[str, int | float]) -> float:
    precision, recall = float(conf["precision"]), float(conf["recall"])
    return 2 * precision * recall / (precision + recall) if precision + recall else 0.0


def select_global_semantic_threshold(probabilities: np.ndarray, truth: np.ndarray, labels: list[str]) -> float:
    probabilities, truth = np.asarray(probabilities), np.asarray(truth, dtype=bool)
    meaningful = np.sum(truth, axis=0) >= 5
    if not np.any(meaningful):
        return .50
    scored = []
    for threshold in SEMANTIC_THRESHOLDS:
        scores = [confusion(probabilities[:, index] >= threshold, truth[:, index]) for index in np.flatnonzero(meaningful)]
        scored.append((float(np.mean([_f1(score) for score in scores])), float(np.mean([score["precision"] for score in scores])), threshold))
    return max(scored, key=lambda item: (item[0], item[1], item[2]))[2]


def select_thresholds(probabilities: np.ndarray, truth: np.ndarray, labels: list[str]) -> dict[str, float]:
    global_threshold = select_global_semantic_threshold(probabilities, truth, labels)
    chosen = {"__global__": global_threshold}
    for index, label in enumerate(labels):
        if int(np.sum(truth[:, index])) < 5:
            chosen[label] = global_threshold
            continue
        options = []
        for threshold in SEMANTIC_THRESHOLDS:
            metric = confusion(probabilities[:, index] >= threshold, truth[:, index])
            options.append((_f1(metric), float(metric["precision"]), threshold))
        chosen[label] = max(options, key=lambda item: (item[0], item[1], item[2]))[2]
    return chosen


def _safe_rates(prediction: np.ndarray, truth: np.ndarray, rows: list[dict[str, Any]]) -> dict[str, dict[str, int | float]]:
    result = {}
    for kind in ("protective", "legitimate"):
        indices = np.array([row.get("kind") == kind for row in rows])
        result[kind] = confusion(prediction[indices], truth[indices]) if np.any(indices) else confusion(np.array([], dtype=bool), np.array([], dtype=bool))
    manipulation = np.array([row.get("kind") == "dangerous" and not row.get("action_target", bool(truth[index])) for index, row in enumerate(rows)])
    result["manipulation_only"] = confusion(prediction[manipulation], truth[manipulation]) if np.any(manipulation) else confusion(np.array([], dtype=bool), np.array([], dtype=bool))
    return result


def safety_qualification(prediction: np.ndarray, truth: np.ndarray, rows: list[dict[str, Any]]) -> dict[str, Any]:
    prediction, truth = np.asarray(prediction, dtype=bool), np.asarray(truth, dtype=bool)
    overall = confusion(prediction, truth); safe = _safe_rates(prediction, truth, rows)
    by_fold: dict[str, dict[str, Any]] = {}
    catastrophic_folds = []
    for fold in sorted({row.get("fold") for row in rows}):
        indices = np.array([row.get("fold") == fold for row in rows]); metrics = confusion(prediction[indices], truth[indices])
        safe_fold = _safe_rates(prediction[indices], truth[indices], [row for row, include in zip(rows, indices) if include])
        catastrophic = (int(np.sum(truth[indices])) >= 5 and metrics["recall"] < .60) or any(
            value["fp"] + value["tn"] >= 5 and value["fpr"] > .60 for value in safe_fold.values())
        by_fold[str(fold)] = {"action": metrics, "safe": safe_fold, "catastrophic": catastrophic}
        if catastrophic: catastrophic_folds.append(fold)
    languages: dict[str, dict[str, Any]] = {}
    catastrophic_languages = []
    for language in sorted({str(row.get("language", "unknown")) for row in rows}):
        indices = np.array([str(row.get("language", "unknown")) == language for row in rows])
        subset_rows = [row for row, include in zip(rows, indices) if include]
        m = confusion(prediction[indices], truth[indices]); sf = _safe_rates(prediction[indices], truth[indices], subset_rows)
        sufficient_danger = int(np.sum(indices)) >= 5 and int(np.sum(truth[indices])) >= 3
        sufficient_safe = any(value["fp"] + value["tn"] >= 5 for value in sf.values())
        catastrophic = (sufficient_danger and m["recall"] < .60) or any(value["fp"] + value["tn"] >= 5 and value["fpr"] > .60 for value in sf.values())
        status = "CATASTROPHIC" if catastrophic else "ASSESSED" if sufficient_danger or sufficient_safe else "INSUFFICIENT_SUPPORT"
        languages[language] = {"status": status, "action": m, "safe": sf}
        if catastrophic: catastrophic_languages.append(language)
    qualified = (overall["recall"] >= .85 and safe["protective"]["fpr"] <= .15 and safe["legitimate"]["fpr"] <= .15
                 and safe["manipulation_only"]["fpr"] <= .20 and not catastrophic_folds and not catastrophic_languages)
    assessed_recalls = [value["action"]["recall"] for value in by_fold.values() if value["action"]["tp"] + value["action"]["fn"] >= 5]
    return {"qualified": qualified, "overall": overall, "safe": safe, "folds": by_fold, "languages": languages,
            "catastrophic_folds": catastrophic_folds, "catastrophic_languages": catastrophic_languages,
            "worst_fold_recall": min(assessed_recalls) if assessed_recalls else 0.0, "overall_recall": overall["recall"],
            "safe_fp_max": max(float(value["fpr"]) for value in safe.values()), "precision": overall["precision"]}


def select_action_threshold(probabilities: np.ndarray, truth: np.ndarray, rows: list[dict[str, Any]]) -> dict[str, Any]:
    results = []
    for threshold in ACTION_THRESHOLDS:
        qualification = safety_qualification(np.asarray(probabilities) >= threshold, truth, rows)
        results.append({"threshold": threshold, "qualified": qualification["qualified"], "qualification": qualification,
                        "f1": _f1(qualification["overall"]), "precision": qualification["overall"]["precision"]})
    eligible = [result for result in results if result["qualified"]]
    if eligible:
        return max(eligible, key=lambda item: (item["f1"], item["precision"], item["threshold"]))
    return max(results, key=lambda item: (item["qualification"]["overall_recall"] - item["qualification"]["safe_fp_max"], item["f1"], item["threshold"]))


def ranking_tuple(candidate: dict[str, Any]) -> tuple[Any, ...]:
    q = candidate.get("qualification", {})
    return (bool(q.get("qualified", False)), float(q.get("worst_fold_recall", 0)), float(q.get("overall_recall", 0)),
            -float(q.get("safe_fp_max", 1)), float(q.get("precision", 0)), float(candidate.get("semantic_macro_f1", 0)),
            float(candidate.get("semantic_micro_f1", 0)), float(candidate.get("minimal_pair_score", 0)),
            float(candidate.get("language_robustness", 0)), float(candidate.get("stability", 0)),
            -float(candidate.get("deployment_cost", 0)))


def rank_candidates(candidates: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered = sorted((dict(candidate) for candidate in candidates), key=lambda candidate: (ranking_tuple(candidate), str(candidate.get("id", ""))), reverse=True)
    for position, candidate in enumerate(ordered, start=1):
        candidate["lexicographic_tuple"] = list(ranking_tuple(candidate)); candidate["rank"] = position
    return ordered


def select_median_seed(seed_summaries: Iterable[dict[str, Any]]) -> dict[str, Any]:
    summaries = list(seed_summaries)
    if {summary.get("seed") for summary in summaries} != {17, 29, 43}:
        raise ValueError("final seed selection requires exactly seeds 17, 29, and 43")
    ranked = sorted(summaries, key=lambda summary: (ranking_tuple(summary), -int(summary["seed"])), reverse=True)
    selected = dict(ranked[1])
    selected["selection_reason"] = "middle rank under the precommitted safety-first lexicographic hierarchy; exact ties use ascending numeric seed"
    selected["seed_ranking"] = [summary["seed"] for summary in ranked]
    return selected

def semantic_metrics(prediction: np.ndarray, truth: np.ndarray, labels: list[str]) -> dict[str, Any]:
    prediction=np.asarray(prediction,dtype=bool); truth=np.asarray(truth,dtype=bool); per={}; scores=[]
    for index,label in enumerate(labels):
        c=confusion(prediction[:,index],truth[:,index]); c['f1']=_f1(c);c['support']=int(truth[:,index].sum());per[label]=c;scores.append(c)
    micro=confusion(prediction.reshape(-1),truth.reshape(-1));micro['f1']=_f1(micro)
    macro={key:float(np.mean([x[key] for x in scores])) for key in ('precision','recall','f1')} if scores else {'precision':0.,'recall':0.,'f1':0.}
    return {'micro':micro,'macro':macro,'exact_match':float(np.all(prediction==truth,axis=1).mean()) if len(prediction) else 0.,'per_label':per}
