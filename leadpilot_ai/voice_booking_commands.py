import re
from datetime import datetime, timezone, timedelta


def clean(text):
    return " ".join(
        re.sub(r"[^a-z0-9 ]", " ", text.lower()).split()
    )


def is_confirmation(text):
    return clean(text) in {
        "confirm booking",
        "confirm the booking",
        "yes confirm booking",
        "yes confirm the booking",
    }


def is_cancel(text):
    return clean(text) in {
        "cancel", "cancel it", "cancel booking",
        "no", "no thanks", "not now",
        "do not book", "don t book",
    }


def is_change(text):
    return clean(text) in {
        "change time", "change the time",
        "different time", "another time",
        "another slot", "choose another time",
    }


def is_agreement(text):
    return clean(text) in {
        "yes", "yes please", "sure", "okay", "ok"
    }



def is_schedule_request(text):
    normalized = clean(text)

    action = re.search(
        r"\b(?:schedule|scheduling|book|booking|"
        r"arrange|reserve|set up)\b",
        normalized
    )

    subject = re.search(
        r"\b(?:appointment|meeting|consultation|"
        r"consultant|call|demo|slot)\b",
        normalized
    )

    timing = re.search(
        r"\b(?:today|tomorrow|monday|tuesday|"
        r"wednesday|thursday|friday|saturday|sunday|"
        r"morning|afternoon|evening|am|pm)\b"
        r"|\b\d{1,2}\b",
        normalized
    )

    return bool(action and (subject or timing))


def is_email_input(text):
    return bool(re.search(
        r"\b(?:email|e[\s-]?mail|inbox)\b",
        text.lower()
    ))


def guard_email_delivery_reply(reply):
    normalized = clean(reply)

    unsupported = (
        "i ve sent",
        "i have sent",
        "i sent",
        "i will send",
        "i ll send",
        "can send you",
        "calendar link",
        "calendar invite",
        "email address",
        "share your email",
        "provide your email",
        "check your inbox",
    )

    if any(item in normalized for item in unsupported):
        return (
            "I can help you find an available "
            "30-minute consultation. "
            "No email or calendar link has been sent. "
            "What date and time would you prefer in IST?",
            True
        )

    return reply, False



def spoken_slot(start_iso):
    ist = timezone(timedelta(hours=5, minutes=30))
    value = datetime.fromisoformat(start_iso)
    return value.astimezone(ist).strftime(
        "%A, %d %B at %I:%M %p IST"
    )

# LeadPilot voice scheduling safety patch v1
