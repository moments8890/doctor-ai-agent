# Doctor AI Agent

A personal AI follow-up copilot for specialists managing private patients outside hospitals. Doctors dictate medical records, get AI-powered differential diagnoses, manage follow-up tasks, and communicate with patients — all shaped by their own clinical rules. Not an EMR; a lightweight clinical productivity tool.

**Stack:** FastAPI + Plan-and-Act agent pipeline / React SPA / WeChat miniprogram / SQLite (dev) / MySQL (prod)

## Quick Start

```bash
./cli.py bootstrap   # one-time setup (installs deps, creates DB)
./cli.py start       # starts backend :8000 + frontend :5173
./cli.py stop        # stops everything
```

For production/VM deployment and LLM provider setup, see [`docs/dev/index.md`](docs/dev/index.md).

## New Here?

Start with **[`docs/architecture.md`](docs/architecture.md)** — it covers what the system does, how the agent pipeline works, and has a "Start Here" table mapping common tasks to the right files. From there, follow the links below for deeper dives.

## Documentation

| Concern | Entrypoint | Covers |
|---------|-----------|--------|
| **Repo rules** | [`AGENTS.md`](AGENTS.md) | Code style, testing policy, push rules, cascading impact checklist |
| **Architecture** | [`docs/architecture.md`](docs/architecture.md) | System layers, agent pipeline, DB schema, prompt system, startup |
| **Product** | [`docs/product/README.md`](docs/product/README.md) | North star, strategy, roadmap, feature status, CDS decisions |
| **UI / UX** | [`docs/ux/UI-DESIGN.md`](docs/ux/UI-DESIGN.md) | Design system, components, tokens, patterns |
| **Dev ops** | [`docs/dev/index.md`](docs/dev/index.md) | Testing, deployment, LLM providers, patient sim |
