# API Contract Tightening — Known Debt

**Goal**: Add explicit response models and align wire contracts across channels so OpenAPI docs are accurate and Pydantic validates outbound payloads.

## Issues

### 1. Patient-switch notification dropped on web/mini (High)

Shared handlers produce `switch_notification` on patient switches, and the web adapter formats it into the reply text. But `routers/records.py:ChatResponse` does not declare the field, so `_handler_result_to_chat()` silently drops it. Mini chat reuses the same model. Voice (`VoiceChatResponse`) does declare it.

**Fix**: Add `switch_notification: Optional[str] = None` to `ChatResponse`.

**Files**: `routers/records.py`, `routers/miniprogram.py`, `services/domain/adapters/web_adapter.py`

### 2. Mini list endpoints leak UI payload shape (Medium)

`GET /api/mini/patients` and `GET /api/mini/records` directly forward the UI helpers, which return cursor/pagination payloads (`next_cursor`, `items`, `total`, `limit`, `offset`). The mini routes don't accept cursor/offset params, so the pagination contract is incomplete and the response shape is whatever the workbench helper currently returns.

**Fix**: Define mini-specific response models or at minimum accept the pagination params and document the shape.

**Files**: `routers/miniprogram.py:116,217`, `routers/ui/__init__.py`, `routers/ui/record_handlers.py`

### 3. Mini CRUD returns untyped dicts (Medium)

`POST /api/mini/patients`, `PATCH /api/mini/patients/{id}`, `POST /api/mini/patients/{id}/access-code`, `POST /api/mini/records`, and `GET /api/mini/me` all return ad-hoc `dict` responses assembled in the route body. FastAPI does not validate or document these schemas.

**Fix**: Add `response_model=` with Pydantic models for each endpoint.

**Files**: `routers/miniprogram.py:127,147,187,236,352`

### 4. Neuro from-text has no response model (Medium)

`POST /api/neuro/from-text` returns `{"case": ..., "log": ..., "db_id": ...}` via `model_dump()` with no declared response model. The OpenAPI schema is missing and the contract silently follows internal model changes.

**Fix**: Define a `NeuroFromTextResponse` Pydantic model.

**Files**: `routers/neuro.py:34`

## When to address

These are API design tasks, not security or correctness fixes. Address during a dedicated API contract review with client-side coordination to avoid breaking existing mini-program and web clients.
