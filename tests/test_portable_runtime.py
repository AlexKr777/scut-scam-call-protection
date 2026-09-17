import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.constants import local_root, runtime_paths
from backend.nomic_deployment_v1 import nomic_cache_dir


class PortableRuntimeTests(unittest.TestCase):
    def test_local_root_uses_explicit_writable_runtime_directory(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {"SCUT_LOCAL_DIR": directory}, clear=False
        ):
            self.assertEqual(local_root(), Path(directory).resolve())

    def test_local_root_defaults_beside_source_for_development(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(local_root(), Path(__file__).resolve().parents[1] / ".local")

    def test_runtime_paths_keep_all_mutable_data_under_explicit_directory(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {"SCUT_LOCAL_DIR": directory}, clear=False
        ):
            local, logs, diagnostics = runtime_paths()
            self.assertEqual((local, logs, diagnostics), (
                Path(directory).resolve(),
                Path(directory).resolve() / "logs",
                Path(directory).resolve() / "diagnostics",
            ))

    def test_nomic_cache_defaults_under_portable_local_runtime(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {"SCUT_LOCAL_DIR": directory}, clear=False
        ):
            self.assertEqual(nomic_cache_dir(), Path(directory).resolve() / "nomic-hf-cache")
