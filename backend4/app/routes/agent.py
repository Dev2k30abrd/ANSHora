import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.agents.agent import run_agent, run_agent_stream
from app.core import db
from app.core.jsonutil import jsonable
from app.llm.client import LLMError, LLMAuthError, LLMQuotaError, LLMRateLimitError, LLMTimeoutError
from app.services.dataset_manager import DatasetNotFoundError, dataset_store

router = APIRouter(prefix="/api/agent", tags=["AI Agent"])


class HistoryMessage(BaseModel):
    role: str
    content: str


class AgentQuery(BaseModel):
    question: str
    dataset_id: str
    history: list[HistoryMessage] = []
    pending_action: dict | None = None


def project_for(dataset_id: str):
    meta = dataset_store.get_meta(dataset_id)
    if meta.get("project_id"):
        return db.one("SELECT * FROM projects WHERE id=?", (meta["project_id"],))
    return None


@router.post("/query")
def query_agent(req: AgentQuery):
    try:
        res = run_agent(
            req.question,
            req.dataset_id,
            [h.model_dump() for h in req.history],
            project_for(req.dataset_id),
            pending_action=req.pending_action,
        )
        return jsonable(res)
    except DatasetNotFoundError as e:
        raise HTTPException(404, str(e))
    except LLMAuthError as e:
        raise HTTPException(502, str(e))
    except LLMQuotaError as e:
        raise HTTPException(402, str(e))
    except LLMRateLimitError as e:
        raise HTTPException(429, str(e))
    except LLMTimeoutError as e:
        raise HTTPException(504, str(e))
    except LLMError as e:
        raise HTTPException(getattr(e, "status_code", 502), str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, f"Error processing query: {e}")


def sse(ev: dict) -> str:
    return f"data: {json.dumps(jsonable(ev))}\n\n"


@router.post("/stream")
def stream_query(req: AgentQuery):
    try:
        proj = project_for(req.dataset_id)
    except DatasetNotFoundError as e:
        raise HTTPException(404, str(e))

    def gen():
        try:
            for ev in run_agent_stream(
                req.question,
                req.dataset_id,
                [h.model_dump() for h in req.history],
                proj,
                pending_action=req.pending_action,
            ):
                yield sse(ev)
        except Exception as e:  # noqa: BLE001
            yield sse({"type": "error", "message": str(e)})

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
