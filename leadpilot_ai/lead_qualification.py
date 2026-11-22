from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api/leads", tags=["Leads"])


class LeadInput(BaseModel):
    budget: Literal[
        "confirmed", "limited", "unknown"
    ] = "unknown"

    authority: Literal[
        "decision_maker", "influencer", "unknown"
    ] = "unknown"

    need: Literal[
        "clear", "partial", "unknown"
    ] = "unknown"

    timeline: Literal[
        "within_30_days",
        "within_90_days",
        "later",
        "unknown"
    ] = "unknown"


SCORES = {
    "budget": {
        "confirmed": 25,
        "limited": 10,
        "unknown": 0
    },
    "authority": {
        "decision_maker": 25,
        "influencer": 10,
        "unknown": 0
    },
    "need": {
        "clear": 25,
        "partial": 10,
        "unknown": 0
    },
    "timeline": {
        "within_30_days": 25,
        "within_90_days": 15,
        "later": 5,
        "unknown": 0
    }
}


QUESTIONS = {
    "budget": "Do you have an allocated budget?",
    "authority": "Who makes the purchasing decision?",
    "need": "What problem do you want to solve?",
    "timeline": "When are you planning to implement a solution?"
}


@router.post("/score")
async def score_lead(lead: LeadInput):
    values = lead.model_dump()

    breakdown = {
        field: SCORES[field][value]
        for field, value in values.items()
    }

    score = sum(breakdown.values())

    if score >= 75:
        category = "Hot"
    elif score >= 40:
        category = "Warm"
    else:
        category = "Cold"

    next_question = None

    for field, value in values.items():
        if value == "unknown":
            next_question = QUESTIONS[field]
            break

    return {
        "success": True,
        "score": score,
        "category": category,
        "breakdown": breakdown,
        "next_question": next_question,
        "method": "rule_based_bant_v1"
    }
