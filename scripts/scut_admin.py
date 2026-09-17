"""Small trusted operator entrypoint for SCUT control-plane administration."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.control_plane import ControlPlaneClient


def main() -> int:
    parser = argparse.ArgumentParser(description="SCUT local operator helper")
    parser.add_argument("command", choices=("release-controller",))
    args = parser.parse_args()
    result = ControlPlaneClient().release_controller()
    if not result:
        print("SCUT controller release was not accepted; verify local control-plane configuration.")
        return 1
    print("SCUT state: NO_CONTROLLER")
    print("Previous controller released." if result["released"] else "No controller was assigned; state was already NO_CONTROLLER.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
