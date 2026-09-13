import html
import hashlib
import json
import logging
import re
import unicodedata
import urllib.parse
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass

from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.config import DATA_DIR
from app.models import Job, Resume
from app.services.channel_classifier import classify_channel
from app.services.openrouter_client import chat_json


MAX_PAGE_BYTES = 500_000
DEFAULT_LOCATION = "Brasil remoto ou hibrido"
DEFAULT_SEARCH_PREFERENCES = (
    "Prioridade: home office/remoto. "
    "Se for em Presidente Prudente, aceitar hibrido. "
    "Nao limitar a busca apenas por localidade; usar localidade como preferencia."
)
DEFAULT_PRIORITY_TOPICS = "Dev Junior Full-Stack, Desenvolvedor Python Junior, React, JavaScript, SQL, Game Developer Junior"
STATE_PATH = DATA_DIR / "job_hunter_state.json"
SEEN_PATH = DATA_DIR / "job_hunter_seen.json"
LAST_RUN_PATH = DATA_DIR / "job_hunter_last_run.json"
HUNTER_ENGINE_VERSION = 19
SEEN_VERSION = 16
USE_AI_IN_HUNTER = False
QUERY_BATCH_SIZE = 8
RESULTS_PER_QUERY = 10
AUTO_RESULTS_PER_CYCLE = 50
MAX_SEEN_URLS = 20_000
JOB_BOARD_SITES = (
    {
        "name": "LinkedIn",
        "domain": "linkedin.com",
        "site": "linkedin.com/jobs/view",
        "path_terms": ("/jobs/view",),
        "queries": (
            'site:linkedin.com/jobs/view "{topic}" "{mode}"',
            'site:br.linkedin.com/jobs/view "{topic}" "{mode}"',
            'site:linkedin.com/jobs/view "{topic}" "{location}"',
        ),
    },
    {
        "name": "InfoJobs",
        "domain": "infojobs.com.br",
        "site": "infojobs.com.br/vaga-de",
        "path_terms": ("/vaga-de-",),
        "queries": (
            'site:infojobs.com.br/vaga-de "{topic}" "{mode}"',
            'site:infojobs.com.br/vaga-de "{topic}" "{location}"',
        ),
    },
    {
        "name": "Gupy",
        "domain": "gupy.io",
        "site": "gupy.io/jobs",
        "path_terms": ("/jobs/", "/job/"),
        "queries": (
            'site:gupy.io/jobs "{topic}" "{mode}"',
            'site:gupy.io/job "{topic}" "{mode}"',
            'site:gupy.io/jobs "{topic}" "{location}"',
        ),
    },
    {
        "name": "Indeed",
        "domain": "indeed.com",
        "site": "br.indeed.com/viewjob",
        "path_terms": ("/viewjob", "/rc/clk"),
        "queries": (
            'site:br.indeed.com/viewjob "{topic}" "{mode}"',
            'site:br.indeed.com/rc/clk "{topic}" "{mode}"',
            'site:br.indeed.com/viewjob "{topic}" "{location}"',
        ),
    },
    {
        "name": "Vagas.com",
        "domain": "vagas.com.br",
        "site": "vagas.com.br/vagas",
        "path_terms": ("/vagas/", "/vagas-de-"),
        "queries": (
            'site:vagas.com.br/vagas "{topic}" "{mode}"',
            'site:vagas.com.br/vagas-de "{topic}" "{mode}"',
            'site:vagas.com.br/vagas "{topic}" "{location}"',
        ),
    },
    {
        "name": "Catho",
        "domain": "catho.com.br",
        "site": "catho.com.br/vagas",
        "path_terms": ("/vagas/",),
        "queries": (
            'site:catho.com.br/vagas "{topic}" "{mode}"',
            'site:catho.com.br/vagas "{topic}" "{location}"',
        ),
    },
    {
        "name": "Glassdoor",
        "domain": "glassdoor.com",
        "site": "glassdoor.com.br/Vaga",
        "path_terms": ("/vaga/", "/job", "/vagas/"),
        "queries": (
            'site:glassdoor.com.br/Vaga "{topic}" "{mode}"',
            'site:glassdoor.com.br/job "{topic}" "{mode}"',
            'site:glassdoor.com.br/Vaga "{topic}" "{location}"',
        ),
    },
    {
        "name": "Remotar",
        "domain": "remotar.com.br",
        "site": "remotar.com.br/job",
        "path_terms": ("/job/",),
        "queries": (
            'site:remotar.com.br/job "{topic}" "{mode}"',
            'site:remotar.com.br/job "{topic}" junior',
        ),
    },
    {
        "name": "Programathor",
        "domain": "programathor.com.br",
        "site": "programathor.com.br",
        "path_terms": ("/jobs", "/vagas", "/job/", "/vaga/"),
        "queries": (
            'site:programathor.com.br "{topic}" "{mode}"',
            'site:programathor.com.br "{topic}" junior',
        ),
    },
    {
        "name": "Trampos",
        "domain": "trampos.co",
        "site": "trampos.co/oportunidade",
        "path_terms": ("/oportunidade/", "/oportunidades/"),
        "queries": (
            'site:trampos.co/oportunidade "{topic}" "{mode}"',
            'site:trampos.co/oportunidades "{topic}" "{mode}"',
        ),
    },
    {
        "name": "GeekHunter",
        "domain": "geekhunter.com.br",
        "site": "geekhunter.com.br/vaga",
        "path_terms": ("/vaga/",),
        "queries": (
            'site:geekhunter.com.br/vaga "{topic}" "{mode}"',
            'site:geekhunter.com.br/vaga "{topic}" junior',
        ),
    },
)
DIRECT_JOB_BOARD_DOMAINS = (
    "gupy.io",
    "infojobs.com.br",
    "programathor.com.br",
    "vagas.com.br",
    "trampos.co",
)
EXPIRED_JOB_TERMS = (
    "vencida",
    "expirada",
    "encerrada",
    "vaga encerrada",
    "processo encerrado",
    "no longer accepting",
    "expired",
    "closed",
)
LOCAL_COMPANY_SEEDS = (
    "Cobmais",
    "Alto Alegre",
    "Usina Alto Alegre",
    "Grupo Alto Alegre",
    "Mazza Tech",
    "Unoeste",
    "Toledo Prudente",
    "Sicredi",
    "Energisa",
)
CONTENT_DOMAINS = (
    "dio.me",
    "blog.betrybe.com",
    "faculdade.grancursosonline.com.br",
    "querobolsa.com.br",
    "orientacarreira.com.br",
)
AGGREGATOR_DOMAINS = (
    "engenharia360.com",
    "riovagas.com.br",
    "rioempregos.com.br",
    "empregos.com.br",
)
BLOCKED_DOMAINS = (
    "google",
    "google.",
    "google.com",
    "google.com.br",
    "maps.google",
    ".maps",
    "goo.gl",
    "g.co",
    "whatsapp.com",
    "whastapp",
    "gruposdewhastapp",
    "gruposwhats",
    "wa.me",
    "telegram.",
    "t.me",
    "telegrupos",
    "facebook.com",
    "fb.com",
    "instagram.com",
    "youtube.com",
    "youtu.be",
    "tiktok.com",
    "twitter.com",
    "x.com",
    "linktr.ee",
    "beacons.ai",
    "notion.site",
    "github.com",
    "gitlab.com",
    "medium.com",
    "reddit.com",
)
GENERIC_JOB_DOMAINS = (
    "vagas.com.br",
    "empregos.com.br",
    "catho.com.br",
    "infojobs.com.br",
    "indeed.com",
    "linkedin.com",
    "gupy.io",
    "glassdoor.com",
    "remotar.com.br",
    "programathor.com.br",
    "trampos.co",
    "geekhunter.com.br",
)
NEGATIVE_URL_TERMS = (
    "/blog/",
    "/articles/",
    "/artigos/",
    "o-que-faz",
    "quanto-ganha",
    "salario",
    "sal%C3%A1rio",
    "profissoes",
    "profissões",
    "faculdade",
    "curso",
    "guia",
    "q-",
    "search",
    "busca",
    "vagas-de-trabalho",
)
CAREER_CONTEXT_TERMS = (
    "trabalhe-conosco",
    "trabalhe_conosco",
    "trabalheconosco",
    "carreira",
    "carreiras",
    "careers",
    "career",
    "work-with-us",
    "join-us",
    "banco-de-talentos",
    "banco_de_talentos",
    "talentos",
    "jobs",
    "job",
    "vaga",
    "vagas",
    "candidate-se",
)
CAREER_TEXT_TERMS = (
    "trabalhe conosco",
    "carreiras",
    "carreira",
    "banco de talentos",
    "candidate-se",
    "candidatura",
    "vagas",
    "vaga",
    "jobs",
    "careers",
    "join us",
    "work with us",
)
TECH_AREA_TERMS = (
    "desenvolvedor",
    "desenvolvedora",
    "developer",
    "dev ",
    "programador",
    "programadora",
    "software",
    "full stack",
    "full-stack",
    "fullstack",
    "frontend",
    "front-end",
    "backend",
    "back-end",
    "python",
    "javascript",
    "typescript",
    "react",
    "node",
    "node.js",
    "nextjs",
    "next.js",
    "php",
    "sql",
    "dados",
    "sistemas",
    "ti",
    "tecnologia",
    "game",
    "jogos",
    "unity",
    "qa",
    "suporte técnico",
    "estágio em ti",
    "estagio em ti",
)
OFF_AREA_TERMS = (
    "vendedor",
    "açougueiro",
    "acougueiro",
    "agricultor",
    "pedagogia",
    "administração",
    "administracao",
    "negócios",
    "negocios",
    "portfólio",
    "portfolio",
    "serviço de",
    "servico de",
    "comercial",
    "atendimento",
)
REMOTE_TERMS = (
    "remoto",
    "remote",
    "home office",
    "home-office",
    "teletrabalho",
    "anywhere",
)
HYBRID_TERMS = (
    "hibrido",
    "híbrido",
    "hybrid",
)
ONSITE_TERMS = (
    "presencial",
    "on-site",
    "onsite",
)
LOCAL_ALLOWED_TERMS = (
    "presidente prudente",
    "prudente",
    "alvares machado",
    "álvares machado",
    "lvares machado",
    "regente feijo",
    "regente feijó",
    "regente feij",
    "pirapozinho",
    "presidente bernardes",
    "presidente epitacio",
    "presidente epitácio",
    "santo anastacio",
    "santo anastácio",
    "martinopolis",
    "martinópolis",
    "rancharia",
    "narandiba",
    "taciba",
    "anhumas",
    "teodoro sampaio",
    "rosana",
    "mirante do paranapanema",
    "adamantina",
    "dracena",
    "assis",
    "oeste paulista",
    "regiao de prudente",
    "região de prudente",
    "pontal do paranapanema",
)
COMPANY_SEED_HOST_HINTS = (
    "cobmais.com.br",
    "altoalegre.com.br",
    "usinaaltoalegre.com.br",
    "mazza.tech",
)
logger = logging.getLogger(__name__)


class SearchPlan(BaseModel):
    target_titles: object = Field(default_factory=list)
    keywords: object = Field(default_factory=list)
    locations: object = Field(default_factory=list)
    search_queries: object = Field(default_factory=list)


class JobRelevance(BaseModel):
    is_job: bool = False
    confidence: int = 0
    reason: str = ""
    normalized_title: str = ""
    company: str = ""
    description: str = ""


class ResumeJobMatch(BaseModel):
    is_match: bool = False
    score: int = Field(default=0, ge=0, le=100)
    reason: str = ""
    matched_skills: list[str] = []
    missing_requirements: list[str] = []


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str
    source: str


@dataclass
class HuntRunStats:
    queries: int = 0
    search_results: int = 0
    candidate_results: int = 0
    saved: int = 0
    rejected: int = 0
    invalid_or_duplicate: int = 0
    no_candidate_url: int = 0
    already_seen: int = 0
    expired_or_closed: int = 0
    network_errors: int = 0
    not_real_job: int = 0
    area_or_modality: int = 0
    not_resume_match: int = 0

    def summary(self) -> str:
        return (
            f"{self.saved} vagas salvas. "
            f"{self.queries} consultas, {self.search_results} resultados coletados, "
            f"{self.candidate_results} candidatos a vaga. "
            f"Rejeitados: {self.rejected} "
            f"(duplicados/URL invalida: {self.invalid_or_duplicate}, sem URL de vaga: {self.no_candidate_url}, "
            f"ja vistos: {self.already_seen}, vencidas/encerradas: {self.expired_or_closed}, "
            f"falhas de rede: {self.network_errors}, "
            f"nao eram vaga real: {self.not_real_job}, "
            f"area/modalidade: {self.area_or_modality}, match baixo com curriculo: {self.not_resume_match})."
        )

    def to_dict(self) -> dict:
        return {
            "queries": self.queries,
            "search_results": self.search_results,
            "candidate_results": self.candidate_results,
            "saved": self.saved,
            "rejected": self.rejected,
            "invalid_or_duplicate": self.invalid_or_duplicate,
            "no_candidate_url": self.no_candidate_url,
            "already_seen": self.already_seen,
            "expired_or_closed": self.expired_or_closed,
            "network_errors": self.network_errors,
            "not_real_job": self.not_real_job,
            "area_or_modality": self.area_or_modality,
            "not_resume_match": self.not_resume_match,
        }


PROMPT_TEMPLATE = """Voce e um assistente de carreira que cria consultas de busca para encontrar vagas compativeis.

Com base no curriculo abaixo, gere consultas objetivas para buscar vagas reais.

Regras:
- Nao invente habilidades que nao aparecem no curriculo.
- Priorize cargos e tecnologias presentes no curriculo.
- Inclua buscas para sites de emprego e tambem sites de empresas.
- Foque em paginas com vagas abertas, carreiras, trabalhe conosco ou candidatura.
- Evite consultas que tragam guia, salario, curso, faculdade, blog ou "o que faz".
- Retorne somente JSON valido.
- Nao use markdown.

Curriculo:
{{RESUME_TEXT}}

Preferencias de localidade e modalidade:
{{LOCATION}}

Formato:
{
  "target_titles": [],
  "keywords": [],
  "locations": [],
  "search_queries": []
}

As search_queries devem ser strings prontas para buscador, por exemplo:
"desenvolvedor python junior remoto vaga email rh"
"site:linkedin.com/jobs/view desenvolvedor python junior remoto"
"site:infojobs.com.br/vagas desenvolvedor python junior"
"site:gupy.io/jobs python junior remoto"
"desenvolvedor python junior trabalhe conosco candidate-se"
"""


RELEVANCE_PROMPT_TEMPLATE = """Voce e um filtro de qualidade para um aplicativo que caca vagas de emprego.

Decida se o resultado abaixo e realmente:
1. uma vaga de emprego aberta;
2. uma pagina de carreiras/trabalhe conosco com disponibilidade para entrar no time;
3. uma lista de vagas com links reais para candidatura.

Rejeite quando for apenas:
- guia de carreira;
- materia informativa;
- salario ou "quanto ganha";
- "o que faz";
- curso, faculdade ou bootcamp;
- blog ou noticia;
- pagina generica sem indicio de vaga aberta;
- agregador com termo de busca, mas sem vaga especifica.
- qualquer pagina fora de contexto de carreiras, trabalhe conosco, banco de talentos, candidatura ou vaga especifica.

Responda somente JSON valido, sem markdown.

Titulo do resultado:
{{TITLE}}

URL:
{{URL}}

Resumo:
{{SNIPPET}}

Formato:
{
  "is_job": false,
  "confidence": 0,
  "reason": "",
  "normalized_title": "",
  "company": "",
  "description": ""
}

Regras:
- is_job deve ser true apenas se houver forte indicio de vaga real ou pagina de carreiras.
- confidence deve ir de 0 a 100.
- normalized_title deve conter o cargo se existir.
- company deve conter a empresa se existir.
- description deve resumir apenas evidencias do resultado.
"""


MATCH_PROMPT_TEMPLATE = """Voce e um recrutador tecnico avaliando se uma vaga combina com um curriculo.

Decida se a vaga abaixo e realmente condizente com as habilidades, nivel e preferencias do candidato.

Regras:
- Nao invente habilidades que nao aparecem no curriculo.
- Rejeite vaga senior/especialista/lead quando o curriculo indicar perfil junior ou inicial.
- Rejeite vaga de outra area mesmo que seja uma vaga real.
- Rejeite presencial fora da localidade aceita, a menos que seja remoto ou hibrido em localidade compativel.
- Aceite apenas quando houver evidencias claras de compatibilidade por cargo, tecnologias e nivel.
- Retorne somente JSON valido, sem markdown.

Curriculo:
{{RESUME_TEXT}}

Preferencias:
{{PREFERENCES}}

Topicos prioritarios:
{{PRIORITY_TOPICS}}

Vaga:
Titulo: {{TITLE}}
URL: {{URL}}
Resumo: {{SNIPPET}}

Formato:
{
  "is_match": false,
  "score": 0,
  "reason": "",
  "matched_skills": [],
  "missing_requirements": []
}

Regra de corte:
- score abaixo de 65 deve ser is_match=false.
- score 65+ somente quando a vaga for uma candidatura plausivel para este curriculo.
"""


def hunt_jobs_for_resume(
    session: Session,
    resume_id: int,
    location: str = DEFAULT_SEARCH_PREFERENCES,
    max_results: int = 25,
    priority_topics: str = DEFAULT_PRIORITY_TOPICS,
) -> tuple[int, int, str]:
    resume = session.get(Resume, resume_id)
    if not resume:
        raise RuntimeError("Curriculo nao encontrado.")

    all_queries = build_search_queries(resume, location, priority_topics)
    state = load_hunter_state()
    seen_store = load_seen_urls()
    persistent_seen = set(seen_store.get("urls", []))
    queries = choose_query_batch(all_queries, state)
    stats = HuntRunStats(queries=len(queries))
    saved = 0
    skipped = 0
    seen_urls: set[str] = set()
    stop_requested = False

    for query in queries:
        first = int(state.get("offsets", {}).get(query, 1))
        try:
            results = search_job_sources(query, per_query_limit=RESULTS_PER_QUERY, first=first)
        except (urllib.error.URLError, TimeoutError, OSError, ET.ParseError) as exc:
            logger.warning("Falha temporaria ao buscar query=%r first=%s: %s", query, first, exc)
            stats.network_errors += 1
            continue
        stats.search_results += len(results)
        for result in results:
            if saved >= max_results:
                stop_requested = True
                break

            canonical_url = canonicalize_url(result.url)
            if not canonical_url or canonical_url in seen_urls:
                skipped += 1
                stats.rejected += 1
                stats.invalid_or_duplicate += 1
                continue
            seen_urls.add(canonical_url)

            candidates = expand_result_candidates(result, canonical_url)
            if not candidates:
                skipped += 1
                stats.rejected += 1
                stats.no_candidate_url += 1
                continue
            for candidate in candidates:
                if saved >= max_results:
                    stop_requested = True
                    break
                if candidate.url in persistent_seen:
                    skipped += 1
                    stats.rejected += 1
                    stats.already_seen += 1
                    continue
                persistent_seen.add(candidate.url)
                stats.candidate_results += 1
                accepted, reason = save_candidate_job(session, candidate, location, resume, priority_topics)
                if accepted:
                    saved += 1
                    stats.saved += 1
                else:
                    skipped += 1
                    stats.rejected += 1
                    if reason == "not_real_job":
                        stats.not_real_job += 1
                    elif reason == "expired_or_closed":
                        stats.expired_or_closed += 1
                    elif reason == "area_or_modality":
                        stats.area_or_modality += 1
                    elif reason == "not_resume_match":
                        stats.not_resume_match += 1
                    else:
                        stats.invalid_or_duplicate += 1
        if stop_requested:
            break

    advance_hunter_state(state, all_queries, queries)
    save_seen_urls(persistent_seen)
    save_last_run_stats(stats, queries)
    session.commit()
    return saved, skipped, stats.summary()


def clean_low_quality_jobs(session: Session) -> int:
    jobs = session.exec(select(Job)).all()
    deleted = 0
    for job in jobs:
        result = SearchResult(
            title=job.title,
            url=job.url,
            snippet=job.description,
            source=job.source,
        )
        relevance = heuristic_job_relevance(result, job.url)
        if (
            is_saved_job_low_quality(job)
            or not is_candidate_job_url(job.url)
            or (not relevance.is_job and job.source in {"Bing Search", "Company Career Discovery"})
        ):
            session.delete(job)
            deleted += 1
    session.commit()
    return deleted


def is_saved_job_low_quality(job: Job) -> bool:
    parsed = urllib.parse.urlparse(job.url or "")
    host = parsed.netloc.lower()
    text = normalize_text(f"{job.title} {job.company} {job.description} {job.url}")

    if is_blocked_domain(host):
        return True
    if any(domain in host for domain in CONTENT_DOMAINS):
        return True
    if any(domain in host for domain in AGGREGATOR_DOMAINS):
        return True
    if any(term.lower() in f"{host}{urllib.parse.unquote(parsed.path.lower())}" for term in NEGATIVE_URL_TERMS):
        return True
    if "google" in text or "whatsapp" in text or "telegram" in text:
        return True
    if is_expired_or_closed_text(text):
        return True
    return False


def clean_bad_fit_jobs(session: Session) -> int:
    jobs = session.exec(select(Job).where(Job.channel == "bad_fit")).all()
    deleted = 0
    for job in jobs:
        session.delete(job)
        deleted += 1
    session.commit()
    return deleted


def save_candidate_job(
    session: Session,
    result: SearchResult,
    location: str,
    resume: Resume,
    priority_topics: str,
) -> tuple[bool, str]:
    canonical_url = canonicalize_url(result.url)
    if not canonical_url:
        return False, "invalid"
    if session.exec(select(Job).where(Job.url == canonical_url)).first():
        return False, "duplicate"
    if not is_candidate_job_url(canonical_url):
        return False, "not_candidate_url"
    if is_expired_or_closed_result(result):
        return False, "expired_or_closed"

    relevance = evaluate_job_relevance(result, canonical_url)
    if not relevance.is_job or relevance.confidence < 45:
        return False, "not_real_job"

    area_ok = is_area_relevant(result, resume, priority_topics)
    modality_ok = is_modality_relevant(result)
    if not area_ok or not modality_ok:
        return False, "area_or_modality"

    match = evaluate_resume_job_match(result, canonical_url, resume, location, priority_topics)
    if not match.is_match or match.score < 55:
        return False, "not_resume_match"

    contact_email = ""
    channel = classify_channel(canonical_url, contact_email)
    if channel == "manual_review":
        contact_email = discover_public_email(canonical_url)
        channel = classify_channel(canonical_url, contact_email)

    title, company = split_title_company(result.title)
    title = relevance.normalized_title or title
    company = relevance.company or company
    session.add(
        Job(
            title=title or result.title[:180],
            company=company,
            location=location,
            url=canonical_url,
            source=result.source,
            contact_email=contact_email,
            description=build_job_description(relevance, match, result),
            channel=channel,
        )
    )
    return True, "saved"


def save_bad_fit_job(
    session: Session,
    result: SearchResult,
    location: str,
    relevance: JobRelevance,
    reason: str,
) -> bool:
    canonical_url = canonicalize_url(result.url)
    if not canonical_url:
        return False
    title, company = split_title_company(result.title)
    title = relevance.normalized_title or title
    company = relevance.company or company
    session.add(
        Job(
            title=title or result.title[:180],
            company=company,
            location=location,
            url=canonical_url,
            source=result.source,
            contact_email="",
            description=f"[VAGA_RUIM] {reason}\n\n{relevance.description or result.snippet or result.title}",
            channel="bad_fit",
        )
    )
    return True


def bad_fit_reason(area_ok: bool, modality_ok: bool) -> str:
    reasons = []
    if not area_ok:
        reasons.append("fora dos tópicos prioritários/currículo")
    if not modality_ok:
        reasons.append("fora da regra de modalidade/localização")
    return "Vaga real, mas " + " e ".join(reasons) + "."


def expand_result_candidates(result: SearchResult, canonical_url: str) -> list[SearchResult]:
    if is_candidate_job_url(canonical_url):
        return [SearchResult(result.title, canonical_url, result.snippet, result.source)]

    if not should_expand_company_result(result, canonical_url):
        return []

    expanded = discover_career_links(canonical_url)
    if expanded:
        title, company = split_title_company(result.title)
        label = company or title or urllib.parse.urlparse(canonical_url).netloc
        return [
            SearchResult(
                title=f"{label} - Carreiras",
                url=url,
                snippet=f"Página de carreira encontrada a partir de {canonical_url}",
                source="Company Career Discovery",
            )
            for url in expanded
        ]
    return []


def should_expand_company_result(result: SearchResult, canonical_url: str) -> bool:
    parsed = urllib.parse.urlparse(canonical_url)
    host = parsed.netloc.lower()
    text = normalize_text(f"{result.title} {result.snippet} {canonical_url}")

    if is_blocked_domain(host):
        return False
    if any(domain in host for domain in CONTENT_DOMAINS):
        return False
    if any(domain in host for domain in AGGREGATOR_DOMAINS):
        return False
    if any(domain in host for domain in GENERIC_JOB_DOMAINS):
        return False
    if any(term in text for term in OFF_AREA_TERMS):
        return False

    if any(hint in host for hint in COMPANY_SEED_HOST_HINTS):
        return True

    company_names = [normalize_text(company) for company in LOCAL_COMPANY_SEEDS]
    if any(company and company in text for company in company_names):
        return True

    # Evita expandir domínios aleatórios. Só tenta quando o resultado já parece site corporativo.
    corporate_terms = ("empresa", "solucoes", "soluções", "tecnologia", "software", "sistemas", "consultoria")
    return any(term in text for term in corporate_terms)


def reset_seen_urls() -> None:
    save_seen_urls(set())


def build_search_queries(
    resume: Resume,
    location: str,
    priority_topics: str = DEFAULT_PRIORITY_TOPICS,
) -> list[str]:
    resume_text = resume.summary or resume.raw_text
    base = _fallback_base(resume_text)
    preferences = parse_location_preferences(location, resume_text)
    seed_companies = _infer_company_seeds(resume_text)
    topic_terms = build_profile_topics(resume_text, priority_topics)
    queries: list[str] = []

    company_queries = []
    for company in seed_companies:
        for topic in topic_terms[:6]:
            company_queries.extend(
                [
                    f'"{company}" "{topic}" "trabalhe conosco"',
                    f'"{company}" "{topic}" carreiras',
                    f'"{company}" "{topic}" vagas',
                ]
            )
        company_queries.extend(
            [
                f'"{company}" "trabalhe conosco" desenvolvedor',
                f'"{company}" "trabalhe conosco"',
                f'"{company}" carreiras tecnologia desenvolvedor',
                f'"{company}" carreiras',
                f'"{company}" vagas programador python',
                f'"{company}" vagas',
                f'"{company}" "banco de talentos" tecnologia',
                f'"{company}" "banco de talentos"',
            ]
        )
    for host in COMPANY_SEED_HOST_HINTS:
        company_queries.extend(
            [
                f"site:{host} trabalhe conosco",
                f"site:{host} carreiras",
                f"site:{host} vagas",
                f"site:{host} banco de talentos",
            ]
        )

    location_queries = []
    for topic in topic_terms:
        for mode in preferences["remote_terms"][:4]:
            location_queries.extend(
                [
                    f'"{topic}" "{mode}" vaga candidate-se -curso -salario -faculdade -blog',
                    f'"{topic}" "{mode}" "trabalhe conosco" -curso -salario -blog',
                    f'site:linkedin.com/jobs/view "{topic}" "{mode}"',
                    f'site:gupy.io/jobs "{topic}" "{mode}"',
                ]
            )
        for city in preferences["hybrid_cities"][:3]:
            location_queries.extend(
                [
                    f'"{topic}" hibrido "{city}" vaga',
                    f'"{topic}" híbrido "{city}" candidate-se',
                ]
            )
    for local in preferences["preferred_locations"]:
        location_queries.extend(
            [
                f'{base} vaga "{local}" candidate-se -curso -salario -faculdade -blog',
                f'{base} "trabalhe conosco" "{local}" -curso -salario -blog',
                f'{base} "carreiras" "{local}" candidatura -curso -blog',
                f'site:linkedin.com/jobs/view {base} "{local}"',
                f'site:infojobs.com.br/vaga-de {base} "{local}"',
                f'site:gupy.io/jobs {base} "{local}"',
            ]
        )
    for mode in preferences["remote_terms"]:
        location_queries.extend(
            [
                f'{base} vaga "{mode}" candidate-se -curso -salario -faculdade -blog',
                f'{base} "{mode}" "enviar curriculo" rh',
                f'site:linkedin.com/jobs/view {base} "{mode}"',
                f'site:gupy.io/jobs {base} "{mode}"',
            ]
        )
    for city in preferences["hybrid_cities"]:
        location_queries.extend(
            [
                f'{base} hibrido "{city}" vaga',
                f'{base} híbrido "{city}" candidate-se',
                f'{base} presencial "{city}" tecnologia vaga',
            ]
        )

    broad_queries = [
        f'{base} vaga desenvolvedor junior candidate-se -curso -salario -faculdade -blog',
        f'{base} "banco de talentos" tecnologia candidatura',
        f'{base} "enviar curriculo" rh empresa',
        f'{base} "work with us" Brazil remote',
        f'{base} "careers" "Brazil" remote',
    ]
    job_board_queries = build_job_board_queries(topic_terms, preferences)
    generated = []
    generated.extend(job_board_queries)
    generated.extend(company_queries)
    generated.extend(location_queries)
    queries = generated

    normalized = []
    for query in queries:
        clean = " ".join(query.split())
        if clean and clean not in normalized:
            normalized.append(clean)
    return normalized[:80]


def build_job_board_queries(topic_terms: list[str], preferences: dict[str, list[str]]) -> list[str]:
    queries = []
    modes = preferences["remote_terms"][:5] or ["remoto"]
    locations = preferences["preferred_locations"][:4] or ["Brasil"]
    direct_sites = [
        site
        for site in JOB_BOARD_SITES
        if any(domain in site["domain"] for domain in DIRECT_JOB_BOARD_DOMAINS)
    ]
    for topic in topic_terms[:16]:
        for site in direct_sites:
            templates = site["queries"]
            template = templates[0]
            queries.append(template.format(topic=topic, mode=modes[0], location=locations[0]))
    return queries


def build_profile_topics(resume_text: str, priority_topics: str) -> list[str]:
    topics = parse_priority_topics(priority_topics)
    normalized_resume = normalize_text(resume_text)
    compact_resume = re.sub(r"[^a-z0-9+#]+", "", normalized_resume)
    inferred = []
    topic_requirements = {
        "Desenvolvedor Full Stack Junior": ("fullstack", "full stack"),
        "Desenvolvedor React Junior": ("react",),
        "Desenvolvedor JavaScript Junior": ("javascript",),
        "Desenvolvedor PHP Junior": ("php",),
        "Desenvolvedor Node.js Junior": ("nodejs", "node.js", "node"),
        "Desenvolvedor Next.js Junior": ("nextjs", "next.js"),
        "Desenvolvedor Frontend Junior": ("frontend", "front-end", "react", "javascript"),
        "Desenvolvedor Backend Junior": ("backend", "back-end", "nodejs", "node", "python", "php"),
        "Desenvolvedor Mobile Junior": ("mobile", "reactnative", "react native"),
        "React Native Junior": ("reactnative", "react native"),
        "Game Developer Junior": ("game", "jogos", "unity", "gamemaker", "godot"),
        "Unity Junior": ("unity",),
        "Python Junior": ("python",),
        "SQL Junior": ("sql", "mysql", "postgresql"),
    }
    for term, needles in topic_requirements.items():
        if any(needle in normalized_resume or needle in compact_resume for needle in needles):
            inferred.append(term)
    for topic in inferred:
        if topic not in topics:
            topics.append(topic)
    return topics[:24]


def load_hunter_state() -> dict:
    try:
        if STATE_PATH.exists():
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {"cursor": 0, "offsets": {}}


def save_hunter_state(state: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def load_seen_urls() -> dict:
    try:
        if SEEN_PATH.exists():
            data = json.loads(SEEN_PATH.read_text(encoding="utf-8"))
            if (
                isinstance(data, dict)
                and data.get("version") == SEEN_VERSION
                and isinstance(data.get("urls"), list)
            ):
                return data
    except Exception:
        pass
    return {"version": SEEN_VERSION, "urls": []}


def save_seen_urls(urls: set[str]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    trimmed = sorted(urls)[-MAX_SEEN_URLS:]
    SEEN_PATH.write_text(
        json.dumps({"version": SEEN_VERSION, "urls": trimmed}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def save_last_run_stats(stats: HuntRunStats, queries: list[str]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    LAST_RUN_PATH.write_text(
        json.dumps(
            {
                "summary": stats.summary(),
                "stats": stats.to_dict(),
                "queries": queries,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def choose_query_batch(queries: list[str], state: dict) -> list[str]:
    if not queries:
        return []
    signature_payload = f"{HUNTER_ENGINE_VERSION}\n" + "\n".join(queries)
    signature = hashlib.sha256(signature_payload.encode("utf-8")).hexdigest()
    if state.get("signature") != signature:
        state["signature"] = signature
        state["cursor"] = 0
        state["offsets"] = {}
    cursor = int(state.get("cursor", 0)) % len(queries)
    batch = []
    for index in range(min(QUERY_BATCH_SIZE, len(queries))):
        batch.append(queries[(cursor + index) % len(queries)])
    return batch


def advance_hunter_state(state: dict, all_queries: list[str], used_queries: list[str]) -> None:
    offsets = state.setdefault("offsets", {})
    for query in used_queries:
        next_offset = int(offsets.get(query, 1)) + RESULTS_PER_QUERY
        offsets[query] = 1 if next_offset > 91 else next_offset
    if all_queries:
        state["cursor"] = (int(state.get("cursor", 0)) + QUERY_BATCH_SIZE) % len(all_queries)
    save_hunter_state(state)


def evaluate_job_relevance(result: SearchResult, canonical_url: str) -> JobRelevance:
    heuristic = heuristic_job_relevance(result, canonical_url)
    if heuristic.confidence <= 20 or heuristic.confidence >= 70 or not USE_AI_IN_HUNTER:
        return heuristic
    try:
        prompt = (
            RELEVANCE_PROMPT_TEMPLATE.replace("{{TITLE}}", result.title)
            .replace("{{URL}}", canonical_url)
            .replace("{{SNIPPET}}", result.snippet)
        )
        ai_result = JobRelevance.model_validate(chat_json(prompt))
        if ai_result.confidence <= 0:
            return heuristic
        return ai_result
    except Exception:
        return heuristic


def evaluate_resume_job_match(
    result: SearchResult,
    canonical_url: str,
    resume: Resume,
    preferences: str,
    priority_topics: str,
) -> ResumeJobMatch:
    heuristic = heuristic_resume_job_match(result, resume, preferences, priority_topics)
    if not USE_AI_IN_HUNTER:
        return heuristic
    if heuristic.score < 50:
        return heuristic
    if heuristic.score >= 65:
        return heuristic
    try:
        resume_context = (
            f"VERSAO ESTRUTURADA:\n{resume.summary}\n\n"
            f"TEXTO BRUTO:\n{resume.raw_text}"
        )
        prompt = (
            MATCH_PROMPT_TEMPLATE.replace("{{RESUME_TEXT}}", resume_context)
            .replace("{{PREFERENCES}}", preferences)
            .replace("{{PRIORITY_TOPICS}}", priority_topics)
            .replace("{{TITLE}}", result.title)
            .replace("{{URL}}", canonical_url)
            .replace("{{SNIPPET}}", result.snippet)
        )
        ai_result = ResumeJobMatch.model_validate(chat_json(prompt))
        if ai_result.score <= 0:
            return heuristic
        ai_result.is_match = ai_result.is_match and ai_result.score >= 65
        return ai_result
    except Exception:
        return heuristic


def heuristic_resume_job_match(
    result: SearchResult,
    resume: Resume,
    preferences: str,
    priority_topics: str,
) -> ResumeJobMatch:
    text = normalize_text(f"{result.title} {result.snippet} {result.url}")
    resume_text = normalize_text(f"{resume.summary} {resume.raw_text}")
    profile_terms = extract_profile_terms(resume_text)
    topic_terms = [normalize_text(term) for term in parse_priority_topics(priority_topics)]
    topic_words = set()
    for topic in topic_terms:
        topic_words.update(
            word
            for word in re.findall(r"[a-z0-9+#.-]{3,}", topic)
            if word not in {"junior", "pleno", "senior", "desenvolvedor", "desenvolvedora"}
        )

    matched_skills = sorted(term for term in profile_terms if term in text)
    topic_hits = sorted(word for word in topic_words if word in text)
    score = 0
    score += min(42, len(matched_skills) * 14)
    score += min(25, len(topic_hits) * 8)
    if any(term in text for term in ("junior", "jr", "trainee", "estagio", "estagio", "júnior", "estágio")):
        score += 25
    if "fullstack" in text and ("full stack" in profile_terms or "fullstack" in profile_terms):
        score += 12
    if "typescript" in text and ("javascript" in profile_terms or "typescript" in profile_terms):
        score += 8
    if "frontend" in text or "front-end" in text:
        if "react" in profile_terms or "javascript" in profile_terms:
            score += 8
    if "backend" in text or "back-end" in text:
        if any(term in profile_terms for term in ("node", "node.js", "python", "php", "sql")):
            score += 8
    if any(term in text for term in REMOTE_TERMS):
        score += 15
    elif has_hybrid_signal(text) and any(local in text for local in LOCAL_ALLOWED_TERMS):
        score += 10
    if any(term in text for term in ("senior", "sênior", " sr ", "sr.", "especialista", "lead", "coordenador", "gerente")):
        score -= 35
    if any(term in text for term in OFF_AREA_TERMS):
        score -= 50
    if not is_modality_relevant(result):
        score -= 30

    score = max(0, min(100, score))
    return ResumeJobMatch(
        is_match=score >= 55,
        score=score,
        reason="Compatibilidade heuristica por habilidades, cargo, nivel e modalidade.",
        matched_skills=matched_skills[:12],
        missing_requirements=[],
    )


def build_job_description(relevance: JobRelevance, match: ResumeJobMatch, result: SearchResult) -> str:
    base = relevance.description or result.snippet or result.title
    matched = ", ".join(match.matched_skills[:10])
    prefix = f"[MATCH {match.score}/100] {match.reason}"
    if matched:
        prefix += f"\nHabilidades encontradas: {matched}"
    return f"{prefix}\n\n{base}"


def heuristic_job_relevance(result: SearchResult, canonical_url: str) -> JobRelevance:
    text = f"{result.title} {result.snippet} {canonical_url}".lower()
    if not is_candidate_job_url(canonical_url):
        return JobRelevance(is_job=False, confidence=5, reason="URL parece ser conteudo informativo ou pagina generica.")

    hard_negative_terms = (
        "o que faz",
        "quanto ganha",
        "salario",
        "salário",
        "guia completo",
        "guia de carreira",
        "faculdade",
        "curso",
        "bootcamp",
        "como se tornar",
        "blog",
        "noticia",
        "notícia",
        "certificacao",
        "certificação",
    )
    if any(term in text for term in hard_negative_terms):
        return JobRelevance(is_job=False, confidence=5, reason="Conteudo informativo ou educacional.")

    positive_terms = (
        "vaga",
        "vagas",
        "emprego",
        "jobs",
        "carreira",
        "carreiras",
        "trabalhe conosco",
        "candidate-se",
        "candidatar",
        "oportunidade",
        "oportunidades",
        "hiring",
        "remoto",
        "hibrido",
        "híbrido",
        "clt",
        "pj",
        "estagio",
        "estágio",
        "junior",
        "júnior",
        "desenvolvedor",
        "programador",
        "analista",
    )
    score = sum(1 for term in positive_terms if term in text)
    is_job = score >= 2 or classify_channel(canonical_url, "") == "sensitive_platform"
    confidence = min(95, 35 + score * 12) if is_job else 25
    title, company = split_title_company(result.title)
    return JobRelevance(
        is_job=is_job,
        confidence=confidence,
        reason="Heuristica local baseada em termos de vaga.",
        normalized_title=title,
        company=company,
        description=result.snippet or result.title,
    )


def is_area_relevant(result: SearchResult, resume: Resume, priority_topics: str) -> bool:
    text = normalize_text(f"{result.title} {result.snippet} {result.url}")
    if any(term in text for term in OFF_AREA_TERMS):
        return False

    topic_terms = [normalize_text(term) for term in parse_priority_topics(priority_topics)]
    if any(topic and topic in text for topic in topic_terms):
        return True

    # Match individual words from multi-word topics, but require enough signal.
    topic_words = set()
    for topic in topic_terms:
        topic_words.update(word for word in re.findall(r"[a-z0-9+#.-]{3,}", topic) if word not in {"junior", "pleno", "senior"})
    topic_score = sum(1 for word in topic_words if word in text)

    resume_text = normalize_text(f"{resume.summary} {resume.raw_text}")
    resume_terms = extract_profile_terms(resume_text)
    profile_score = sum(1 for term in resume_terms if term in text)
    tech_score = sum(1 for term in TECH_AREA_TERMS if term in text)

    return topic_score >= 1 or profile_score >= 2 or tech_score >= 1


def is_modality_relevant(result: SearchResult) -> bool:
    text = normalize_text(f"{result.title} {result.snippet} {result.url}")

    if any(term in text for term in REMOTE_TERMS):
        return True

    if has_hybrid_signal(text):
        return any(local in text for local in LOCAL_ALLOWED_TERMS)

    if any(term in text for term in ONSITE_TERMS):
        return any(local in text for local in LOCAL_ALLOWED_TERMS)

    # Páginas de carreiras/banco de talentos nem sempre trazem modalidade no resultado da busca.
    # Mantemos para revisão se forem da área; a análise com IA pode decidir depois.
    return True


def has_hybrid_signal(text: str) -> bool:
    return any(term in text for term in HYBRID_TERMS) or bool(re.search(r"h.?brido", text))


def extract_profile_terms(text: str) -> set[str]:
    candidates = set()
    for term in TECH_AREA_TERMS:
        if term in text:
            candidates.add(term)
    for skill in (
        "python",
        "react",
        "javascript",
        "typescript",
        "sql",
        "mysql",
        "mongodb",
        "firebase",
        "node",
        "node.js",
        "nextjs",
        "next.js",
        "php",
        "api",
        "full stack",
        "fullstack",
        "game",
        "unity",
        "gamemaker",
    ):
        if skill in text:
            candidates.add(skill)
    return candidates


def parse_priority_topics(value: str) -> list[str]:
    raw = value or DEFAULT_PRIORITY_TOPICS
    parts = re.split(r"[,;\n]+", raw)
    topics = []
    for part in parts:
        clean = " ".join(part.strip().split())
        if clean and clean not in topics:
            topics.append(clean)
    return topics[:20]


def normalize_text(value: str) -> str:
    replacements = {
        "á": "a",
        "à": "a",
        "ã": "a",
        "â": "a",
        "é": "e",
        "ê": "e",
        "í": "i",
        "ó": "o",
        "ô": "o",
        "õ": "o",
        "ú": "u",
        "ç": "c",
    }
    text = value.lower()
    for source, target in replacements.items():
        text = text.replace(source, target)
    return text


def is_candidate_job_url(url: str) -> bool:
    parsed = urllib.parse.urlparse(url)
    host = parsed.netloc.lower()
    path = urllib.parse.unquote(parsed.path.lower())
    full = f"{host}{path}"

    if is_blocked_domain(host):
        return False
    if "inactive.gupy.io" in host:
        return False
    if any(domain in host for domain in CONTENT_DOMAINS):
        return False
    if any(domain in host for domain in AGGREGATOR_DOMAINS):
        return False
    if any(term.lower() in full for term in NEGATIVE_URL_TERMS):
        return False

    if "linkedin.com" in host:
        return "/jobs/view" in path
    if "infojobs.com.br" in host:
        return "/vaga-de-" in path
    if "indeed.com" in host:
        return "/viewjob" in path or "/rc/clk" in path
    if "gupy.io" in host:
        return "/jobs/" in path or "/job/" in path
    if "vagas.com.br" in host:
        return "/vagas/" in path or "/vagas-de-" in path
    if "glassdoor.com" in host:
        return "/job" in path.lower() or "/vaga/" in path.lower() or "/vagas/" in path.lower()
    if "catho.com.br" in host:
        return (
            "/vagas/" in path
            and len(path.strip("/").split("/")) >= 2
            and not path.rstrip("/").endswith("/vagas/desenvolvedor")
        )
    if "remotar.com.br" in host:
        return "/job/" in path
    if "programathor.com.br" in host:
        return any(term in path for term in ("/jobs", "/vagas", "/job/", "/vaga/"))
    if "trampos.co" in host:
        return "/oportunidade/" in path or "/oportunidades/" in path
    if "geekhunter.com.br" in host:
        return "/vaga/" in path

    for site in JOB_BOARD_SITES:
        if site["domain"] in host:
            return any(term in path for term in site["path_terms"])

    return any(term in path for term in CAREER_CONTEXT_TERMS)


def is_blocked_domain(host: str) -> bool:
    normalized = host.lower().removeprefix("www.")
    return any(domain in normalized for domain in BLOCKED_DOMAINS)


def search_job_sources(query: str, per_query_limit: int = 8, first: int = 1) -> list[SearchResult]:
    host = site_domain_from_query(query)
    if host and any(domain in host for domain in DIRECT_JOB_BOARD_DOMAINS):
        return search_direct_job_board(query, per_query_limit=per_query_limit, first=first)[:per_query_limit]
    return search_bing_rss(query, per_query_limit=per_query_limit, first=first)


def search_direct_job_board(query: str, per_query_limit: int = 8, first: int = 1) -> list[SearchResult]:
    host = site_domain_from_query(query)
    topic = search_topic_from_query(query)
    if not host or not topic:
        return []
    term = direct_search_term(topic)

    page = max(1, ((max(1, first) - 1) // max(1, per_query_limit)) + 1)
    try:
        if "gupy.io" in host:
            return search_gupy(term, page, per_query_limit)
        if "infojobs.com.br" in host:
            return search_infojobs(term, page, per_query_limit)
        if "programathor.com.br" in host:
            return search_programathor(term, page, per_query_limit)
        if "vagas.com.br" in host:
            return search_vagas_com(term, page, per_query_limit)
        if "trampos.co" in host:
            return search_trampos(term, page, per_query_limit)
    except Exception:
        return []
    return []


def search_programathor(topic: str, page: int, limit: int) -> list[SearchResult]:
    params = urllib.parse.urlencode({"search": topic, "page": page})
    url = f"https://programathor.com.br/jobs?{params}"
    html_text = fetch_html(url)
    results = []
    topic_terms = search_match_terms(topic)
    for href, label in extract_links(html_text):
        path = urllib.parse.urlparse(href).path
        if not re.match(r"^/jobs/\d+", path):
            continue
        if is_expired_or_closed_text(label):
            continue
        if topic_terms and not any(term in normalize_text(label) for term in topic_terms):
            continue
        absolute = canonicalize_url(urllib.parse.urljoin(url, href))
        if not absolute:
            continue
        title, company = split_programathor_label(label)
        results.append(
            SearchResult(
                title=title or label[:160],
                url=absolute,
                snippet=label,
                source="Programathor",
            )
        )
        if len(results) >= limit:
            break
    return unique_results(results)


def search_gupy(topic: str, page: int, limit: int) -> list[SearchResult]:
    offset = max(0, (page - 1) * limit)
    params = urllib.parse.urlencode({"name": topic, "offset": offset, "limit": limit})
    url = f"https://portal.api.gupy.io/api/job?{params}"
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 CareerPilotAI/1.0",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        payload = json.loads(response.read(MAX_PAGE_BYTES).decode("utf-8", errors="ignore"))

    results = []
    for item in payload.get("data", []):
        title = str(item.get("name") or "").strip()
        job_url = str(item.get("jobUrl") or "").strip()
        company = str(item.get("careerPageName") or "").strip()
        description = _strip_html(str(item.get("description") or ""))
        deadline = str(item.get("applicationDeadline") or "").strip()
        if not title or not job_url or "inactive.gupy.io" in job_url.lower():
            continue
        if deadline and is_iso_date_in_past(deadline):
            continue
        location = "Remoto" if item.get("isRemoteWork") or item.get("workplaceType") == "remote" else " ".join(
            str(part or "").strip() for part in [item.get("city"), item.get("state"), item.get("country")] if str(part or "").strip()
        )
        snippet = " | ".join(part for part in [title, company, location, description[:220]] if part)
        if is_expired_or_closed_text(snippet):
            continue
        results.append(
            SearchResult(
                title=f"{title} - {company}" if company else title,
                url=job_url,
                snippet=snippet,
                source="Gupy",
            )
        )
    return unique_results(results)


def search_infojobs(topic: str, page: int, limit: int) -> list[SearchResult]:
    # InfoJobs exposes a public HTML listing. The first page is the reliable source; repeated
    # fetches are deduplicated by the persistent seen URL store.
    params = urllib.parse.urlencode({"palabra": topic})
    url = f"https://www.infojobs.com.br/empregos.aspx?{params}"
    html_text = fetch_html(url)
    results = []
    topic_terms = search_match_terms(topic)
    for href, label in extract_links(html_text):
        path = urllib.parse.urlparse(href).path
        if "/vaga-de-" not in path:
            continue
        if is_expired_or_closed_text(label):
            continue
        if topic_terms and not any(term in normalize_text(label) for term in topic_terms):
            continue
        absolute = canonicalize_url(urllib.parse.urljoin(url, href))
        if not absolute:
            continue
        results.append(
            SearchResult(
                title=label[:160],
                url=absolute,
                snippet=label,
                source="InfoJobs",
            )
        )
        if len(results) >= limit:
            break
    return unique_results(results)


def search_vagas_com(topic: str, page: int, limit: int) -> list[SearchResult]:
    slug = slugify_for_url(topic)
    params = urllib.parse.urlencode({"ordenar_por": "mais_recentes", "pagina": page})
    url = f"https://www.vagas.com.br/vagas-de-{slug}?{params}"
    html_text = fetch_html(url)
    results = []
    topic_terms = search_match_terms(topic)
    for href, label in extract_links(html_text):
        path = urllib.parse.urlparse(href).path
        if not re.match(r"^/vagas/v\d+", path):
            continue
        if is_expired_or_closed_text(label):
            continue
        if topic_terms and not any(term in normalize_text(label) for term in topic_terms):
            continue
        absolute = canonicalize_url(urllib.parse.urljoin(url, href))
        if not absolute:
            continue
        results.append(
            SearchResult(
                title=label[:160],
                url=absolute,
                snippet=label,
                source="Vagas.com",
            )
        )
        if len(results) >= limit:
            break
    return unique_results(results)


def search_trampos(topic: str, page: int, limit: int) -> list[SearchResult]:
    params = urllib.parse.urlencode({"query": topic, "page": page})
    url = f"https://trampos.co/oportunidades?{params}"
    html_text = fetch_html(url)
    results = []
    topic_terms = search_match_terms(topic)
    for item in extract_trampos_items(html_text):
        opportunity_id = item.get("id")
        title = str(item.get("name") or "").strip()
        company = str(item.get("company_name") or "").strip()
        if not opportunity_id or not title:
            continue
        city = str(item.get("city") or "").strip()
        state = str(item.get("state") or "").strip()
        home_office = bool(item.get("home_office"))
        location = "Remoto" if home_office else " ".join(part for part in [city, state] if part)
        absolute = canonicalize_url(f"https://trampos.co/oportunidades/{opportunity_id}")
        snippet = " | ".join(part for part in [title, company, location, str(item.get("category_name") or "")] if part)
        if topic_terms and not any(term in normalize_text(snippet) for term in topic_terms):
            continue
        results.append(
            SearchResult(
                title=f"{title} - {company}" if company else title,
                url=absolute,
                snippet=snippet,
                source="Trampos",
            )
        )
        if len(results) >= limit:
            break
    return unique_results(results)


def direct_search_term(topic: str) -> str:
    normalized = normalize_text(topic)
    priority_terms = (
        "python",
        "react",
        "javascript",
        "typescript",
        "sql",
        "full stack",
        "full-stack",
        "fullstack",
        "react native",
        "backend",
        "frontend",
        "front-end",
        "mobile",
        "game",
        "unity",
        "qa",
    )
    for term in priority_terms:
        if term in normalized:
            return term
    if "desenvolvedor" in normalized or "developer" in normalized or "dev " in normalized:
        return "desenvolvedor"
    return topic


def search_match_terms(topic: str) -> set[str]:
    normalized = normalize_text(topic)
    terms = set()
    for word in re.findall(r"[a-z0-9+#.-]{3,}", normalized):
        if word not in {"junior", "pleno", "senior", "vaga", "vagas", "remoto", "home", "office"}:
            terms.add(word)
    return terms


def is_expired_or_closed_result(result: SearchResult) -> bool:
    return is_expired_or_closed_text(f"{result.title} {result.snippet} {result.url}")


def is_expired_or_closed_text(value: str) -> bool:
    text = normalize_text(value)
    return any(term in text for term in EXPIRED_JOB_TERMS)


def is_iso_date_in_past(value: str) -> bool:
    try:
        from datetime import datetime, timezone

        normalized = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed < datetime.now(timezone.utc)
    except Exception:
        return False


def fetch_html(url: str) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 CareerPilotAI/1.0",
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        content_type = response.headers.get("content-type", "")
        if "text/html" not in content_type and "text/plain" not in content_type:
            return ""
        return response.read(MAX_PAGE_BYTES).decode("utf-8", errors="ignore")


def extract_links(html_text: str) -> list[tuple[str, str]]:
    links = []
    for href, label in re.findall(r"<a[^>]+href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", html_text, flags=re.I | re.S):
        clean_label = _strip_html(html.unescape(label))
        clean_label = " ".join(clean_label.split())
        links.append((html.unescape(href).strip(), clean_label))
    return links


def extract_trampos_items(html_text: str) -> list[dict]:
    items = []
    for raw in re.findall(r"\{\"id\":\d+.*?\"published_at\":\"[^\"]+\"\}", html_text):
        try:
            item = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            items.append(item)
    return items


def unique_results(results: list[SearchResult]) -> list[SearchResult]:
    seen = set()
    unique = []
    for result in results:
        canonical = canonicalize_url(result.url)
        if not canonical or canonical in seen:
            continue
        seen.add(canonical)
        unique.append(SearchResult(result.title, canonical, result.snippet, result.source))
    return unique


def split_programathor_label(label: str) -> tuple[str, str]:
    clean = " ".join(label.split())
    marker_words = (" NOVA ", " Remoto ", " São Paulo ", " Belo Horizonte ", " Curitiba ", " Rio de Janeiro ")
    for marker in marker_words:
        if marker in clean:
            title = clean.split(marker, 1)[0].strip()
            return title, ""
    return clean, ""


def site_domain_from_query(query: str) -> str:
    match = re.search(r"\bsite:([^\s\"()]+)", query, flags=re.I)
    if not match:
        return ""
    domain = match.group(1).lower().strip()
    return domain.removeprefix("www.").removeprefix("br.")


def site_domains_from_query(query: str) -> list[str]:
    domain = site_domain_from_query(query)
    if not domain:
        return []
    parts = domain.split("/")
    host = parts[0].removeprefix("www.").removeprefix("br.")
    return _unique([host, domain])


def search_topic_from_query(query: str) -> str:
    quoted = [part.strip() for part in re.findall(r'"([^"]+)"', query) if part.strip()]
    ignored = {normalize_text(term) for term in (*REMOTE_TERMS, *HYBRID_TERMS, *LOCAL_ALLOWED_TERMS, "brasil")}
    for part in quoted:
        if normalize_text(part) not in ignored:
            return part

    without_site = re.sub(r"\bsite:[^\s\"()]+", " ", query, flags=re.I)
    without_ops = re.sub(r"\b(OR|AND)\b|[()]", " ", without_site, flags=re.I)
    words = []
    for word in re.findall(r"[A-Za-zÀ-ÿ0-9+#.-]{2,}", without_ops):
        normalized = normalize_text(word)
        if normalized in ignored or normalized in {"vaga", "vagas", "remoto", "home", "office"}:
            continue
        words.append(word)
    return " ".join(words[:5]).strip()


def slugify_for_url(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_text.lower()).strip("-")
    return slug or "desenvolvedor"


def search_bing_rss(query: str, per_query_limit: int = 8, first: int = 1) -> list[SearchResult]:
    encoded = urllib.parse.urlencode({"q": query, "format": "rss", "first": max(1, first)})
    url = f"https://www.bing.com/search?{encoded}"
    request = urllib.request.Request(url, headers={"User-Agent": "CareerPilotAI/1.0"})
    with urllib.request.urlopen(request, timeout=15) as response:
        data = response.read(MAX_PAGE_BYTES)

    root = ET.fromstring(data)
    results = []
    required_domains = site_domains_from_query(query)
    for item in root.findall("./channel/item")[:per_query_limit]:
        title = _xml_text(item, "title")
        link = _xml_text(item, "link")
        description = html.unescape(_xml_text(item, "description"))
        if title and link:
            canonical_link = canonicalize_url(link)
            host = urllib.parse.urlparse(canonical_link).netloc.lower().removeprefix("www.").removeprefix("br.")
            full = f"{host}{urllib.parse.urlparse(canonical_link).path.lower()}"
            if required_domains and not any(domain in full for domain in required_domains):
                continue
            results.append(
                SearchResult(
                    title=html.unescape(title),
                    url=canonical_link or link,
                    snippet=_strip_html(description),
                    source=source_name_for_url(link),
                )
            )
    return results


def source_name_for_url(url: str) -> str:
    host = urllib.parse.urlparse(url).netloc.lower()
    for site in JOB_BOARD_SITES:
        if site["domain"] in host:
            return site["name"]
    return "Bing Search"


def discover_public_email(url: str) -> str:
    if classify_channel(url, "") == "sensitive_platform":
        return ""
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "CareerPilotAI/1.0"})
        with urllib.request.urlopen(request, timeout=10) as response:
            content_type = response.headers.get("content-type", "")
            if "text/html" not in content_type and "text/plain" not in content_type:
                return ""
            text = response.read(MAX_PAGE_BYTES).decode("utf-8", errors="ignore")
    except Exception:
        return ""

    emails = re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text)
    blocked_domains = {"example.com", "domain.com", "sentry.io"}
    for email in emails:
        domain = email.split("@")[-1].lower()
        if domain not in blocked_domains and not email.lower().endswith((".png", ".jpg", ".jpeg")):
            return email
    return ""


def discover_career_links(url: str) -> list[str]:
    parsed = urllib.parse.urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return []
    if is_blocked_domain(parsed.netloc):
        return []
    if classify_channel(url, "") == "sensitive_platform":
        return []

    try:
        request = urllib.request.Request(url, headers={"User-Agent": "CareerPilotAI/1.0"})
        with urllib.request.urlopen(request, timeout=10) as response:
            content_type = response.headers.get("content-type", "")
            if "text/html" not in content_type:
                return []
            html_text = response.read(MAX_PAGE_BYTES).decode("utf-8", errors="ignore")
    except Exception:
        return []

    links = []
    for href, label in re.findall(r"<a[^>]+href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", html_text, flags=re.I | re.S):
        clean_label = _strip_html(html.unescape(label)).lower()
        absolute = urllib.parse.urljoin(url, html.unescape(href).strip())
        absolute = canonicalize_url(absolute)
        if not absolute:
            continue
        absolute_host = urllib.parse.urlparse(absolute).netloc.lower()
        if absolute_host != parsed.netloc.lower():
            continue
        target_text = f"{absolute} {clean_label}".lower()
        if any(term in target_text for term in CAREER_CONTEXT_TERMS):
            links.append(absolute)

    # Common paths are cheap to try and often exist without being linked clearly in the markup.
    base = f"{parsed.scheme}://{parsed.netloc}"
    common_paths = (
        "/trabalhe-conosco",
        "/trabalheconosco",
        "/carreiras",
        "/carreira",
        "/careers",
        "/vagas",
        "/jobs",
        "/banco-de-talentos",
    )
    for path in common_paths:
        candidate = canonicalize_url(base + path)
        if candidate and career_url_exists(candidate):
            links.append(candidate)
    return _unique(url for url in links if url and is_candidate_job_url(url))[:8]


def career_url_exists(url: str) -> bool:
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "CareerPilotAI/1.0"})
        with urllib.request.urlopen(request, timeout=6) as response:
            content_type = response.headers.get("content-type", "")
            if response.status >= 400 or ("text/html" not in content_type and "text/plain" not in content_type):
                return False
            text = response.read(120_000).decode("utf-8", errors="ignore").lower()
            return any(term in text for term in CAREER_TEXT_TERMS)
    except Exception:
        return False


def canonicalize_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return ""
    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=False)
    filtered = [(key, value) for key, value in query if not key.lower().startswith("utm_")]
    return urllib.parse.urlunparse((parsed.scheme, parsed.netloc.lower(), parsed.path.rstrip("/") or "/", "", urllib.parse.urlencode(filtered), ""))


def split_title_company(title: str) -> tuple[str, str]:
    clean = " ".join(title.split())
    for separator in (" - ", " | ", " at ", " na "):
        if separator in clean:
            left, right = clean.split(separator, 1)
            return left.strip(), right.strip()
    return clean, ""


def _fallback_base(text: str) -> str:
    lower = text.lower()
    if "python" in lower and "react" in lower:
        return "desenvolvedor full stack junior python react"
    if "python" in lower:
        return "desenvolvedor python junior"
    if "react" in lower:
        return "desenvolvedor react junior"
    if "game" in lower or "unity" in lower:
        return "desenvolvedor jogos junior"
    return "desenvolvedor junior tecnologia"


def parse_location_preferences(preference_text: str, resume_text: str) -> dict[str, list[str]]:
    normalized = f"{preference_text} {resume_text}".lower()
    preferred_locations = _infer_locations(resume_text, "")
    hybrid_cities = []
    if "presidente prudente" in normalized:
        preferred_locations.insert(0, "Presidente Prudente")
        hybrid_cities.append("Presidente Prudente")
    if "são paulo" in normalized or "sao paulo" in normalized:
        preferred_locations.append("São Paulo")

    remote_terms = ["home office", "remoto", "remote", "anywhere", "Brasil remoto"]
    if "hibrido" in normalized or "híbrido" in normalized:
        remote_terms.append("hibrido")
        remote_terms.append("híbrido")

    return {
        "preferred_locations": _unique(preferred_locations)[:5],
        "hybrid_cities": _unique(hybrid_cities)[:4],
        "remote_terms": _unique(remote_terms)[:8],
    }


def _infer_locations(text: str, preferred_location: str) -> list[str]:
    candidates = [preferred_location, "Brasil", "remoto Brasil"]
    known_locations = (
        "Presidente Prudente",
        "São Paulo",
        "Sao Paulo",
        "Brasil",
    )
    normalized = text.lower()
    for location in known_locations:
        if location.lower() in normalized:
            candidates.insert(0, location)
    return _unique(candidates)[:5]


def _infer_company_seeds(text: str) -> list[str]:
    companies = list(LOCAL_COMPANY_SEEDS)
    # Captura nomes citados no curriculo que aparecem perto de empresa/projeto sem depender da IA.
    matches = re.findall(r"(?:Empresa|Projeto|Cliente)\s*[:|-]\s*([A-ZÁÉÍÓÚÂÊÔÃÕÇ][A-Za-zÁÉÍÓÚÂÊÔÃÕÇáéíóúâêôãõç0-9 .&-]{2,50})", text)
    companies.extend(match.strip() for match in matches)
    return _unique(company.strip(" .|-") for company in companies)[:16]


def _unique(values) -> list[str]:
    unique = []
    for value in values:
        clean = str(value).strip()
        if clean and clean not in unique:
            unique.append(clean)
    return unique


def _as_strings(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, dict):
        return [str(item) for item in value.values() if str(item).strip()]
    return []


def _xml_text(item: ET.Element, tag: str) -> str:
    child = item.find(tag)
    return child.text.strip() if child is not None and child.text else ""


def _strip_html(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", value)).strip()
