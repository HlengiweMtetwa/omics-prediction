"""FastAPI backend - a second presentation layer over ai_wasteguard,
proving the same services used by the Streamlit app work independently
of it. Run with: uvicorn api.main:app --reload
"""
import logging
import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.routers import admin, auth, dashboard, jobs, models, projects, reports, sites_and_sampling, uploads

logger = logging.getLogger("ai_wasteguard.api")

app = FastAPI(
    title="AI-WasteGuard API",
    version="0.1.0",
    description=(
        "Reference API over the ai_wasteguard registry/auth/job/report/model "
        "services. This is an early, partial surface - see README.md for "
        "what is and isn't covered yet."
    ),
)

# Narrow by default: only origins explicitly listed via CORS_ALLOWED_ORIGINS
# (comma-separated) are permitted. Empty by default - same-origin/non-browser
# clients (curl, server-to-server) are unaffected either way.
_allowed_origins = [o.strip() for o in os.environ.get("CORS_ALLOWED_ORIGINS", "").split(",") if o.strip()]
if _allowed_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(projects.router)
app.include_router(sites_and_sampling.router)
app.include_router(uploads.router)
app.include_router(jobs.router)
app.include_router(reports.router)
app.include_router(models.router)
app.include_router(admin.router)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    # Never leak internal stack traces / exception details to API clients.
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error."})


@app.get("/api/v1/health", tags=["health"])
def health() -> dict:
    return {"status": "ok"}
