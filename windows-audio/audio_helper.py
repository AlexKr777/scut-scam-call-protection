"""Explicit Windows Phone Link audio capture diagnostic."""
from __future__ import annotations

import argparse
import array
import json
import math
import subprocess
import sys
import time
import wave
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
SILENCE_RMS = 120.0


def json_safe(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    return str(value)


def package_processes() -> list[dict[str, Any]]:
    """Discover running AppX processes by package path, never by process name."""
    try:
        import psutil
        command = "Get-AppxPackage | Select-Object Name,PackageFullName,InstallLocation | ConvertTo-Json -Compress"
        raw = subprocess.run(["powershell", "-NoProfile", "-Command", command], capture_output=True, text=True, timeout=10).stdout
        packages = json.loads(raw) if raw.strip() else []
        if isinstance(packages, dict):
            packages = [packages]
        locations = [(str(item.get("InstallLocation", "")).lower(), item) for item in packages if item.get("InstallLocation")]
        found = []
        for process in psutil.process_iter(["pid", "exe"]):
            executable = str(process.info.get("exe") or "")
            package = next((item for location, item in locations if location and executable.lower().startswith(location)), None)
            if package:
                found.append({"pid": process.info["pid"], "executable": executable, "package": package.get("Name"), "packageFullName": package.get("PackageFullName")})
        return found
    except Exception as error:
        return [{"discoveryError": type(error).__name__, "detail": str(error)[:180]}]


def audio_sessions() -> list[dict[str, Any]]:
    try:
        from pycaw.pycaw import AudioUtilities
        rows = []
        for session in AudioUtilities.GetAllSessions():
            process = getattr(session, "Process", None)
            rows.append({"pid": getattr(process, "pid", None), "process": process.name() if process else None,
                         "displayName": str(getattr(session, "DisplayName", "")), "state": str(getattr(session, "State", ""))})
        return rows
    except Exception as error:
        return [{"discoveryError": type(error).__name__, "detail": str(error)[:180]}]


def endpoints() -> list[dict[str, Any]]:
    try:
        import pyaudiowpatch as pyaudio
        audio = pyaudio.PyAudio()
        try:
            return [{"index": info["index"], "name": info["name"], "channels": info["maxInputChannels"],
                     "sampleRate": info["defaultSampleRate"], "loopback": bool(info.get("isLoopbackDevice"))}
                    for info in audio.get_device_info_generator()]
        finally:
            audio.terminate()
    except Exception as error:
        return [{"discoveryError": type(error).__name__, "detail": str(error)[:180]}]


def pcm_metrics(chunks: list[bytes]) -> dict[str, float | int]:
    values = array.array("h")
    for chunk in chunks:
        values.frombytes(chunk)
    if not values:
        return {"samples": 0, "peak": 0, "rms": 0.0}
    return {"samples": len(values), "peak": max(abs(value) for value in values),
            "rms": round(math.sqrt(sum(value * value for value in values) / len(values)), 2)}


def probe_endpoint(audio: Any, info: dict[str, Any], seconds: float) -> tuple[dict[str, Any], list[bytes]]:
    rate, channels, frames = int(info["defaultSampleRate"]), int(info["maxInputChannels"]), 1024
    chunks: list[bytes] = []
    result: dict[str, Any] = {"endpoint": info["name"], "index": info["index"], "sampleRate": rate, "channels": channels}
    try:
        def receive(in_data: bytes, frame_count: int, time_info: dict[str, Any], status: int) -> tuple[None, int]:
            if in_data:
                chunks.append(in_data)
            return None, 0  # paContinue; avoids a blocking read on silent drivers.
        stream = audio.open(format=audio.get_format_from_width(2), channels=channels, rate=rate, input=True,
                            input_device_index=info["index"], frames_per_buffer=frames, stream_callback=receive)
        try:
            time.sleep(seconds)
        finally:
            stream.stop_stream(); stream.close()
        result.update(pcm_metrics(chunks))
        result["signal"] = bool(result["rms"] >= SILENCE_RMS and result["peak"] > 500)
    except Exception as error:
        result.update({"signal": False, "error": type(error).__name__, "detail": str(error)[:220]})
    return result, chunks


def capture(seconds: float, diagnostics: Path, test_id: str = "", source: str = "EXPLICIT_TEST_BUTTON") -> dict[str, Any]:
    diagnostics.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {"testId": test_id, "source": source, "at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "requestedSeconds": seconds,
                              "processes": package_processes(), "audioSessions": audio_sessions(), "strategies": [], "endpoints": endpoints()}
    # The portable Python dependencies lack the Windows ApplicationLoopback API.
    # Record real sessions first, then actively probe every available endpoint.
    report["strategies"].append({"name": "process-application-loopback", "state": "UNAVAILABLE",
                                 "detail": "No ApplicationLoopback backend is bundled; session inventory completed and endpoint PCM probing continues."})
    try:
        import pyaudiowpatch as pyaudio
        audio = pyaudio.PyAudio()
        try:
            loopbacks = list(audio.get_loopback_device_info_generator())
            if not loopbacks:
                report["strategies"].append({"name": "endpoint-loopback", "state": "UNAVAILABLE", "detail": "WASAPI exposed no loopback endpoints."})
            else:
                probes, successful = [], None
                for endpoint in loopbacks:
                    probe, chunks = probe_endpoint(audio, endpoint, max(2.0, seconds / len(loopbacks)))
                    probes.append(probe)
                    if probe.get("signal") and successful is None:
                        successful = (probe, chunks)
                report["strategies"].append({"name": "endpoint-loopback", "state": "UNVERIFIED_PCM" if successful else "NO_PCM_SIGNAL", "probes": probes,
                                             "detail": "Endpoint loopback is a system mix and cannot attribute PCM to Phone Link."})
                if successful:
                    probe, chunks = successful
                    recording = diagnostics / "test_call.wav"
                    with wave.open(str(recording), "wb") as output:
                        output.setnchannels(int(probe["channels"])); output.setsampwidth(2); output.setframerate(int(probe["sampleRate"])); output.writeframes(b"".join(chunks))
                    report["recording"] = str(recording)
        finally:
            audio.terminate()
    except ImportError:
        report["strategies"].append({"name": "endpoint-loopback", "state": "UNAVAILABLE", "detail": "pyaudiowpatch is not installed."})
    except Exception as error:
        report["strategies"].append({"name": "endpoint-loopback", "state": "ERROR", "detail": f"{type(error).__name__}: {str(error)[:220]}"})
    signal = any(strategy.get("state") == "UNVERIFIED_PCM" for strategy in report["strategies"])
    report["state"] = "UNVERIFIED_PHONE_LINK_AUDIO" if signal else "NO_PHONE_LINK_CALL_AUDIO"
    report["detail"] = "PCM exists on a shared endpoint but is not attributable to Phone Link; rejected." if signal else "No non-silent PCM was captured; do not treat this as call capture."
    serialized = json.dumps(json_safe(report), ensure_ascii=False, indent=2)
    (diagnostics / "PHONE_LINK_AUDIO_DIAGNOSTIC.json").write_text(serialized, encoding="utf-8")
    (diagnostics / "PHONE_LINK_AUDIO_BLOCKER.md").write_text("# Phone Link audio diagnostic\n\n```json\n" + serialized + "\n```\n", encoding="utf-8")
    return report


def main() -> int:
    # The server consumes this machine-readable output as UTF-8 even when the
    # interactive PowerShell console is configured for an OEM code page.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--list", action="store_true"); parser.add_argument("--test-capture", action="store_true")
    parser.add_argument("--seconds", type=float, default=6.0); parser.add_argument("--diagnostics-dir", type=Path, default=ROOT / "diagnostics"); parser.add_argument("--test-id", default=""); parser.add_argument("--source", default="EXPLICIT_TEST_BUTTON")
    args = parser.parse_args()
    if args.list:
        print(json.dumps({"endpoints": endpoints(), "audioSessions": audio_sessions()}, ensure_ascii=False)); return 0
    if args.test_capture:
        result = capture(max(2.0, min(args.seconds, 20.0)), args.diagnostics_dir, args.test_id, args.source)
        print(json.dumps(json_safe(result), ensure_ascii=False)); return 2
    parser.print_help(); return 2


if __name__ == "__main__":
    raise SystemExit(main())
