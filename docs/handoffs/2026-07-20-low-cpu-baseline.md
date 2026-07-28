# Low-CPU baseline evidence

Date: 2026-07-20

## Applied runtime limits

- Memos container: `750000000` NanoCPUs (`0.75` CPU) and `GOMAXPROCS=1`.
- AI Service container: `250000000` NanoCPUs (`0.25` CPU), with `OMP_NUM_THREADS=1`, `OPENBLAS_NUM_THREADS=1`, and `MKL_NUM_THREADS=1`.
- Qdrant and Ollama are explicit Compose profiles and were not started or recreated.

## Verification

- `docker compose config --quiet` and profile-aware config validation passed.
- Runtime Docker inspection confirmed the limits and thread settings above.
- AI Service `GET /health` returned deterministic-provider health.
- Serial `scripts/verify-devmemo.ps1` passed: `187 passed`, one existing Starlette/httpx deprecation warning, `DEVMEMO_VERIFY_OK`.

No volume was deleted. Default runtime behavior remains deterministic + memory, `AI_INDEX_ON_WEBHOOK=false`, `AI_INDEX_MODE=memo`, and `AI_PUBLIC_CHUNK_RETRIEVAL=false`.
