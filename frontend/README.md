# React + Material UI Frontend

This folder contains a Vite + React + MUI frontend that talks to the existing FastAPI backend.

## Prerequisites

- Backend running on `http://127.0.0.1:8000`
- Node.js 18+ and npm

## Start

1. Start backend (from repo root):

```bash
.venv/bin/uvicorn main:app --reload --port 8000
```

2. Start frontend (new terminal):

```bash
cd frontend
npm install
npm run dev
```

3. Open:

- `http://127.0.0.1:5173/` for Chat
- `http://127.0.0.1:5173/manage` for Manage

## API Notes

- Vite dev server proxies `/api/*` to `http://127.0.0.1:8000` (see `vite.config.js`).
- No backend CORS changes are needed for local development with this proxy.
