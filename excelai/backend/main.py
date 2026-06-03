from __future__ import annotations

import os
import sys
from pathlib import Path

# Ensure the parent of 'backend/' is on sys.path so "from backend.xxx" imports work on Vercel
_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from backend.routes.auth import router as auth_router
from backend.routes.extract import router as extract_router
from backend.routes.export import router as export_router
from backend.routes.export_pdf import router as export_pdf_router
from backend.routes.workbook import router as workbook_router

BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = Path(_PROJECT_ROOT) / "frontend"

# Load environment variables from .env file (development) or system env (production)
env_file = BASE_DIR / ".env"
if env_file.exists():
    load_dotenv(env_file)

app = FastAPI(title="ExcelAI", version="1.0.0")

allowed_origins = [origin.strip() for origin in os.getenv("CORS_ORIGINS", "*").split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if "*" in allowed_origins else allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(extract_router)
app.include_router(export_router)
app.include_router(export_pdf_router)
app.include_router(workbook_router)

# Mount static files
if FRONTEND_DIR.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIR / "assets"), name="assets")
    app.mount("/css", StaticFiles(directory=FRONTEND_DIR / "css"), name="css")
    app.mount("/js", StaticFiles(directory=FRONTEND_DIR / "js"), name="js")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "ExcelAI"}


@app.get("/favicon.ico", response_model=None)
async def favicon() -> Response:
    """Return 204 No Content for favicon requests (silently handled by browser)"""
    return Response(status_code=204)


@app.get("/favicon.png", response_model=None)
async def favicon_png() -> Response:
    """Return 204 No Content for favicon requests (silently handled by browser)"""
    return Response(status_code=204)


@app.get("/robots.txt")
async def robots() -> Response:
    """Return 204 No Content for robots.txt requests"""
    return Response(status_code=204)


@app.get("/", response_model=None)
async def root() -> Response:
    """Serve index.html for root path"""
    index_path = FRONTEND_DIR / "index.html"
    if index_path.exists():
        return FileResponse(index_path, media_type="text/html")
    return JSONResponse(status_code=404, content={"error": "Frontend not found"})


@app.exception_handler(HTTPException)
async def http_exception_handler(_: Request, exc: HTTPException) -> JSONResponse:
    detail = exc.detail
    if isinstance(detail, dict):
        error = str(detail.get("error") or "Request failed")
        message = str(detail.get("detail") or detail.get("message") or "")
    else:
        error = "Request failed"
        message = str(detail)
    return JSONResponse(status_code=exc.status_code, content={"error": error, "detail": message})


@app.exception_handler(Exception)
async def generic_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=500, content={"error": "Internal server error", "detail": str(exc)})


@app.get("/{full_path:path}", response_model=None)
async def serve_frontend(full_path: str) -> Response:
    """Catch-all route to serve frontend files or index.html for client-side routing"""
    # Skip API routes
    if full_path.startswith("api/"):
        return JSONResponse(status_code=404, content={"error": "API endpoint not found"})
    
    # Try to serve the file directly
    file_path = FRONTEND_DIR / full_path
    if file_path.exists() and file_path.is_file():
        media_type = None
        if str(file_path).endswith(".html"):
            media_type = "text/html"
        elif str(file_path).endswith(".svg"):
            media_type = "image/svg+xml"
        elif str(file_path).endswith(".css"):
            media_type = "text/css"
        elif str(file_path).endswith(".js"):
            media_type = "application/javascript"
        return FileResponse(file_path, media_type=media_type)
    
    # For SPA client-side routing, serve index.html
    index_path = FRONTEND_DIR / "index.html"
    if index_path.exists() and not full_path.endswith((".css", ".js", ".svg", ".png", ".jpg", ".gif")):
        return FileResponse(index_path, media_type="text/html")
    
    return JSONResponse(status_code=404, content={"error": "Not found"})
