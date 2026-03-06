# Config Module

Purpose:
- Runtime configuration source files loaded by the server.

Key file:
- `runtime.json`: local runtime config (generated/edited locally, not tracked in git).
- `runtime.json.sample`: committed sample you can copy to `runtime.json`.

Notes:
- The project uses JSON runtime config (not `.env`) as the primary configurable source.
