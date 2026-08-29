from __future__ import annotations

import uvicorn

from backend.app.config import Settings


if __name__ == "__main__":
    settings = Settings.from_env()
    uvicorn.run("backend.app.main:app", host=settings.host, port=settings.port, reload=False)

