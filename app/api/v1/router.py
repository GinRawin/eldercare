from fastapi import APIRouter

from app.api.v1.endpoints import intake_logs, profiles, reminders, risk

router = APIRouter()
router.include_router(profiles.router)
router.include_router(risk.router)
router.include_router(intake_logs.router)
router.include_router(reminders.router)
