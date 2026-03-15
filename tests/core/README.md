# Core E2E Tests

This folder contains non-WeChat E2E tests focused on core application behavior.

Files:
- `test_multi_gateway_e2e.py`: verifies one doctor/patient flow across text + voice gateways shares DB state.
- `test_p3_d2_parity_e2e.py`: smoke/parity chain for risk/task/notification pipeline behavior.

Run:

```bash
./dev.sh test unit
.venv/bin/python -m pytest tests/core/ -v
```

These tests reuse local test fixtures and do not require a running server/Ollama.
