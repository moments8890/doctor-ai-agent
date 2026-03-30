# Developer Guide

Everything you need to develop, test, and deploy.

---

## Quick Start

```bash
./cli.py bootstrap                    # one-time setup
./cli.py start                        # backend :8000 + frontend :5173
./cli.py start --port 8001 --no-frontend  # test server (never use 8000 for tests)
./cli.py stop
```

## LLM Providers

All providers run Qwen or DeepSeek models. Pick one:

```bash
./cli.py start --provider groq        # fast dev — Qwen3 32B, free 6K req/day
./cli.py start --provider cerebras    # fastest — Qwen3 32B, free 1M tokens/day
./cli.py start --provider sambanova   # free forever — Qwen2.5 72B, no credit card
./cli.py start --provider deepseek    # best quality — production
./cli.py start --provider ollama      # offline — Qwen 2.5 7B, local GPU
```

API keys go in `config/runtime.json` (gitignored; see `config/runtime.json.sample`).

Switch models at runtime: `GROQ_MODEL=deepseek-r1-distill-qwen-32b ./cli.py start --provider groq`

For full provider comparison (pricing, latency, all models): [llm-providers.md](llm-providers.md)

---

## Testing

### Policy

- **Default:** do NOT run tests automatically during development
- **Opt-in TDD:** invoke `/tdd` to activate for a session
- **Pre-push:** run `/test-gate` or the commands below
- **Port 8001 only:** all tests run against `:8001`, never `:8000` (dev server with real data)
- **Default test LLM provider:** `groq`

### Running Tests

```bash
# Backend — the reliable gate for any change
cd frontend/web && npm run build
bash scripts/test.sh integration-full

# Frontend
cd frontend/web && npm test

# Unit tests (after modifying domain logic)
bash scripts/test.sh unit

# Benchmark (only if e2e/fixtures/data/ is installed)
./cli.py start --port 8001 --no-frontend &
bash scripts/test.sh hero-loop
```

### Test Modes (`scripts/test.sh`)

| Mode | What it runs | Needs fixtures? |
|------|-------------|----------------|
| `unit` | `tests/core/` (mocked, no server) | No |
| `integration-full` | All `tests/integration/` | No |
| `chatlog-half` | Chatlog E2E replay (half) | Yes (`e2e/fixtures/data/`) |
| `chatlog-full` | Chatlog E2E replay (full) | Yes |
| `hero-loop` | Benchmark gate | Yes + saved baseline |
| `all` | Integration tests | No |

### What to Test When

| Change type | Run |
|------------|-----|
| Domain logic (triage, PDF, knowledge) | `/tdd` + unit tests |
| Prompts / routing | `integration-full` |
| Frontend components | `npm run build` + `npm test` |
| Pre-push (any change) | `/test-gate` |

### Patient Simulation

```bash
./cli.py start --port 8001 --no-frontend &
python scripts/run_patient_sim.py --server http://127.0.0.1:8001
```

Reports: `reports/patient_sim/`, `reports/doctor_sim/`

For personas, YAML config, and validation: [patient-simulation-guide.md](patient-simulation-guide.md)

---

## Deployment

### Local (dev)

```bash
./cli.py bootstrap && ./cli.py start
```

### Production (Tencent Cloud VM)

```bash
./cli.py bootstrap --vm                          # one-time: OS deps, Docker, MySQL
export DEEPSEEK_API_KEY="<key>"
./cli.py start --prod --provider deepseek         # or: --provider tencent_lkeap
```

For the full 8-step deployment guide: [../deploy/tecenet-deployment/index.md](../deploy/tecenet-deployment/index.md)

### Release Checklist

Before pushing:

1. `cd frontend/web && npm run build` — frontend compiles
2. `bash scripts/test.sh integration-full` — backend passes
3. If benchmark fixtures installed: `bash scripts/test.sh hero-loop`

For full checklist: [mvp-release-checklist.md](mvp-release-checklist.md)

---

## Configuration

- **Single config file:** `config/runtime.json` (gitignored)
- **Template:** `config/runtime.json.sample`
- **No `.env` files** — the main app does not use dotenv
- **LAN inference preferred:** set `OLLAMA_BASE_URL` to `http://192.168.0.123:11434` in runtime.json

---

## Dev Data

```bash
python scripts/preload_patients.py --doctor-id <id> --count 30 --with-records
python scripts/seed_db.py --export       # snapshot current DB
python scripts/seed_db.py --import       # restore snapshot
python scripts/seed_db.py --reset --import  # wipe + restore
```

---

## Deep Dives

| Doc | Covers |
|-----|--------|
| [llm-providers.md](llm-providers.md) | Full provider comparison, pricing, all models, setup instructions |
| [llm-prompting-guide.md](llm-prompting-guide.md) | 7-layer prompt stack, writing rules, patterns, anti-patterns |
| [patient-simulation-guide.md](patient-simulation-guide.md) | Sim framework, personas, YAML config, validation |
| [../TESTING.md](../TESTING.md) | Full test classification, medical safety testing, custom skills |
| [frontend-ui-audit.md](frontend-ui-audit.md) | 3-level UI audit process |
| [mvp-release-checklist.md](mvp-release-checklist.md) | Release gate details |
| [ollama-windows-lan-setup.md](ollama-windows-lan-setup.md) | Windows LAN Ollama server setup |
| [../deploy/tecenet-deployment/index.md](../deploy/tecenet-deployment/index.md) | Tencent Cloud deployment (8-step guide) |
