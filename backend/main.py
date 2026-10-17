"""Sehat Saathi Backend Main Application.
FastAPI setup with CORS, lifespan startup verification, and router mounts.
"""
import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.config import settings
from backend.database import init_db_sync
from backend.api.routes_patient import router as patient_router
from backend.api.routes_pairing import router as pairing_router
from backend.api.routes_caregiver import router as caregiver_router
from backend.api.routes_internal import router as internal_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("sehat_saathi")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # PR-11: Validate configuration on startup
    logger.info("Validating provider configuration...")
    settings.validate_provider_configs()
    logger.info(f"AI Provider Active: {settings.AI_PROVIDER} (Fallback: {settings.FALLBACK_PROVIDER})")

    # Initialize SQLite database and seed synthetic summary
    logger.info("Initializing SQLite database...")
    init_db_sync()
    logger.info("Database initialized with synthetic data.")

    yield

    logger.info("Shutting down Sehat Saathi backend.")


app = FastAPI(
    title="Sehat Saathi Backend (English-only Edition)",
    description="Voice-first discharge-instruction assistant backend with patient-controlled caregiver access and swappable AI providers.",
    version="1.1.0",
    lifespan=lifespan
)

# CORS Middleware for PWA and Mobile Web Clients
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static audio placeholder directory
static_audio_dir = os.path.join(os.path.dirname(__file__), "static", "audio")
os.makedirs(static_audio_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static")), name="static")

from backend.api.routes_prescriptions import router as prescriptions_router
from backend.api.routes_doctor import router as doctor_router

# Mount API Routers
app.include_router(patient_router)
app.include_router(pairing_router)
app.include_router(caregiver_router)
app.include_router(prescriptions_router)
app.include_router(doctor_router)
app.include_router(internal_router)

# Mount frontend PWA if built
frontend_dist = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend", "dist"))
if os.path.exists(frontend_dist):
    app.mount("/app", StaticFiles(directory=frontend_dist, html=True), name="frontend")


@app.get("/")
def read_root():
    return {
        "app": "Sehat Saathi Backend",
        "edition": "English-only v1.1",
        "status": "online",
        "docs_url": "/docs"
    }


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
