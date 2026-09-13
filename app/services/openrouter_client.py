import json
import os

from openai import OpenAI

from app.config import OPENROUTER_BASE_URL, OPENROUTER_MODEL


def _client() -> OpenAI:
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY não está configurada nas variáveis de ambiente.")
    return OpenAI(api_key=api_key, base_url=OPENROUTER_BASE_URL)


def chat_json(prompt: str) -> dict:
    response = _client().chat.completions.create(
        model=OPENROUTER_MODEL,
        temperature=0.2,
        messages=[
            {
                "role": "system",
                "content": "Responda somente com JSON válido, sem markdown e sem texto adicional.",
            },
            {"role": "user", "content": prompt},
        ],
    )
    content = response.choices[0].message.content or ""
    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        start = content.find("{")
        end = content.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(content[start : end + 1])
            except json.JSONDecodeError:
                pass
        raise RuntimeError("A IA retornou JSON inválido. Tente novamente.") from exc
