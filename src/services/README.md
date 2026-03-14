# Services Module

Purpose:
- Core business logic (intent routing, structuring, session/memory, notifications, tasks, runtime config).

Key areas:
- AI pipeline: `agent.py`, `intent.py`, `structuring.py`, `vision.py`, `transcription.py`.
- Conversation/session: `session.py`, `memory.py`, `interview.py`.
- Tasking/notify: `tasks.py`, `notification.py`, `notify_control.py`, `wechat_notify.py`.
- Runtime/config: `runtime_config.py`, `observability.py`.
- WeChat domain logic: `wechat_domain.py`, `wecom_kf_sync.py`, `wechat_media_pipeline.py`.

Notes:
- Keep side effects and external calls centralized here (not in routers).
