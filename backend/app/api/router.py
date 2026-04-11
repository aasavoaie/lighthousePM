from fastapi import APIRouter

from app.api.admin import router as admin_router
from app.api.health import router as health_router
from app.api.issues import router as issues_router
from app.api.metrics import router as metrics_router
from app.api.releases import router as releases_router
from app.api.signals import router as signals_router
from app.api.sync import router as sync_router

api_router = APIRouter()
api_router.include_router(admin_router)
api_router.include_router(health_router)
api_router.include_router(releases_router)
api_router.include_router(issues_router)
api_router.include_router(metrics_router)
api_router.include_router(signals_router)
api_router.include_router(sync_router)
