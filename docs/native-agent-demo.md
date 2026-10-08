# Native Agent demo

[简体中文](native-agent-demo.zh-CN.md) · [AI guide](../README_AI.md)

Run a portfolio demo with an existing portable Memos executable and `ai-service/.venv`.
No Docker, model, or API key is needed. The binary must include the current AgentRun and
Provider BFF APIs; the core installer does not bundle Python AI Service. Install pinned
Python dependencies using [development](development.md). The launcher never builds,
downloads dependencies, or opens a browser.

From the repository root, substitute your existing portable binary path. Do not use Setup:

```powershell
.\scripts\start-agent-demo-native.ps1 -MemosExe .\build\DevMemoAI.exe
```

The launcher starts two loopback-only services in sequence, selects free ports, and prints
the demo URL and synthetic login. Each run creates separate data, seeds two Chinese project
notes, saves deterministic settings, and verifies cited answers and project reports.
Keep the terminal running and manually open the printed URL using the `demo` login and
printed random password. Ctrl+C stops only these two child processes and preserves reports.

To verify HTTP behavior and stop automatically:

```powershell
.\scripts\start-agent-demo-native.ps1 -MemosExe .\build\DevMemoAI.exe -VerifyOnly
```

This mode checks 25 behaviors: administrator settings, connection testing, actual Memo
Webhook indexing, server citations, consecutive reports, idempotent request replay,
download SHA-256, private Memo isolation, and creator-only artifacts. It also stops its
AI Service, verifies Agent HTTP 503 while ordinary Memo reads still work, and stops Memos.
Success prints `DEVMEMO_NATIVE_DEMO_OK`; failure exits nonzero and preserves local logs.

The fallback demonstration temporarily saves a local Provider configuration without
Memo data consent. The existing guard rejects it before constructing/calling the Provider;
the report marks `provider_unavailable` and deterministic fallback. Deterministic settings
are then restored. This synthetic configuration failure does not verify a real Provider,
network timeout, or model quality.

Git-ignored `.devmemo-local/runtime/native-agent-demo-*` holds separate core/AI databases,
logs, `project-summary.md`, `project-summary-fallback.md`, `evidence-answer.json`, and
`verification.json`. The latter records checks, binary digest, and child exit state.
Login tokens and temporary delegation/encryption keys stay in process memory;
inherited Provider credentials are not reused.

Optional `-MemosPort 5231 -AiPort 8001` fixes the ports; occupied ports fail without
stopping existing services. Deployment defaults are unchanged. The demo uses
`GOMAXPROCS=1`, one Python worker, and single-threaded numerical libraries.

HTTP evidence does not replace UI acceptance. Existing embedded Web resources must have
the AI UI opt-in (`VITE_AI_SERVICE_URL`) to display the Agent panels. This launcher cannot
change an embedded build-time flag. Downloaded HTTP reports remain usable if panels are
absent, but that does not establish a complete UI demonstration.
