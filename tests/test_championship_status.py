import json
import tempfile
import unittest
from pathlib import Path

from scripts.championship_status import bounded_status_lines, make_status, pid_is_alive, write_runtime_status


class ChampionshipStatusTests(unittest.TestCase):
    def test_status_has_required_fit_coordinates_and_logs(self):
        status = make_status(
            "SCREENING",
            {"candidate": "e5_base", "revision": "abc", "depth": 2, "fold": 1, "seed": 17, "epoch": 3},
            pid=123,
            stdout_log="out.log",
            stderr_log="err.log",
        )
        self.assertTrue({"pid", "phase", "candidate", "revision", "depth", "fold", "seed", "epoch", "stdout_log", "stderr_log"} <= status.keys())

    def test_runtime_status_is_atomic_and_dead_pid_is_reported(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "runtime_status.json"
            write_runtime_status(path, make_status("FAILED", pid=999_999_999, stdout_log="out", stderr_log="err"))
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["phase"], "FAILED")
            self.assertFalse(pid_is_alive(999_999_999))
            self.assertEqual(list(Path(temporary).glob("*.tmp")), [])

    def test_bounded_status_lines_include_only_requested_tail(self):
        status = make_status("SCREENING", pid=1, stdout_log="out", stderr_log="err", fit_total=24, fit_completed=2)
        lines = bounded_status_lines(status, stdout_lines=[str(n) for n in range(8)], stderr_lines=["error"], limit=3)
        self.assertIn("phase=SCREENING", lines[0])
        self.assertEqual(lines[-4:-1], ["5", "6", "7"])
        self.assertEqual(lines[-1], "error")


if __name__ == "__main__":
    unittest.main()
