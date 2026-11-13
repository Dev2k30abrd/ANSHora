from fastapi import APIRouter

from app.core import config as cfg
from app.packs import get_pack, list_packs

router = APIRouter(prefix="/api", tags=["System"])


@router.get("/system/status")
def status():
    return {
        "name": "Anshora Analyst", "version": "1.0.0", "auth_required": cfg.AUTH_REQUIRED,
        "registration_open": cfg.ALLOW_REGISTRATION,
        "llm": {"mode": "demo" if cfg.use_mock_llm() else "live",
                "model": None if cfg.use_mock_llm() else cfg.LLM_MODEL, "tool_mode": cfg.TOOL_MODE},
        "features": {"python_sandbox": cfg.ENABLE_PYTHON_SANDBOX, "scheduler": cfg.ENABLE_SCHEDULER,
                     "default_currency": cfg.DEFAULT_CURRENCY},
    }


@router.get("/packs")
def packs():
    return {"packs": list_packs()}


@router.get("/packs/{pack_id}")
def pack(pack_id: str):
    return get_pack(pack_id)
