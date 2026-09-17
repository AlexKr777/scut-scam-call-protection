# Verified jury-demo flow

## Shortest verified demo

| Step | Backend support/data | Trigger and risk |
|---|---|---|
| 1. Open Control Center | local server/browser, status fields | `START_SCUT`; prerequisites include project Python, APK, Whisper self-test |
| 2. Pair Android | one-time pairing payload; Android reports permissions/heartbeat | generate payload, paste in Android; network/reachability required |
| 3. Verify Android alert | synthetic alert delivered to authenticated WS client | **Test Android Alert**; does not prove detection/audio |
| 4. Verify Phone Link audio separately | 6 s process-loopback candidate test, signal/RMS/peak/WAV | **Test Call Capture** during a real suitable call; PASS is machine-dependent |
| 5. Demonstrate verified semantic alert | local transcript injection produces risk/decision; PROTECT CRITICAL sends Android event | Set PROTECT, submit a stable caller-directed scam phrase; does not demonstrate automatic live phone capture |
| 6. Optional guarded STT demo | TEST guarded system mix → final Whisper transcript | TEST + guarded button; only when sentinel and helper conditions hold; not Phone Link-attributed |

Evidence: `README.md:1-20`, `backend/services.py:159-273`, `309-371`, `410-457`; `frontend/index.html:27-34`.

## Demo preparation constraints

- Run capture diagnostic on the target machine while a real remote caller speaks; source documents this as the only capture PASS criterion.
- Android must be paired, online and granted notification permission; overlay is optional.
- Whisper must have passed bootstrap; default ASR may require configured CUDA profile or explicit recovery mode.
- The most defensible end-to-end jury claim is **manual stable transcript → semantic detection → paired Android alert**. Do not represent it as a verified continuous Phone Link live-call pipeline.
