from datetime import datetime

from sqlmodel import Session

from app.models import Analysis, Application, Job, Resume
from app.services.email_sender import send_application_email


def create_application(session: Session, analysis_id: int) -> Application:
    analysis = session.get(Analysis, analysis_id)
    if not analysis:
        raise RuntimeError("Análise não encontrada.")
    job = session.get(Job, analysis.job_id)
    if not job:
        raise RuntimeError("Vaga não encontrada.")

    status_by_channel = {
        "email_auto": "queued",
        "sensitive_platform": "manual_required",
        "manual_review": "draft",
    }
    application = Application(
        job_id=job.id,
        analysis_id=analysis.id,
        status=status_by_channel.get(job.channel, "draft"),
        channel=job.channel,
        sent_to=job.contact_email if job.channel == "email_auto" else "",
    )
    session.add(application)
    session.commit()
    session.refresh(application)
    return application


def send_application(session: Session, application_id: int) -> Application:
    application = session.get(Application, application_id)
    if not application:
        raise RuntimeError("Candidatura não encontrada.")

    job = session.get(Job, application.job_id)
    analysis = session.get(Analysis, application.analysis_id)
    if not job or not analysis:
        raise RuntimeError("Dados da candidatura incompletos.")
    resume = session.get(Resume, analysis.resume_id)
    if not resume:
        raise RuntimeError("Currículo da análise não encontrado.")

    send_application_email(
        to_email=job.contact_email,
        subject=analysis.email_subject,
        body=analysis.email_body,
        resume_path=resume.file_path,
        channel=job.channel,
    )
    application.status = "sent"
    application.sent_to = job.contact_email
    application.sent_at = datetime.utcnow()
    session.add(application)
    session.commit()
    session.refresh(application)
    return application
