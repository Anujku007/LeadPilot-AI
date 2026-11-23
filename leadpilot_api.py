from typing import Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from leadpilot_ai.nvidia_llm_service import NvidiaLLMService
from leadpilot_ai.lead_qualification import router as lead_router
from leadpilot_ai.lead_extraction import router as extraction_router
from leadpilot_ai.conversation_api import router as conversation_router
from leadpilot_ai.smart_conversation import router as smart_conversation_router
from leadpilot_ai.dashboard_api import router as dashboard_router
from leadpilot_ai.sales_pipeline_api import router as sales_pipeline_router
from leadpilot_ai.sales_insights_api import router as sales_insights_router
from leadpilot_ai.voice_api import router as voice_router
from leadpilot_ai.calendar_availability import router as calendar_router
from leadpilot_ai.appointment_booking import router as booking_router
from leadpilot_ai.appointment_workflow import router as workflow_router
from leadpilot_ai.appointment_confirmation import router as confirmation_router
from leadpilot_ai.natural_language_scheduling import router as scheduling_router
from leadpilot_ai.twilio_stream import router as twilio_router
from leadpilot_ai.twilio_playback_local import router as playback_router
from leadpilot_ai.twilio_duplex_local import router as duplex_router
from leadpilot_ai.twilio_paced_local import router as paced_router
from leadpilot_ai.twilio_live_local import router as live_router

app = FastAPI(title="LeadPilot AI API", version="0.1.0")

nvidia = NvidiaLLMService()


class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    history: list[Message] = Field(
        default_factory=list,
        max_length=20
    )


@app.get("/health")
async def health():
    return {"status": "ok", "service": "LeadPilot AI"}


@app.post("/api/chat")
async def chat(request: ChatRequest):
    try:
        history = [
            item.model_dump()
            for item in request.history
        ]

        answer = await nvidia.generate_response(
            message=request.message,
            history=history
        )

        return {
            "success": True,
            "reply": answer,
            "model": nvidia.model
        }

    except Exception as error:
        print("NVIDIA service error:", type(error).__name__)
        raise HTTPException(
            status_code=502,
            detail="NVIDIA request failed. Check server logs."
        ) from error


app.include_router(lead_router)
app.include_router(extraction_router)
app.include_router(conversation_router)
app.include_router(smart_conversation_router)
app.include_router(dashboard_router)
app.include_router(sales_pipeline_router)
app.include_router(sales_insights_router)
app.include_router(voice_router)
app.include_router(calendar_router)
app.include_router(booking_router)
app.include_router(workflow_router)
app.include_router(confirmation_router)
app.include_router(scheduling_router)
app.include_router(twilio_router)
app.include_router(playback_router)
app.include_router(duplex_router)
app.include_router(paced_router)
app.include_router(live_router)


# LEADPILOT_AUTH_V1 - protects FastAPI API and docs
from starlette.middleware.base import BaseHTTPMiddleware
from leadpilot_ai.auth_api import router as auth_router, auth_middleware
from leadpilot_ai.team_access import router as team_router

app.include_router(auth_router)
app.include_router(team_router)
app.add_middleware(BaseHTTPMiddleware, dispatch=auth_middleware)
