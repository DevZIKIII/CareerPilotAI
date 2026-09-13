import mimetypes
import os
import smtplib
from email.message import EmailMessage
from pathlib import Path


def _smtp_config() -> dict:
    config = {
        "host": os.getenv("SMTP_HOST"),
        "port": os.getenv("SMTP_PORT"),
        "user": os.getenv("SMTP_USER"),
        "password": os.getenv("SMTP_PASSWORD"),
        "from_email": os.getenv("FROM_EMAIL"),
    }
    missing = [key for key, value in config.items() if not value]
    if missing:
        raise RuntimeError(f"Configuração SMTP incompleta. Faltando: {', '.join(missing)}.")
    config["port"] = int(config["port"])
    return config


def send_application_email(
    to_email: str,
    subject: str,
    body: str,
    resume_path: str,
    channel: str,
) -> None:
    if channel == "sensitive_platform":
        raise RuntimeError("Esta vaga está em plataforma sensível. Abra o link e candidate-se manualmente.")
    if channel != "email_auto":
        raise RuntimeError("Envio automático permitido apenas para vagas com e-mail direto.")
    if not to_email:
        raise RuntimeError("A vaga não possui e-mail de contato.")

    config = _smtp_config()
    message = EmailMessage()
    message["From"] = config["from_email"]
    message["To"] = to_email
    message["Subject"] = subject or "Candidatura"
    message.set_content(body or "Olá, segue minha candidatura em anexo.")

    resume = Path(resume_path)
    if not resume.exists():
        raise RuntimeError("Arquivo de currículo não encontrado para anexo.")

    mime_type, _ = mimetypes.guess_type(resume.name)
    maintype, subtype = (mime_type or "application/octet-stream").split("/", 1)
    message.add_attachment(
        resume.read_bytes(),
        maintype=maintype,
        subtype=subtype,
        filename=resume.name,
    )

    with smtplib.SMTP(config["host"], config["port"]) as smtp:
        smtp.starttls()
        smtp.login(config["user"], config["password"])
        smtp.send_message(message)
