import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from .database import init_db
from .config import config
from .routers import projects, documents, chat, reports, voice


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    os.makedirs(config.DATA_DIR, exist_ok=True)
    os.makedirs(config.projects_dir, exist_ok=True)
    os.makedirs(config.chroma_dir, exist_ok=True)
    await init_db()
    yield
    # Shutdown (nothing to clean up)


app = FastAPI(
    title="Strategic Property AI Assistant",
    version="1.0.0",
    lifespan=lifespan,
)

# API routes
app.include_router(projects.router, prefix="/api/projects", tags=["projects"])
app.include_router(documents.router, prefix="/api/documents", tags=["documents"])
app.include_router(chat.router, prefix="/api/chat", tags=["chat"])
app.include_router(reports.router, prefix="/api/reports", tags=["reports"])
app.include_router(voice.router, prefix="/api/voice", tags=["voice"])

# Serve frontend static files
_frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend")
_frontend_dir = os.path.abspath(_frontend_dir)

app.mount("/static", StaticFiles(directory=_frontend_dir), name="static")


@app.get("/")
async def serve_frontend():
    return FileResponse(os.path.join(_frontend_dir, "index.html"))


# PWA required files at root paths (browsers fetch these without /static/ prefix)
@app.get("/sw.js")
async def service_worker():
    return FileResponse(
        os.path.join(_frontend_dir, "sw.js"),
        media_type="application/javascript",
        headers={"Service-Worker-Allowed": "/"},
    )


@app.get("/manifest.json")
async def manifest():
    return FileResponse(
        os.path.join(_frontend_dir, "manifest.json"),
        media_type="application/manifest+json",
    )


@app.get("/{path:path}")
async def catch_all(path: str):
    # Serve index.html for any non-API route (SPA support)
    index = os.path.join(_frontend_dir, "index.html")
    return FileResponse(index)
