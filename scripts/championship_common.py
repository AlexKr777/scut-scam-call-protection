"""Safety primitives for the isolated SCUT Brain Championship.

This module deliberately opens only the two immutable Stage-1 sources.  In
particular, it has no fresh-holdout or historical-TEST path resolution.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any


EXPECTED_HASHES = {
    "v3": "A12362265C8FFD39C7436E405C23844FE4312874DB08D76AE2D193FED25B5D96",
    "extension": "083947CF8F94EFA92AD6420C08AFE6CA09D1B9C0896E945FF9E091EC9F6FE8DC",
    # This value is retained as protocol metadata only.  Championship code
    # must never open fresh-holdout content, even to calculate this hash.
    "blueprint": "414D44D0A58BDFBDE0B51A2C3ACB4644AF11621A3783965E257FF8AB17B04D22",
}

_SOURCE_FILES = {
    "v3": Path("experiments") / "semantic_corpus_v3.json",
    "extension": Path("experiments") / "semantic_training_extension_v1.json",
}
_BLUEPRINT_FILE = Path("reports") / "scut_semantic_brain_v2" / "fresh_holdout_blueprint.json"
_CACHE_VARIABLES = (
    "HF_HOME",
    "HF_HUB_CACHE",
    "TRANSFORMERS_CACHE",
    "XDG_CACHE_HOME",
    "TEMP",
    "TMP",
    "PIP_CACHE_DIR",
)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def configure_ml_caches(root: Path) -> dict[str, Path]:
    """Set every ML cache/temp environment variable under an explicit cache root."""
    root = Path(root)

    paths = {
        "HF_HOME": root / "hf-cache",
        "HF_HUB_CACHE": root / "hf-cache",
        "TRANSFORMERS_CACHE": root / "hf-cache",
        "XDG_CACHE_HOME": root / ".ml-tmp",
        "TEMP": root / ".ml-tmp",
        "TMP": root / ".ml-tmp",
        "PIP_CACHE_DIR": root / ".pip-cache",
    }
    for path in set(paths.values()):
        path.mkdir(parents=True, exist_ok=True)
    for variable, path in paths.items():
        rendered = str(path)
        os.environ[variable] = rendered
    return paths


def assert_integrity(root: Path) -> dict[str, str]:
    """Validate source bytes plus the non-dialogue fresh-holdout blueprint hash.

    The blueprint is an immutable generation manifest, not fresh benchmark
    dialogue content.  It is hash-checked only to enforce the approved
    integrity contract and is never parsed, enumerated, or emitted.
    """
    root = Path(root)
    observed: dict[str, str] = {}
    for name, relative_path in _SOURCE_FILES.items():
        path = root / relative_path
        if not path.is_file():
            raise FileNotFoundError(path)
        observed[name] = _sha256_file(path)
        if observed[name] != EXPECTED_HASHES[name]:
            raise RuntimeError(
                f"immutable championship source hash mismatch for {relative_path}: "
                f"expected {EXPECTED_HASHES[name]}, got {observed[name]}"
            )
    blueprint_path = root / _BLUEPRINT_FILE
    if not blueprint_path.is_file():
        raise FileNotFoundError(blueprint_path)
    observed["blueprint"] = _sha256_file(blueprint_path)
    if observed["blueprint"] != EXPECTED_HASHES["blueprint"]:
        raise RuntimeError(
            "immutable fresh-holdout blueprint hash mismatch: "
            f"expected {EXPECTED_HASHES['blueprint']}, got {observed['blueprint']}"
        )
    return observed


def _load_allowed_source(path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict) or set(document) != {"bases", "variants"}:
        raise ValueError(f"invalid Stage-1 source shape: {path}")
    bases, variants = document["bases"], document["variants"]
    if not isinstance(bases, list) or not isinstance(variants, list):
        raise ValueError(f"invalid Stage-1 collections: {path}")
    if not all(isinstance(row, dict) for row in [*bases, *variants]):
        raise ValueError(f"non-object record in Stage-1 source: {path}")
    return bases, variants


def load_train_validation_records(
    root: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str], dict[str, list[str]]]:
    """Return only TRAIN/VALIDATION records with base-derived kinds and lineage."""
    root = Path(root)
    assert_integrity(root)
    train: list[dict[str, Any]] = []
    validation: list[dict[str, Any]] = []
    all_labels: set[str] = set()

    for relative_path in _SOURCE_FILES.values():
        bases, variants = _load_allowed_source(root / relative_path)
        base_kinds = {
            row.get("base_scenario_id"): row.get("kind")
            for row in bases
            if isinstance(row.get("base_scenario_id"), str) and isinstance(row.get("kind"), str)
        }
        for raw_row in [*bases, *variants]:
            split = raw_row.get("split")
            if split not in {"train", "validation"}:
                continue
            group = raw_row.get("base_scenario_id")
            labels = raw_row.get("labels")
            if not isinstance(group, str) or not isinstance(labels, list) or not all(isinstance(label, str) for label in labels):
                raise ValueError(f"invalid allowed record metadata: {raw_row.get('id', '<unknown>')}")
            kind = base_kinds.get(group)
            if kind not in {"dangerous", "protective", "legitimate"}:
                raise ValueError(f"missing base-derived kind for {raw_row.get('id', '<unknown>')}")
            row = dict(raw_row)
            row["kind"] = kind
            all_labels.update(labels)
            (train if split == "train" else validation).append(row)

    train_groups = sorted({row["base_scenario_id"] for row in train})
    validation_groups = sorted({row["base_scenario_id"] for row in validation})
    if set(train_groups) & set(validation_groups):
        raise RuntimeError("base_scenario_id crosses TRAIN/VALIDATION boundary")
    return train, validation, sorted(all_labels), {
        "train_groups": train_groups,
        "validation_groups": validation_groups,
    }


def load_train_records(root: Path) -> tuple[list[dict[str, Any]], list[str], dict[str, list[str]]]:
    """Championship-safe loader: it never materializes observed validation rows."""
    root = Path(root); assert_integrity(root)
    train: list[dict[str, Any]] = []; labels: set[str] = set()
    for relative_path in _SOURCE_FILES.values():
        bases, variants = _load_allowed_source(root / relative_path)
        kinds = {x.get("base_scenario_id"): x.get("kind") for x in bases}
        for raw in [*bases, *variants]:
            if raw.get("split") != "train": continue
            group, row_labels = raw.get("base_scenario_id"), raw.get("labels")
            if not isinstance(group, str) or not isinstance(row_labels, list): raise ValueError("invalid TRAIN record")
            kind=kinds.get(group)
            if kind not in {"dangerous", "protective", "legitimate"}: raise ValueError("invalid TRAIN kind")
            row=dict(raw); row["kind"]=kind; train.append(row); labels.update(row_labels)
    return train, sorted(labels), {"train_groups": sorted({x["base_scenario_id"] for x in train}), "validation_status": "OBSERVED_VALIDATION"}


def write_observed_validation_status(directory: Path) -> Path:
    path=Path(directory)/"validation_status.json"
    atomic_json_write(path, {"OLD_CHAMPIONSHIP_STATUS":"NO_QUALIFIED_CHAMPION", "validation_status":"OBSERVED_VALIDATION", "championship_policy":"DO_NOT_LOAD_OR_RERUN", "unseen_confirmation_status":"UNSEEN_CONFIRMATION_NOT_YET_AVAILABLE"})
    return path


def atomic_json_write(path: Path, value: dict[str, Any]) -> None:
    """Atomically replace a JSON artifact using a temporary sibling file."""
    path = Path(path)
    if not path.parent.is_dir():
        raise FileNotFoundError(path.parent)
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False
        ) as temporary:
            temporary_name = temporary.name
            json.dump(value, temporary, ensure_ascii=False, indent=2, sort_keys=True)
            temporary.write("\n")
            temporary.flush()
            os.fsync(temporary.fileno())
        Path(temporary_name).replace(path)
    finally:
        if temporary_name is not None:
            temporary_path = Path(temporary_name)
            if temporary_path.exists():
                temporary_path.unlink()


def write_status(path: Path, status: dict[str, Any]) -> None:
    atomic_json_write(path, status)


def read_completed_fit(path: Path) -> dict[str, Any] | None:
    """Return a completed fit record, otherwise None without guessing its state."""
    if not Path(path).is_file():
        return None
    record = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(record, dict) or record.get("status") != "COMPLETED":
        return None
    return record
