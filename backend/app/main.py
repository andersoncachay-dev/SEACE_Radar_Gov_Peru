from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .database import Base, engine
from .routers import (
    alerts,
    app_settings,
    auth,
    documents,
    legal_documents,
    opportunities,
    opportunity_reviews,
    opportunity_tracking,
    opportunity_view_states,
    radar_keywords,
    runs,
    search_profiles,
    tracking_areas,
    tracking_responsibles,
    tracking_templates,
    users,
)
from .services.run_service import reconcile_interrupted_runs
from .services.scheduler_service import start_scheduler, stop_scheduler


def create_app() -> FastAPI:
    if settings.auto_create_tables:
        Base.metadata.create_all(bind=engine)

    app = FastAPI(title=settings.app_name)
    origins = [origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def prevent_stale_api_responses(request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        response.headers["Vary"] = "Authorization"
        return response

    app.include_router(auth.router)
    app.include_router(users.router)
    app.include_router(search_profiles.router)
    app.include_router(radar_keywords.router)
    app.include_router(opportunities.router)
    app.include_router(opportunity_view_states.router)
    app.include_router(runs.router)
    app.include_router(alerts.router)
    app.include_router(documents.router)
    app.include_router(legal_documents.router)
    app.include_router(app_settings.router)
    app.include_router(tracking_areas.router)
    app.include_router(tracking_responsibles.router)
    app.include_router(tracking_templates.router)
    app.include_router(opportunity_tracking.router)
    app.include_router(opportunity_reviews.router)

    @app.get("/")
    def root():
        return {
            "name": settings.app_name,
            "docs": "/docs",
            "health": "/health",
        }

    @app.get("/health")
    def health():
        return {
            "status": "ok",
            "environment": settings.environment,
            "menor8_enabled": settings.enable_menor8_module,
            "scheduler_enabled": settings.enable_scheduler,
        }

    @app.on_event("startup")
    def on_startup():
        reconcile_interrupted_runs()
        start_scheduler()

    @app.on_event("shutdown")
    def on_shutdown():
        stop_scheduler()

    return app


app = create_app()
