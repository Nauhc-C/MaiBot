# MaiBot Development Guide

This file provides guidance when working on the MaiBot codebase.

## Critical: Read AGENTS.md First

**Before making any non-trivial changes**, read [`AGENTS.md`](./AGENTS.md) in full. It contains essential conventions and rules that govern this codebase.

## Project Overview

MaiBot (麦麦/MaiSaka) is an LLM-based interactive agent that runs on QQ via NapCat/OneBot. It's part of the larger Sakiko orchestration wrapper located at the parent directory.

## Architecture

**Two-process model:** `bot.py` starts a Runner (daemon/supervisor) that spawns and monitors a Worker process (identified by `MAIBOT_WORKER_PROCESS=1` env var). Exit code `42` triggers a restart.

### Key Source Areas

- **`src/maisaka/`** — Sakiko/MaiSaka runtime layer
  - Chat loop orchestration (`chat_loop_service.py`)
  - Reasoning engine
  - Focus/attention logic
  - Memory system
  - Reply effects
  - Built-in tools
  
- **`src/chat/`** — Core messaging infrastructure
  - Message receive/send
  - Heart flow
  - Replyer
  - Image system

- **`src/A_memorix/`** — Self-contained memory subsystem
  - **IMPORTANT:** Has its own modification policy
  - Read `src/A_memorix/MODIFICATION_POLICY.md` before editing anything here
  - Respect attribution constraints

- **`src/llm_models/`** — LLM integration layer
- **`src/learners/`** — Expression, behavior, and jargon learning
- **`src/person_info/`** — User/person information management
- **`src/webui/`** — FastAPI-based web dashboard
- **`src/plugin_runtime/`** — Plugin system runtime
- **`src/mcp_module/`** — MCP (Model Context Protocol) integration

- **`plugins/`** — Bundled plugins (each in its own subfolder)
  - `xuqian13_tts-voice-plugin` — TTS integration with GPT-SoVITS

### Configuration

- **`config/bot_config.toml`** — Bot personality, reply style, QQ account
- **`config/model_config.toml`** — LLM model configuration

**Config modification rule:** Edit the template files and bump version numbers, don't edit the actual config files directly. Never add `ConfigUpgradeHook` unless explicitly instructed. Never touch `legacy_migration` (frozen).

## Running & Testing

This project uses **uv** as the primary package manager. `pyproject.toml` is the source of truth; keep `requirements.txt` in sync.

### Commands (run from `project/MaiBot`)

```bash
# Run the bot
uv run python -X utf8 bot.py

# Run all tests
uv run pytest

# Run specific test
uv run pytest pytests/maisaka_test/path_to_test.py::test_name

# Lint
uv run ruff check .

# Format
uv run ruff format .
```

**Ruff config:** Line length 120, rules E/F/B, double quotes.

**Test structure:** Tests live in `pytests/`, mirroring `src/` as `*_test` directories. `pytests/conftest.py` adds `src/` and project root to `sys.path`.

### Dashboard/WebUI

Frontend lives in `dashboard/`, uses **bun**:

```bash
# Dev server (MUST use port 7999)
bun run dev

# Build (run manually, not automatic)
bun run build

# Lint & test
bun run lint
bun run test  # vitest
```

Electron variants available under `electron:*` scripts.

## Core Conventions (Summary)

See [`AGENTS.md`](./AGENTS.md) for full details. Key points:

### Language
- **Primary language: 简体中文** for comments, logs, WebUI
- Prompt template changes must be mirrored across CN/EN/JP files, aligned to Chinese version

### Code Quality
- **No fallback/兜底 patterns** — let errors surface fully, find root causes
- Keep existing comments and type annotations during refactors
- Avoid unbounded ruff/formatting sweeps over unrelated code

### Import Order
1. `from ... import` blocks before bare `import` blocks, alphabetized
2. Stdlib/third-party before local imports
3. Local `from src...` imports grouped by second-level folder
4. Blank lines between groups

### Session IDs
- Outside chat-stream creation/registration, don't call `SessionUtils.calculate_session_id`
- Resolve real `ChatSession` IDs via `chat_manager`
- Never write self-computed fallback hashes to the DB

### Attribute Access
- Avoid `getattr`/`setattr` for known attributes
- Access attributes directly when type is known

### WebUI
- Display real stream names (group name or "xxx的私聊"), not `session_id`
- Dev server fixed to port 7999
- Don't auto-run `npm run build` — manual only

### Plugins
- Create new plugins as independent repos under `plugins/`
- Don't modify root `.gitignore`
- Ask before changing main program code for a plugin

### Prompt Templates
- Changes must be synchronized across CN/EN/JP files
- Align to the Chinese version

## Memory System (A_memorix)

If your changes touch `src/A_memorix/`, **read `src/A_memorix/MODIFICATION_POLICY.md` first**. This subsystem has its own attribution and modification constraints that must be respected.

## Plugin Development

- SDK guide: https://github.com/Mai-with-u/maibot-plugin-sdk/blob/main/docs/guide.md
- Plugin submission: https://github.com/Mai-with-u/plugin-repo/blob/main/CONTRIBUTING.md
- Create plugins as independent git repos under `plugins/`
- Request permission before modifying main program code for plugin needs

## Changelog Guidelines

Structure in two parts:
1. User-facing feature changes
2. Developer-facing changes (fixes, plugin SDK, API changes)

Group by module, one feature per line.

**Don't include:** Version bumps, dependency updates.

## Log Retrieval CLI Usage

When using the log retrieval CLI for agents:
1. Search first, then decide what to read — don't request full logs upfront
2. Use time ranges, exact phrases, keywords, session/stage filters to narrow results
3. Read index/summary/pointers by default; only fetch full text when needed
4. For planner/replyer/user issues, use context relationships to locate related records
5. If CLI returns JSON, filter by structured fields — don't copy long text fields into context

## Documentation Updates

For functional changes, API changes, or development changes:
- Update `/mai-docs` in the project root
- Don't create new content in parent directories

## Related Files

- [`AGENTS.md`](./AGENTS.md) — Full development conventions (READ THIS)
- [`README.md`](./README.md) — User-facing documentation
- [`CODE_OF_CONDUCT.md`](./CODE_OF_CONDUCT.md)
- [`EULA.md`](./EULA.md)
- [`LICENSE`](./LICENSE)
