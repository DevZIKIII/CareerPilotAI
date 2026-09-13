from app.config import SENSITIVE_DOMAINS


def classify_channel(job_url: str | None, contact_email: str | None) -> str:
    if contact_email and contact_email.strip():
        return "email_auto"

    normalized_url = (job_url or "").lower()
    if any(domain in normalized_url for domain in SENSITIVE_DOMAINS):
        return "sensitive_platform"

    return "manual_review"
