# Routers Module

Purpose:
- FastAPI route handlers for API, WeChat, admin data views, and task endpoints.

Key files:
- `records.py`: main doctor chat/input endpoints (`/api/records/...`).
- `wechat.py`: WeChat/WeCom message entrypoint and dispatch.
- `ui.py`: admin/system data endpoints for frontend.
- `tasks.py`: task operations and task-related APIs.
- `voice.py`: voice upload/transcription-facing routes.
- `neuro.py`: neuro-specific record routes.

Notes:
- Routers should stay thin and delegate business logic to `services/`.
