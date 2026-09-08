from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import json

from app.agents.analytics_agent import (
    run_analytics_agent,
    stream_analytics_agent,
    AIServiceError,
)
from app.services.dataset_manager import DatasetNotFoundError


router = APIRouter(prefix="/api/agent", tags=["AI Agent"])


class HistoryMessage(BaseModel):
    role: str
    content: str


class AgentQuery(BaseModel):
    question: str
    dataset_id: str
    history: list[HistoryMessage] = []


@router.post("/query")
def query_agent(request: AgentQuery):
    try:
        result = run_analytics_agent(
            request.question,
            request.dataset_id,
            [h.dict() for h in request.history],
        )
        return result

    except DatasetNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error))
    except AIServiceError as error:
        raise HTTPException(status_code=503, detail=str(error))
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error))


@router.post("/stream")
def stream_query_agent(request: AgentQuery):
    def generate():
        try:
            for event in stream_analytics_agent(
                request.question,
                request.dataset_id,
                [h.dict() for h in request.history],
            ):
                yield f"data: {json.dumps(event)}\n\n"

        except Exception as error:
            yield f"data: {json.dumps({'type': 'error', 'message': str(error)})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
