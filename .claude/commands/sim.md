# /sim — Run patient or doctor simulation

Run simulated patients or doctors against the interview pipeline to verify
agent behavior. Wraps `scripts/run_patient_sim.py` and `scripts/run_doctor_sim.py`.

## Usage

- `/sim` — run all 10 patient personas (default)
- `/sim P1,P3,P6` — run specific patient personas
- `/sim doctor` — run doctor simulation
- `/sim doctor D1,D2` — run specific doctor personas
- `/sim quick` — run 3 fast personas (P1, P2, P9) for a quick smoke test

## Workflow

### Step 1: Check server on port 8001

```bash
curl -sf http://127.0.0.1:8001/health > /dev/null 2>&1 && echo "SERVER_UP" || echo "SERVER_DOWN"
```

If `SERVER_DOWN`, warn the user:
"Test server not running on port 8001. Start it with:
`./cli.py start --port 8001 --no-frontend`
Then run /sim again."

**Do NOT start the server automatically** — the user controls server lifecycle.
**Do NOT use port 8000** — that is the dev server with real data (AGENTS.md rule).

### Step 2: Determine what to run

Parse the user's arguments:

| Input | Personas | Script |
|-------|----------|--------|
| `/sim` | `--patients all` | `run_patient_sim.py` |
| `/sim P1,P3` | `--patients P1,P3` | `run_patient_sim.py` |
| `/sim quick` | `--patients P1,P2,P9` | `run_patient_sim.py` |
| `/sim doctor` | `--personas all` | `run_doctor_sim.py` |
| `/sim doctor D1,D2` | `--personas D1,D2` | `run_doctor_sim.py` |

### Step 3: Run the simulation

For patient sim:
```bash
cd /Volumes/ORICO/Code/doctor-ai-agent && \
PYTHONPATH=src .venv/bin/python scripts/run_patient_sim.py \
  --patients <PERSONAS> \
  --patient-llm groq \
  --server http://127.0.0.1:8001 \
  --no-quality-score
```

For doctor sim:
```bash
cd /Volumes/ORICO/Code/doctor-ai-agent && \
PYTHONPATH=src .venv/bin/python scripts/run_doctor_sim.py \
  --personas <PERSONAS> \
  --server http://127.0.0.1:8001
```

Use `timeout: 300000` (5 minutes) — simulations can take a while with LLM calls.

### Step 4: Parse and report results

After the simulation completes, summarize:

```
Simulation Results:
━━━━━━━━━━━━━━━━━━━━━━━━━
Personas: <list>
Server: http://127.0.0.1:8001
LLM: groq

| Persona | Turns | Fields | Status |
|---------|-------|--------|--------|
| P1 動脈瘤 | 8 | 12/14 | PASS |
| P2 中風隨訪 | 6 | 10/14 | PASS |
| ...     | ... | ... | ... |

Total: X/Y passed
━━━━━━━━━━━━━━━━━━━━━━━━━
```

If any persona failed, show the failure details (which fields were missing,
any errors encountered).

### Step 5: Check for regressions

If previous simulation results exist in `reports/patient_sim/`, compare:
- Did any previously-passing persona now fail?
- Did field extraction counts drop?

Report regressions prominently:
"REGRESSION: P3 was passing (11/14 fields) but now fails (8/14 fields)"

## Available Patient Personas

| ID | Case | Focus |
|----|------|-------|
| P1 | Aneurysm | Standard neurosurgery intake |
| P2 | Stroke follow-up | Post-acute care |
| P3 | Carotid stenosis | Vascular neurology |
| P4 | AVM (anxious) | Patient anxiety handling |
| P5 | ICH recovery | Rehab phase |
| P6 | Headache differential | Broad differential diagnosis |
| P7 | Post-coiling meds | Medication management |
| P8 | Flow diverter (non-adherent) | Compliance challenges |
| P9 | Amaurosis fugax | Urgent referral |
| P10 | DAVF tinnitus | Rare presentation |

## Rules

- **Always port 8001** — never 8000 (AGENTS.md: "Test server runs on port 8001")
- **Default LLM: groq** — (AGENTS.md: "Default LLM provider for tests")
- **Don't auto-start server** — user controls lifecycle
- **Report results clearly** — this is the primary verification tool for agent behavior
