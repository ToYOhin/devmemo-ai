# AI Service application boundary

This directory is the target module boundary for the next refactor. It is introduced before moving runtime code so each migration can keep `main.py` as a compatibility launcher.

- `api/`: HTTP and Memos webhook protocol mapping.
- `domain/`: provider-neutral request, summary, embedding, and retrieval models.
- `services/`: use cases and orchestration.
- `adapters/`: OpenAI, Ollama, FastEmbed, Qdrant, and persistence implementations.

Do not import vendor SDK types into `domain/`. Move one boundary at a time and keep the existing test command green.
