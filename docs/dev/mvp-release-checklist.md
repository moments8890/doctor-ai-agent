# MVP Release Checklist

Every release candidate must pass all items below before merging or pushing to
`main`.

---

## 1. Unit tests

```bash
bash scripts/test.sh unit
```

- [ ] 100% green (0 failures)
- [ ] Overall coverage >80%
- [ ] Diff-cover on changed/new lines >80%:

```bash
git fetch --no-tags origin main
.venv/bin/diff-cover reports/coverage/coverage.xml \
  --compare-branch=origin/main --diff-range-notation=.. --fail-under=81
```

## 2. MVP hero-loop benchmark

This gate is only runnable when the local benchmark assets are installed:

- dataset files under `e2e/fixtures/data/`
- at least one saved baseline under `reports/baseline/`

```bash
bash scripts/test.sh hero-loop
```

Runs against the dedicated `:8001` benchmark server. Produces
`reports/candidate/hero.json` and compares it to the latest saved baseline.

- [ ] Hero-loop cases pass with `--fail-on-regression`
- [ ] No new failures in candidate vs baseline

### Benchmark dimensions (all must be non-regressing)

| Dimension | Description |
|---|---|
| Patient binding correctness | Patient identified/created as expected |
| Pending-draft lifecycle correctness | Draft created, confirmed, or abandoned correctly |
| Compound-intent handling correctness | Allowed combos execute; unsupported combos clarify |
| Query success rate | Query returns expected results without write side effects |
| Fatal error rate | Must be 0 |

Regression in any of these dimensions is a **release blocker**.
If the benchmark assets are missing in the local clone, mark the release as
**benchmark-blocked by missing fixtures**, not product-green.

## 3. Integration tests (when LLM pipeline changed)

```bash
./cli.py start --port 8001 --no-frontend &
bash scripts/test.sh integration-full
```

- [ ] No new failures vs previous run
- [ ] Required only when routing, prompts, context assembly, or structuring changed

## 4. Architecture docs

- [ ] `ARCHITECTURE.md` updated if schema, endpoints, env vars, or service structure changed

## 5. Baseline saved

```bash
bash scripts/save_baseline.sh
```

- [ ] Baseline artifact saved after passing all gates above

---

## Baseline artifact convention

- **Location**: `reports/baseline/`
- **Naming**: `{git-sha}-hero.json` (default from `save_baseline.sh`) or `{custom-name}-hero.json`
- **Source**: copied from `reports/candidate/hero.json` after a passing run
- Every release candidate must have a saved baseline before pushing
- See `scripts/save_baseline.sh` and `scripts/compare_baseline.py` for details

## Regression policy

1. Any regression in the 5 benchmark dimensions listed above = **release blocker**.
2. P1 work must prove it does not degrade P0 hero-loop behavior:
   - Run `bash scripts/test.sh hero-loop` **before** and **after** the change.
   - Include the comparison output in the commit message or PR description.
3. If a regression is **intentional** (deliberate behavior change):
   - Update the baseline: `bash scripts/save_baseline.sh`
   - Document why in the commit message (e.g. "baseline updated: changed draft confirmation wording").
4. Benchmark comparison details are documented in [`tests/README.md`](../../tests/README.md).

## Quick reference

| Gate | Command | When |
|---|---|---|
| Frontend smoke | `cd frontend/web && npm run build` | Every push |
| Unit tests | `bash scripts/test.sh unit` | Deterministic/domain-heavy changes |
| Diff-cover | `.venv/bin/diff-cover ...` | Every push |
| Hero-loop benchmark | `bash scripts/test.sh hero-loop` | When local benchmark dataset + baseline are installed |
| Integration tests | `bash scripts/test.sh integration-full` | Every push that changes backend/LLM workflow |
| Save baseline | `bash scripts/save_baseline.sh` | After a passing benchmark run |
