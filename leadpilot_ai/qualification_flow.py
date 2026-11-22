from .lead_qualification import SCORES, QUESTIONS

FIELDS = ("budget", "authority", "need", "timeline")


def merge_qualification(previous, extracted):
    values = {}

    for field in FIELDS:
        old = (previous or {}).get(field, "unknown")
        new = (extracted or {}).get(field, "unknown")

        if old not in SCORES[field]:
            old = "unknown"

        if new in SCORES[field] and new != "unknown":
            values[field] = new
        else:
            values[field] = old

    breakdown = {
        field: SCORES[field][value]
        for field, value in values.items()
    }

    score = sum(breakdown.values())

    missing = [
        field for field in FIELDS
        if values[field] == "unknown"
    ]

    if missing:
        category = "Incomplete"
    elif score >= 75:
        category = "Hot"
    elif score >= 40:
        category = "Warm"
    else:
        category = "Cold"

    next_question = (
        QUESTIONS[missing[0]] if missing else None
    )

    return {
        "success": True,
        "extracted": values,
        "score": score,
        "category": category,
        "breakdown": breakdown,
        "missing_fields": missing,
        "next_question": next_question,
        "method": "nvidia_bant_stateful_v2"
    }


def prompt_for_lead(qualification):
    values = qualification["extracted"]

    known = "\n".join(
        f"- {field}: {values[field]}"
        for field in FIELDS
    )

    next_question = qualification["next_question"]

    if next_question:
        instruction = (
            "Acknowledge the customer's latest statement. "
            "Ask exactly one follow-up question: "
            + next_question
            + " Do not ask other questions."
        )
    else:
        instruction = (
            "The lead's BANT information is complete. "
            "Briefly acknowledge their needs. "
            "Offer a 30-minute sales consultation "
            "and ask whether they want to schedule it. "
            "Do not repeat qualification questions."
        )

    return (
        "You are LeadPilot AI, a professional "
        "AI sales qualification assistant.\n"
        "Known BANT information:\n"
        + known
        + "\nInstructions:\n"
        + instruction
        + "\nNever invent prices, appointment slots, "
        "or product features. Never claim an "
        "appointment is booked because no booking "
        "tool is connected yet. Be concise."
    )


# LeadPilot voice scheduling safety patch v1
_original_prompt_for_lead = prompt_for_lead


def prompt_for_lead(*args, **kwargs):
    prompt = _original_prompt_for_lead(*args, **kwargs)

    if not isinstance(prompt, str):
        return prompt

    return prompt + (
        "\nIMPORTANT CAPABILITY LIMITS: "
        "You cannot send emails, calendar links, or "
        "calendar invitations. Never claim that an "
        "email or invite was sent. Do not ask for an "
        "email address for scheduling. "
        "Appointment tools are separate from this "
        "chat response. Never claim that an appointment "
        "has been booked without a confirmed tool result. "
        "For scheduling, ask the customer to choose "
        "a date and time in IST."
    )
