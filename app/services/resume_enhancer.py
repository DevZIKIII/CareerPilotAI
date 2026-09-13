from pydantic import BaseModel, Field

from app.services.openrouter_client import chat_json
from app.services.resume_reader import extract_basic_skills, summarize_resume


class EnhancedResume(BaseModel):
    professional_headline: object = ""
    contact_summary: object = ""
    professional_summary: object = ""
    experience: object = Field(default_factory=list)
    education: object = Field(default_factory=list)
    technical_skills: object = Field(default_factory=list)
    projects: object = Field(default_factory=list)
    languages: object = Field(default_factory=list)
    email_profile: object = ""


PROMPT_TEMPLATE = """Você é um assistente especialista em currículos para candidatura profissional.

Extraia e organize o máximo de informações úteis do currículo abaixo.

Regras obrigatórias:
- Não invente experiências.
- Não invente habilidades.
- Não altere datas, empresas, cargos, cursos ou níveis.
- Se uma informação estiver confusa, preserve com cautela sem aumentar a qualificação.
- Organize o conteúdo para ser usado em análise de vagas e geração de e-mails de candidatura.
- Responda somente JSON válido.
- Não use markdown.

Currículo bruto extraído:
{{RAW_TEXT}}

Formato obrigatório:
{
  "professional_headline": "",
  "contact_summary": "",
  "professional_summary": "",
  "experience": [],
  "education": [],
  "technical_skills": [],
  "projects": [],
  "languages": [],
  "email_profile": ""
}

Instruções para email_profile:
- Escreva em primeira pessoa.
- Seja curto, profissional e factual.
- Use apenas informações presentes no currículo.
- Não inclua telefone, email ou links se eles já estiverem em contact_summary.
"""


def enhance_resume_with_ai(raw_text: str) -> tuple[str, list[str]]:
    prompt = PROMPT_TEMPLATE.replace("{{RAW_TEXT}}", raw_text)
    result = EnhancedResume.model_validate(chat_json(prompt))
    formatted = _format_enhanced_resume(result)
    skills = sorted(set(_as_list(result.technical_skills) + extract_basic_skills(raw_text)))
    return formatted, skills


def safe_enhance_resume(raw_text: str) -> tuple[str, list[str], str | None]:
    try:
        return (*enhance_resume_with_ai(raw_text), None)
    except Exception as exc:
        return summarize_resume(raw_text), extract_basic_skills(raw_text), str(exc)


def _format_enhanced_resume(result: EnhancedResume) -> str:
    sections = [
        ("Título profissional", _as_list(result.professional_headline)),
        ("Contato", _as_list(result.contact_summary)),
        ("Resumo profissional", _as_list(result.professional_summary)),
        ("Experiência", _as_list(result.experience)),
        ("Formação", _as_list(result.education)),
        ("Habilidades técnicas", _as_list(result.technical_skills)),
        ("Projetos", _as_list(result.projects)),
        ("Idiomas", _as_list(result.languages)),
        ("Perfil para e-mail", _as_list(result.email_profile)),
    ]
    lines: list[str] = []
    for title, values in sections:
        clean_values = [value.strip() for value in values if value and value.strip()]
        if not clean_values:
            continue
        lines.append(title.upper())
        lines.extend(f"- {value}" for value in clean_values)
        lines.append("")
    return "\n".join(lines).strip()


def _as_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, dict):
        parts = []
        for key, item in value.items():
            text = _stringify(item)
            if text:
                parts.append(f"{key}: {text}")
        return parts
    if isinstance(value, list):
        items = []
        for item in value:
            if isinstance(item, (list, dict)):
                items.extend(_as_list(item))
            else:
                text = _stringify(item)
                if text:
                    items.append(text)
        return items
    text = _stringify(value)
    return [text] if text else []


def _stringify(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        parts = []
        for key, item in value.items():
            text = _stringify(item)
            if text:
                parts.append(f"{key}: {text}")
        return " | ".join(parts)
    if isinstance(value, list):
        return " | ".join(text for text in (_stringify(item) for item in value) if text)
    return str(value).strip()
