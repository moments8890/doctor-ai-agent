# Tests Module

Purpose:
- Unit and component tests that run without real external services.

Layout:
- `conftest.py`: shared fixtures/mocks for test environment.
- `test_*.py`: unit/component coverage for db/services/routers/utils.
- `fixtures/`: reusable static fixtures and test data used by unit tests.

Execution:
- Main unit run: `./dev.sh test unit`

Notes:
- End-to-end/integration tests are in `../e2e/`.
