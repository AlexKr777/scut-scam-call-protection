# Gaps and unknowns

| Finding | Classification | What would verify/reduce uncertainty |
|---|---|---|
| Continuous Phone Link capture in PROTECT | NOT IMPLEMENTED by inspected orchestration | code would need a PROTECT capture worker wired to process loopback/ASR; current code has none |
| Automatic call start/end detection | NOT IMPLEMENTED | no event watcher/call state machine found; inspect future native integration if added |
| Production success on a specific machine | UNCERTAIN | run explicit Phone Link diagnostic with a real call and inspect generated diagnostic, without publishing personal audio/details |
| Guarded mix identity | PARTIAL | helper relies on one hard-coded audio session display name and default communications endpoint, so it is not generic/process-attributed |
| Nomic inference availability | UNCERTAIN | verify required model artifact, CUDA/Torch runtime and deployment configuration on target; service catches any failure |
| Provider/AI availability | UNCERTAIN | verify configured environment variable names and endpoint connectivity; never expose values |
| Persistence/history | NOT IMPLEMENTED except paired devices/machine config | no call/transcript/alert database/files or history routes found |
| Alert cancel/dismiss/cooldown | NOT IMPLEMENTED | no data model/API/action found; ACK only measures latency |
| Browser/WebSocket authentication | PARTIAL | mobile auth exists; browser subscribe is accepted without auth. Network deployment/security posture needs separate review |
| Host test result | VERIFIED limitation in audit environment | workspace Python 3.14 could not import `audioop`; bootstrap targets Python 3.12 (`scripts/first-run.ps1:57-86`, `backend/realtime_pipeline.py:9`) |

No secrets, private diagnostic recordings, phone numbers, device names, credentials, tokens, or environment values are reproduced in this audit.
