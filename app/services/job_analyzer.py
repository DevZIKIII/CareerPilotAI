import json

from pydantic import BaseModel, Field, field_validator
from sqlmodel import Session

from app.models import Analysis, Job, Resume
from app.services.openrouter_client import chat_json


class JobAnalysisResult(BaseModel):
    score: int = Field(ge=0, le=100)
    match_level: str
    worth_applying: bool
    strengths: list[str] = []
    weaknesses: list[str] = []
    keywords: list[str] = []
    missing_requirements: list[str] = []
    resume_adjustments: list[str] = []
    recommendation: str = ""
    email_subject: str = ""
    email_body: str = ""
    action_suggestion: str = ""

    @field_validator("match_level")
    @classmethod
    def normalize_match_level(cls, value: str) -> str:
        normalized = value.lower().strip()
        if normalized not in {"baixo", "medio", "alto"}:
            raise ValueError("match_level deve ser baixo, medio ou alto")
        return normalized


PROMPT_TEMPLATE = """Você é um assistente de carreira especializado em análise de compatibilidade entre currículo e vaga.

Analise o currículo e a descrição da vaga.

Regras:
- Não invente experiências.
- Não diga que o candidato sabe algo que não aparece no currículo.
- Pode sugerir melhorias de apresentação, mas não pode criar informação falsa.
- Se a vaga for boa, gere carta de apresentação curta e profissional.
- Se a vaga for de plataforma sensível, recomende aplicação manual.
- Responda somente JSON válido.
- Não use markdown.

Currículo:
{{RESUME_TEXT}}

Vaga:
{{JOB_DESCRIPTION}}

Canal detectado:
{{CHANNEL}}

Formato obrigatório:

{
  "score": 0,
  "match_level": "baixo|medio|alto",
  "worth_applying": true,
  "strengths": [],
  "weaknesses": [],
  "keywords": [],
  "missing_requirements": [],
  "resume_adjustments": [],
  "recommendation": "",
  "email_subject": "",
  "email_body": "",
  "action_suggestion": ""
}

REGRAS PARA O SCORE
- 0 a 39: baixo
- 40 a 69: medio
- 70 a 100: alto

REGRAS DE CANAL
Se channel = "email_auto":
- Gerar email_subject.
- Gerar email_body.
- action_suggestion deve indicar que pode ser enviado por e-mail se aprovado.

Se channel = "sensitive_platform":
- Não gerar instrução de automação.
- action_suggestion deve indicar: abrir o link manualmente, revisar os pontos recomendados e candidatar-se pela plataforma.

Se channel = "manual_review":
- action_suggestion deve indicar revisão manual antes de qualquer envio.
"""


def _match_level_from_score(score: int) -> str:
    if score <= 39:
        return "baixo"
    if score <= 69:
        return "medio"
    return "alto"


def analyze_job(session: Session, resume_id: int, job_id: int) -> Analysis:
    resume = session.get(Resume, resume_id)
    job = session.get(Job, job_id)
    if not resume:
        raise RuntimeError("Currículo não encontrado.")
    if not job:
        raise RuntimeError("Vaga não encontrada.")

    resume_context = (
        f"VERSÃO ESTRUTURADA DO CURRÍCULO:\n{resume.summary}\n\n"
        f"TEXTO BRUTO EXTRAÍDO PARA CONFERÊNCIA:\n{resume.raw_text}"
    )
    prompt = (
        PROMPT_TEMPLATE.replace("{{RESUME_TEXT}}", resume_context)
        .replace("{{JOB_DESCRIPTION}}", job.description)
        .replace("{{CHANNEL}}", job.channel)
    )
    result = JobAnalysisResult.model_validate(chat_json(prompt))
    result.match_level = _match_level_from_score(result.score)

    analysis = Analysis(
        job_id=job.id,
        resume_id=resume.id,
        score=result.score,
        match_level=result.match_level,
        worth_applying=result.worth_applying,
        strengths_json=json.dumps(result.strengths, ensure_ascii=False),
        weaknesses_json=json.dumps(result.weaknesses, ensure_ascii=False),
        keywords_json=json.dumps(result.keywords, ensure_ascii=False),
        missing_requirements_json=json.dumps(result.missing_requirements, ensure_ascii=False),
        resume_adjustments_json=json.dumps(result.resume_adjustments, ensure_ascii=False),
        recommendation=result.recommendation,
        email_subject=result.email_subject,
        email_body=result.email_body,
        action_suggestion=result.action_suggestion,
    )
    session.add(analysis)
    session.commit()
    session.refresh(analysis)
    return analysis
