import json
import os
import tempfile
import unittest
from pathlib import Path

from scripts.championship_common import (
    EXPECTED_HASHES,
    assert_integrity,
    atomic_json_write,
    configure_ml_caches,
    load_train_validation_records,
    write_status,
)


ROOT = Path(__file__).resolve().parents[1]


class ChampionshipCommonTests(unittest.TestCase):
    def test_integrity_accepts_the_two_allowed_immutable_sources(self):
        observed = assert_integrity(ROOT)

        self.assertEqual(observed["v3"], "A12362265C8FFD39C7436E405C23844FE4312874DB08D76AE2D193FED25B5D96")
        self.assertEqual(observed["extension"], "083947CF8F94EFA92AD6420C08AFE6CA09D1B9C0896E945FF9E091EC9F6FE8DC")
        self.assertEqual(EXPECTED_HASHES["blueprint"], "414D44D0A58BDFBDE0B51A2C3ACB4644AF11621A3783965E257FF8AB17B04D22")

    def test_cache_policy_sets_every_ml_cache_under_the_requested_portable_root(self):
        previous = {key: os.environ.get(key) for key in (
            "HF_HOME", "HF_HUB_CACHE", "TRANSFORMERS_CACHE", "XDG_CACHE_HOME",
            "TEMP", "TMP", "PIP_CACHE_DIR",
        )}
        try:
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary) / "ml-cache"
                paths = configure_ml_caches(root)
            self.assertEqual(
                set(paths),
                {"HF_HOME", "HF_HUB_CACHE", "TRANSFORMERS_CACHE", "XDG_CACHE_HOME", "TEMP", "TMP", "PIP_CACHE_DIR"},
            )
            self.assertTrue(all(value.is_relative_to(root) for value in paths.values()))
            self.assertEqual(os.environ["HF_HOME"], str(root / "hf-cache"))
            self.assertEqual(os.environ["TEMP"], str(root / ".ml-tmp"))
        finally:
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    def test_loader_emits_only_train_and_validation_without_group_overlap(self):
        train, validation, labels, lineage = load_train_validation_records(ROOT)

        self.assertEqual(len(train), 292)
        self.assertEqual(len(validation), 31)
        self.assertTrue(labels)
        self.assertTrue(all(row["split"] == "train" for row in train))
        self.assertTrue(all(row["split"] == "validation" for row in validation))
        self.assertFalse(set(lineage["train_groups"]) & set(lineage["validation_groups"]))

    def test_atomic_json_write_replaces_complete_status_document(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "runtime_status.json"
            path.write_text('{"phase":"OLD"}', encoding="utf-8")

            write_status(path, {"phase": "SCREENING", "fit": "e5_base-top_2-fold_0-seed_17"})

            self.assertEqual(
                json.loads(path.read_text(encoding="utf-8")),
                {"fit": "e5_base-top_2-fold_0-seed_17", "phase": "SCREENING"},
            )
            self.assertEqual(list(Path(temporary).glob("*.tmp")), [])

    def test_atomic_json_write_rejects_a_path_without_parent_directory(self):
        with self.assertRaises(FileNotFoundError):
            atomic_json_write(Path("does-not-exist") / "status.json", {"phase": "FAILED"})


if __name__ == "__main__":
    unittest.main()
