"""Speech transcription routes (REST + WebSocket)."""
from channels.web.transcribe.ws import router as ws_router  # noqa: F401
from channels.web.transcribe.routes import router as rest_router  # noqa: F401
