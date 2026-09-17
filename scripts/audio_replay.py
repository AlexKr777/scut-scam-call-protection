"""Operator entry point for the immutable SCUT Audio Replay V1 pack."""
from __future__ import annotations
import argparse, json, os, sys, time, uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from backend.audio_replay import (LOCK, MANIFEST, REPORTS, RUNTIME, STATUS, STOP, STABILIZER_V3_REPORTS, STABILIZER_V3_RUNTIME, STREAMING_PIPELINE_VERSION, UTTERANCE_PIPELINE_VERSION, UTTERANCE_REPORTS, UTTERANCE_RUNTIME, WHISPER_QUALITY_V2_PIPELINE_VERSION, WHISPER_QUALITY_V2_REPORTS, WHISPER_QUALITY_V2_RUNTIME, AudioReplayEngine, atomic_json_write, now, prepare_pack, verify_preflight, write_reports)

def command_prepare(_: argparse.Namespace) -> int:
    result = prepare_pack(); preflight = verify_preflight()
    print(json.dumps({**result, "preflight": preflight}, ensure_ascii=False, indent=2)); return 0

def _load_cases() -> list[dict]:
    return [x for x in json.loads(LOCK.read_text(encoding="utf-8"))["cases"] if x.get("download_status") == "READY"]

def _run(args: argparse.Namespace, *, reports_dir: Path, runtime_dir: Path, artifact_stem: str, pipeline_version: str | None = None, replay_method: str = "replay") -> int:
    preflight = verify_preflight(); cases = _load_cases()
    case_id = getattr(args, "case_id", None)
    selected = [x for x in cases if not case_id or x["case_id"] == case_id]
    if case_id and not selected: raise SystemExit(f"unknown READY case: {case_id}")
    run_id = args.run_id or datetime_id()
    run_started = now()
    runtime_dir.mkdir(parents=True, exist_ok=True); (reports_dir / "calls").mkdir(parents=True, exist_ok=True)
    completed = []
    status_path = runtime_dir / "status.json"
    stop_path = runtime_dir / "stop.request"
    atomic_json_write(status_path, status(run_id, "RUNNING", "LOADING_RUNTIME", selected, completed, None, run_started))
    try:
        engine = AudioReplayEngine(preflight)
    except Exception as error:
        atomic_json_write(status_path, {**status(run_id, "FAILED", "LOADING_RUNTIME", selected, completed, None, run_started), "last_error": str(error)})
        raise
    for index, case in enumerate(selected, 1):
        if stop_path.exists():
            atomic_json_write(status_path, status(run_id, "STOPPED", "SAFE_CHECKPOINT", selected, completed, case, run_started)); return 0
        output = reports_dir / "calls" / f"{case['case_id']}.json"
        if output.is_file() and not args.force:
            completed.append(json.loads(output.read_text(encoding="utf-8"))); continue
        atomic_json_write(status_path, status(run_id, "RUNNING", "BENCHMARK", selected, completed, case, run_started))
        try:
            result = getattr(engine, replay_method)(case, realtime=args.realtime)
        except Exception as error:
            result = {**case, "status": "ERROR", "triggered": False, "errors": [str(error)], "whisper": {"WER": None, "CER": None}, "nomic": {"max_score": None}}
        atomic_json_write(output, result); completed.append(result)
        atomic_json_write(status_path, status(run_id, "RUNNING", "BENCHMARK", selected, completed, None, run_started))
    paths = write_reports(completed, preflight, run_id, reports_dir, artifact_stem, pipeline_version)
    atomic_json_write(status_path, {**status(run_id, "COMPLETE", "REPORT", selected, completed, None, run_started), "reports": paths})
    print(json.dumps(paths, ensure_ascii=False, indent=2)); return 0

def command_run(args: argparse.Namespace) -> int:
    return _run(args, reports_dir=REPORTS, runtime_dir=RUNTIME, artifact_stem="SCUT_AUDIO_REPLAY_V1", replay_method="replay_streaming")

def command_run_stabilizer_v2(args: argparse.Namespace) -> int:
    """Run the immutable V1 pack into a separate post-stabilizer artifact."""
    return _run(args, reports_dir=STABILIZER_V3_REPORTS, runtime_dir=STABILIZER_V3_RUNTIME,
                artifact_stem="SCUT_AUDIO_REPLAY_V1_STABILIZER_V3", pipeline_version=STREAMING_PIPELINE_VERSION, replay_method="replay_streaming")

def command_run_utterance(args: argparse.Namespace) -> int:
    """Run the immutable V1 pack through the authoritative whole-utterance path."""
    return _run(args, reports_dir=UTTERANCE_REPORTS, runtime_dir=UTTERANCE_RUNTIME,
                artifact_stem="SCUT_AUDIO_REPLAY_V1_UTTERANCE_WHISPER", pipeline_version=UTTERANCE_PIPELINE_VERSION)

def command_run_whisper_quality_v2(args: argparse.Namespace) -> int:
    return _run(args, reports_dir=WHISPER_QUALITY_V2_REPORTS, runtime_dir=WHISPER_QUALITY_V2_RUNTIME,
                artifact_stem="SCUT_WHISPER_QUALITY_V2", pipeline_version=WHISPER_QUALITY_V2_PIPELINE_VERSION,
                replay_method="replay_whisper_quality_v2")

def command_demo(args: argparse.Namespace) -> int:
    """Replay exactly one locked case without changing benchmark outputs."""
    preflight = verify_preflight()
    case = next((row for row in _load_cases() if row["case_id"] == args.case_id), None)
    if case is None:
        raise SystemExit(f"unknown READY case: {args.case_id}")
    print(f"SCUT AUDIO REPLAY V1 REALTIME_1X\nCase: {case['case_id']}\nExpected: {case['expected_class']}\nThreshold: {preflight['threshold']}")
    result = AudioReplayEngine(preflight, logger=print).replay(case, realtime=True)
    whisper, nomic, alert = result["whisper"], result["nomic"], result["alert"]
    rolling = nomic["timeline"][-1]["rolling_transcript"] if nomic["timeline"] else ""
    print("\nDEMO SUMMARY")
    print(f"case_id={result['case_id']}\nexpected_class={result['expected_class']}\nlatest_finalized_segment={whisper['final_transcript']}\nfinal_accumulated_transcript={rolling}\nmax_nomic_score={nomic['max_score']}\nalert={'YES' if alert['triggered'] else 'NO'}\nfirst_alert_sec={alert['first_alert_sec']}\nwhisper_latency_sec={whisper['latency_sec']}\nwhisper_rtf={whisper['real_time_factor']}")
    return 0

def datetime_id() -> str:
    return time.strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6]

def status(run_id, state, phase, selected, completed, current, started_at):
    failed = sum(x.get("status") in {"ERROR", "FAIL_DETECTION", "FAIL_ASR"} for x in completed)
    return {"run_id": run_id, "pid": os.getpid(), "state": state, "phase": phase, "started_at": started_at, "updated_at": now(), "total_cases": len(selected), "completed_cases": len(completed), "failed_cases": failed, "remaining_cases": len(selected) - len(completed), "current_case_id": current and current["case_id"], "current_language": current and current["language"], "current_expected_class": current and current["expected_class"], "current_source_type": current and current["source_type"], "current_audio_position_sec": None, "current_audio_duration_sec": current and current.get("duration_sec"), "whisper_segments": None, "nomic_evaluations": None, "last_nomic_score": None, "max_nomic_score": None, "alert_triggered": None, "first_alert_sec": None, "elapsed_sec": None, "eta_sec": None, "last_error": None}

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(); subs = parser.add_subparsers(dest="command", required=True)
    subs.add_parser("prepare").set_defaults(func=command_prepare)
    run = subs.add_parser("run"); run.add_argument("--case-id"); run.add_argument("--realtime", action="store_true"); run.add_argument("--force", action="store_true"); run.add_argument("--run-id"); run.set_defaults(func=command_run)
    stabilized = subs.add_parser("run-stabilizer-v2"); stabilized.add_argument("--force", action="store_true"); stabilized.add_argument("--run-id"); stabilized.add_argument("--realtime", action="store_true"); stabilized.set_defaults(func=command_run_stabilizer_v2)
    utterance = subs.add_parser("run-utterance"); utterance.add_argument("--case-id"); utterance.add_argument("--force", action="store_true"); utterance.add_argument("--run-id"); utterance.add_argument("--realtime", action="store_true"); utterance.set_defaults(func=command_run_utterance)
    quality_v2 = subs.add_parser("run-whisper-quality-v2"); quality_v2.add_argument("--case-id"); quality_v2.add_argument("--force", action="store_true"); quality_v2.add_argument("--run-id"); quality_v2.add_argument("--realtime", action="store_true"); quality_v2.set_defaults(func=command_run_whisper_quality_v2)
    demo = subs.add_parser("demo"); demo.add_argument("case_id"); demo.set_defaults(func=command_demo)
    return parser

def main() -> int:
    args = build_parser().parse_args()
    return args.func(args)
if __name__ == "__main__": raise SystemExit(main())
