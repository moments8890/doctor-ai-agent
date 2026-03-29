# Developer Operations — Canonical Entrypoint

How to develop, test, and deploy.

## Testing

| Doc | Covers |
|-----|--------|
| [../TESTING.md](../TESTING.md) | Test modes, validation workflow, port conventions, MVP testing policy |
| [frontend-ui-audit.md](frontend-ui-audit.md) | 3-level UI audit process (functional → usable → workflow-fit) |
| [patient-simulation-guide.md](patient-simulation-guide.md) | Patient simulation framework, personas, running sims on port 8001 |
| [adr-0020-patient-portal-testing.md](adr-0020-patient-portal-testing.md) | Patient portal testing strategy |

## LLM & Prompts

| Doc | Covers |
|-----|--------|
| [llm-providers.md](llm-providers.md) | LLM provider setup (Groq, Ollama, DeepSeek, Tencent LKEAP) |
| [llm-prompting-guide.md](llm-prompting-guide.md) | Prompt engineering guide adapted to 6-layer stack and Chinese medical domain |
| [ollama-windows-lan-setup.md](ollama-windows-lan-setup.md) | Windows LAN Ollama inference server setup |

## Deployment & Release

| Doc | Covers |
|-----|--------|
| [../deploy/tecenet-deployment/index.md](../deploy/tecenet-deployment/index.md) | Tencent Cloud deployment (8-step guide: prerequisites → go-live) |
| [mvp-release-checklist.md](mvp-release-checklist.md) | Release gate: frontend build, integration suite, optional benchmark gate when local dataset assets are installed |

## Quick Reference

- **Dev server:** `./cli.py start` (port 8000)
- **Test server:** `./cli.py start --port 8001 --no-frontend`
- **Frontend smoke:** `cd frontend/web && npm run build`
- **Backend integration:** `bash scripts/test.sh integration-full`
- **Benchmark gate:** `bash scripts/test.sh hero-loop` only when `e2e/fixtures/data/` and `reports/baseline/` are installed locally
- **Patient sim:** `python scripts/run_patient_sim.py --server http://127.0.0.1:8001`
- **LAN inference:** set `OLLAMA_BASE_URL=http://192.168.0.123:11434` in `config/runtime.json`
