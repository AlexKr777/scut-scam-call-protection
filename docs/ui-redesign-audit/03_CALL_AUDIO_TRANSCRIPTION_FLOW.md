# Call, audio, and transcription flow

## Actual flows (do not conflate them)

### A. Phone Link capture verification — VERIFIED diagnostic, not live protection

1. User presses **Test Call Capture**; backend discovers currently running candidates attributable to Phone Link/CrossDevice.
2. For each candidate, the server invokes `scut-process-loopback.exe --pid … --seconds 6 --wav …`.
3. The helper activates Windows process-loopback for that PID/tree, captures 48 kHz/16-bit/stereo PCM to a WAV, and returns RMS/peak/signal JSON. A PASS requires helper signal, a nonempty WAV, and no helper error.
4. On PASS, the diagnostic copies the WAV to `diagnostics/test_call.wav`, stores attempt data in in-memory `audio_status`, and writes diagnostic files. On failure it records FAIL and blocker evidence.

Evidence: `backend/services.py:26-75`, `backend/services.py:410-457`; `windows-audio/scut_process_loopback.cpp:57-111`.

### B. Guarded transcription — VERIFIED TEST-mode diagnostic

1. User sets `TEST`, then presses **Test Guarded Call Transcript**. Other modes return `TEST_MODE_REQUIRED`.
2. Three daemon threads start: guarded mix capture, mic capture, and the single priority ASR consumer.
3. The mix helper refuses capture unless a session display name contains a device-specific sentinel; it loopbacks the default communications render endpoint. The mic helper reads the default communications capture endpoint. Both output raw PCM only.
4. The mix worker collects two-second capture blocks, splits them into 250 ms frames, uses RMS VAD, and finalizes an utterance after the buffer’s VAD rule. The ASR worker transcribes a finalized caller utterance once with the configured accurate Whisper pass. Caller work has priority over mic work.
5. Final caller text is passed to `ScutService.transcript`, then server emits `FINAL_TRANSCRIPT` and status events. The status payload only exposes the latest transcript; it does not expose the emitted timestamps/language to the web UI.

Evidence: `backend/services.py:159-273`; `backend/guarded_audio.py:30-65`; `backend/realtime_pipeline.py:45-104`; `windows-audio/scut_guarded_mix_pcm_stream.cpp:1-8`.

```mermaid
sequenceDiagram
  participant U as User
  participant W as Web UI
  participant S as ScutService
  participant M as Guarded mix helper
  participant STT as faster-whisper
  participant R as Risk engine
  U->>W: TEST; Test Guarded Call Transcript
  W->>S: POST /api/diagnostics/guarded-transcription
  S->>M: capture 2 s PCM blocks (stdout)
  M-->>S: raw PCM or sentinel/capture error
  S->>S: 250 ms frames, VAD, endpoint finalization
  S->>STT: finalized caller PCM once
  STT-->>S: text + language/probability
  S->>R: finalized Utterance
  S-->>W: FINAL_TRANSCRIPT, risk_event, decision/status
  alt PROTECT + CRITICAL decision
    S-->>Android: alert WebSocket event
  end
```

## STT contract

| UI-relevant item | Availability | Notes |
|---|---|---|
| partial live text | PARTIAL / unused | internal `FAST_PARTIAL` status branch exists but normal caller path intentionally disables rolling text (`backend/services.py:179-185`, `247-255`) |
| final segment text | YES | emitted WebSocket event and latest status transcript (`backend/services.py:234-240`) |
| full call transcript/history | NO | deque retains only 12 plain strings in memory (`backend/services.py:83-86`, `309-315`) |
| start/end timestamps | PARTIAL | emitted only in `FINAL_TRANSCRIPT`; no HTTP/history schema (`backend/services.py:239`) |
| language/probability | PARTIAL | returned by Whisper and recorded in audio status; not included in final event/status transcript (`backend/guarded_audio.py:48-65`) |
| speakers | PARTIAL | caller/user processing exists; web only renders one latest text |
| confidence | PARTIAL | Whisper quality metrics exist internally; no stable UI contract |

Whisper is local `faster-whisper`; bootstrap prepares small CPU model, while the default caller profile requests `large-v3-turbo` CUDA and supports explicit small/CPU recovery (`backend/whisper_engine.py:18-71`, `backend/config.py:31-40`). Language is detected by Whisper; no fixed Romanian/Russian/English option is passed in the active accurate call (`backend/guarded_audio.py:48-65`).

## Failure-visible audio states

Observed values include `IDLE`, `STARTING`, `CAPTURING`, `FINAL_TRANSCRIPT`, `FAST_PARTIAL`, `STABLE_TRANSCRIPT`, `TEST_MODE_REQUIRED`, `ALREADY_CAPTURING`, `CALL_SENTINEL_NOT_ACTIVE`, `GUARDED_CAPTURE_FAILED_<exit>`, `USER_MIC_CAPTURE_FAILED_<exit>`, diagnostic `PASS`/`FAIL`, and `NATIVE_PROCESS_LOOPBACK_HELPER_MISSING` reasons. These are strings, not a formal enum (`backend/services.py:100`, `159-273`, `410-457`).
