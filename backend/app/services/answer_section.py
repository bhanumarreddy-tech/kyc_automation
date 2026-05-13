"""Per-section "answer with Google Search grounding" Gemini call.

For each KYC section we make one or more Gemini ``generate_content`` calls
(initial answer plus optional schema-repair turns) that enable the Google Search
tool and return a strict JSON object listing answers and citation links for
every question in the section.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from google.genai import types

from app.config import get_settings
from app.questions import KYCQuestion
from app.services.gemini_client import (
    count_grounding_web_queries,
    extract_text,
    generate_content_with_overload_retry,
    get_client,
    google_search_tools,
    merge_answer_sources_with_grounding_metadata,
    parse_json_response,
    summarise_response_for_logs,
)
from app.services.gemini_schemas import KYC_ANSWER_RESPONSE_JSON_SCHEMA

logger = logging.getLogger(__name__)


def _structured_json_with_search_supported(model: str) -> bool:
    """Gemini 3+ allows JSON schema constrained decoding alongside Google Search."""
    return "gemini-3" in model.lower()


# Total attempts (initial + repair turns) when the model omits ``items`` or
# returns an empty section payload.
ANSWER_SCHEMA_MAX_ATTEMPTS = 3

DECLARATIONS_NOT_PUBLIC_MSG = (
    "Not available from public sources — declarations, consents, and signed "
    "confirmations are not discoverable via web search and must be supplied "
    "by the applicant (e.g. signed forms or direct attestation)."
)

_SYSTEM_PROMPT = (
    "You are a senior KYC / KYB analyst at a commercial bank. For each "
    "question you receive, produce a terse, factual answer about the named "
    "company that is GROUNDED IN LIVE WEB SOURCES.\n"
    "\n"
    "WEB SEARCH IS MANDATORY:\n"
    "- You MUST use the search tool before answering. Plan your "
    "  searches up front: issue one or more queries that together cover "
    "  every question in this section (e.g. 'Best Buy SEC 10-K registered "
    "  address', 'Best Buy CIK number', 'Best Buy executive officers "
    "  2026'). Re-search whenever a question needs a fact you have not "
    "  already retrieved this turn.\n"
    "- Prefer authoritative primary sources: official company registries "
    "  (SEC EDGAR, Companies House, state Secretary of State, etc.), the "
    "  company's own website / investor-relations pages, regulatory "
    "  filings, and reputable news outlets. Avoid Wikipedia and forum "
    "  posts as the sole source for a fact.\n"
    "- SEC EDGAR recency — for SEC-registered U.S. issuers, prioritize the "
    "  issuer's newest 10-K, 10-Q, 8-K, or definitive proxy filings (use "
    "  www.sec.gov/Archives/edgar/... URLs dated in or near the present "
    "  calendar year) over outdated articles, scraped mirrors, blogs, "
    "  Wikimedia excerpts, or search snippets from years-old pages. Prefer "
    "  the EDGAR primary document or filing index for the fact.\n"
    "- Sources are per serial_no — each JSON item's `sources` array must list "
    "only URLs retrieved via search this turn whose content backs THAT item's "
    "answer alone. Never paste the identical URL list onto every question. Avoid "
    "the EDGAR browse landing page unless search actually returned grounding from "
    "it for that specific answer — prefer linking the excerpt (specific 10-K, "
    "10-Q primary document URL, Companies House filing, etc.). Prefer SEC "
    "`www.sec.gov/Archives/edgar/` links you retrieved ahead of unrelated domains "
    "when sorting up to three URLs per question.\n"
    "- SEC EDGAR links: prefer "
    "  https://www.sec.gov/Archives/edgar/... URLs over any "
    "  *.s3.amazonaws.com or raw storage mirror. Copy exhibit "
    "  URLs verbatim from search results — never invent or guess exhibit "
    "  filenames (e.g. dex33.htm). When unsure of the exact exhibit path, "
    "  cite the filing index page for that accession ({accession}-index.htm "
    "  under the accession folder on www.sec.gov/Archives/edgar/data/) "
    "  rather than a guessed document URL.\n"
    "- Every factual answer (anything other than the exact literals "
    "  \"Not found\" or \"Not relevant\") MUST be supported by at least "
    "  one search result that you actually retrieved this turn, and "
    "  that URL MUST appear in the 'sources' list for THAT question ONLY. "
    "  Readers must be able to open each listed URL and find support for "
    "  that answer. Do "
    "  NOT cite a URL you did not fetch.\n"
    "- Your training-data knowledge is a tie-breaker only: use it to "
    "  disambiguate or sanity-check what the web returned, never as the "
    "  primary source. If search does not surface a fact in this "
    "  turn, run another search rather than falling back to memory.\n"
    "- Two different sentinels — choose correctly:\n"
    "  * Return the exact string \"Not relevant\" (case-sensitive) with "
    "    an empty sources list when the question does not apply to this "
    "    subject or context. Examples: asking for an individual's date of "
    "    birth, residential address, passport ID, or source of wealth when "
    "    the entity is a corporation with no named individual in scope "
    "    (e.g. no UBO meeting the stated threshold, so those rows are "
    "    about natural persons but there is no such person to describe); "
    "    sub-questions that only make sense when a parent question "
    "    establishes a person or relationship that does not exist here. "
    "    Do NOT use \"Not found\" for these — use \"Not relevant\".\n"
    "  * Return the exact string \"Not found\" (case-sensitive) with an "
    "    empty sources list ONLY when the question could in principle be "
    "    answered from public or applicant-supplied material but you did "
    "    not find it: private/internal facts, forward-looking commitments, "
    "    intent to consent to monitoring, signed declarations, the "
    "    specific source of funds for the account being opened, etc. Do "
    "    not use \"Not found\" when the correct classification is "
    "    non-applicability — use \"Not relevant\" instead.\n"
    "\n"
    "STYLE RULES for the 'answer' field - follow these strictly:\n"
    "1. Return only the value(s) the question asks for. Do not restate the "
    "   company name as the subject of a sentence. Do not restate or "
    "   paraphrase the question.\n"
    "2. No preamble, no filler. Do not start with phrases like 'The "
    "   company...', 'It is...', 'Based on public information...', "
    "   'According to...', 'The registered address is...'.\n"
    "3. For fact-style questions (registration numbers, addresses, dates, "
    "   TINs, tickers, entity types, jurisdictions, percentages), return "
    "   the bare value. Use 'Label: value' when there are multiple labelled "
    "   values, separated by '; '.\n"
    "4. For list/multi-item questions (UBOs, key personnel, jurisdictions, "
    "   products), return entries separated by '; '. Keep each entry "
    "   compact (e.g. 'Corie Barry (CEO); Matt Bilunas (CFO)'), not a "
    "   paragraph.\n"
    "5. For yes/no questions, lead with 'Yes' or 'No', then a brief "
    "   qualifier if needed (e.g. 'Yes - NYSE: BBY').\n"
    "\n"
    "Worked examples (apply the same pattern to every question):\n"
    "  Q: What is the company's registration number?\n"
    "  GOOD: \"CIK: 0000764478; Delaware file number: 0764478.\"\n"
    "  BAD:  \"Best Buy Co., Inc. has the SEC CIK number 0000764478 and "
    "Delaware file number 0764478.\"\n"
    "\n"
    "  Q: What is the company's registered address?\n"
    "  GOOD: \"7601 Penn Avenue South, Richfield, Minnesota 55423, "
    "United States.\"\n"
    "  BAD:  \"The registered address is 7601 Penn Avenue South, "
    "Richfield, Minnesota 55423, United States.\""
)


_RESPONSE_FORMAT_INSTRUCTIONS = (
    "Respond with a single JSON object and nothing else (no prose, no "
    "markdown fences). The schema is:\n"
    "{\n"
    '  "items": [\n'
    "    {\n"
    '      "serial_no": <integer matching the question>,\n'
    '      "answer": <string, the bare value(s) - see STYLE RULES - or '
    'the literal "Not found" or the literal "Not relevant">,\n'
    '      "sources": [ { "title": <string>, "url": <string> }, ... ]\n'
    "    }\n"
    "  ]\n"
    "}\n"
    "Include exactly one entry per question. Only list URLs in `sources` for that "
    "question that search actually surfaced as evidence for THAT answer "
    "(not a generic issuer bundle). Prefer www.sec.gov/Archives/edgar/ primary "
    "documents retrieved this turn where applicable; at most three URLs total per "
    "question. Paste URLs "
    "exactly as returned by search. For SEC filings use "
    "www.sec.gov/Archives/edgar/ URLs only (not S3 mirrors).\n"
    "Reminder: the 'answer' field "
    "must not restate the company name or the question, and must not "
    "begin with filler phrases such as 'The company...', 'It is...', or "
    "'The X is...'."
)


def _repair_schema_user_message(
    num_questions: int, serial_nos: list[int]
) -> str:
    serial_part = ", ".join(str(n) for n in serial_nos)
    return (
        "Your previous reply did not include a valid JSON payload for this "
        "section. Respond with ONLY one JSON object and nothing else (no "
        "markdown fences, no commentary). The object MUST have a top-level "
        f'key \"items\" whose value is an array of exactly {num_questions} '
        "objects — one per question, in any order. Each object MUST contain:\n"
        '  \"serial_no\": <integer>,\n'
        '  \"answer\": <string>,\n'
        '  \"sources\": [ { \"title\": <string>, \"url\": <string> }, ... ]\n'
        f"Use these serial_no values and no others: {serial_part}."
    )


@dataclass
class AnsweredQuestion:
    serial_no: int
    answer: str
    sources: list[dict[str, str]]


def _build_user_message(
    company: str,
    section_no: int,
    section_name: str,
    questions: list[KYCQuestion],
    *,
    issuer_sec_hint: str = "",
) -> str:
    question_lines = [
        f"  - serial_no={q.serial_no}: {q.question}" for q in questions
    ]
    preamble = issuer_sec_hint or ""
    return (
        f"Company: {company}\n"
        + preamble
        + f"Section {section_no}: {section_name}\n\n"
        f"Answer the following KYC questions about this company. You "
        f"MUST use search to ground every answer in live, "
        f"authoritative sources before responding - do not answer from "
        f"memory. Plan a small batch of searches that together cover "
        f"all the questions below (e.g. one query for registry / "
        f"incorporation facts, one for executives, one for financials, "
        f"etc.), and run additional searches if a question is still "
        f"unanswered. Cite only URLs you actually retrieved this turn "
        f"for each serial_no separately (no copied URL lists across questions). "
        f"Use the exact string \"Not relevant\" when the question does "
        f"not apply to this entity or context (see system rules); use "
        f"\"Not found\" only when the question could apply but public "
        f"sources lack the fact and only the applicant can supply it "
        f"(declarations, source of funds for the account, private "
        f"documents).\n\n"
        f"Questions:\n" + "\n".join(question_lines) + "\n\n"
        f"{_RESPONSE_FORMAT_INSTRUCTIONS}"
    )


def _log_answer_usage(section_no: int, response: types.GenerateContentResponse) -> None:
    um = getattr(response, "usage_metadata", None)
    web_queries = count_grounding_web_queries(response)
    finish = None
    if response.candidates:
        finish = getattr(response.candidates[0], "finish_reason", None)
    logger.info(
        "section %d answer usage: prompt_tokens=%s, output_tokens=%s, "
        "finish_reason=%s, web_queries=%d, detail=[%s]",
        section_no,
        getattr(um, "prompt_token_count", None) if um is not None else None,
        getattr(um, "candidates_token_count", None) if um is not None else None,
        finish,
        web_queries,
        summarise_response_for_logs(response),
    )


def _parse_items_to_answered(
    data: object, questions: list[KYCQuestion]
) -> list[AnsweredQuestion] | None:
    """Build per-question answers if *data* is a dict with a usable ``items`` list."""
    if not isinstance(data, dict):
        return None
    items = data.get("items")
    if not isinstance(items, list) or len(items) == 0:
        return None

    by_serial: dict[int, AnsweredQuestion] = {}
    for raw in items:
        if not isinstance(raw, dict):
            continue
        try:
            serial_no = int(raw.get("serial_no"))
        except (TypeError, ValueError):
            continue
        answer = str(raw.get("answer") or "").strip()
        sources_raw = raw.get("sources") or []
        sources: list[dict[str, str]] = []
        if isinstance(sources_raw, list):
            for src in sources_raw:
                if not isinstance(src, dict):
                    continue
                url = str(src.get("url") or "").strip()
                if not url:
                    continue
                title = str(src.get("title") or "").strip() or url
                sources.append({"title": title, "url": url})
        by_serial[serial_no] = AnsweredQuestion(
            serial_no=serial_no,
            answer=answer,
            sources=sources,
        )

    ordered = [
        by_serial.get(q.serial_no, AnsweredQuestion(q.serial_no, "", []))
        for q in questions
    ]
    if not any(a.answer.strip() for a in ordered):
        return None
    return ordered


def _try_parse_answer_payload(
    response: object, questions: list[KYCQuestion]
) -> list[AnsweredQuestion] | None:
    try:
        data = parse_json_response(response)
    except (json.JSONDecodeError, ValueError):
        return None
    return _parse_items_to_answered(data, questions)


def _apply_declarations_public_notice(
    section_no: int, results: list[AnsweredQuestion]
) -> list[AnsweredQuestion]:
    if section_no != 8:
        return results
    out: list[AnsweredQuestion] = []
    for item in results:
        if (
            item.answer.strip() == "Not found"
            or item.answer.strip() == ""
        ):
            out.append(
                AnsweredQuestion(
                    serial_no=item.serial_no,
                    answer=DECLARATIONS_NOT_PUBLIC_MSG,
                    sources=[],
                )
            )
        else:
            out.append(item)
    return out


async def answer_section(
    company: str,
    section_no: int,
    section_name: str,
    questions: list[KYCQuestion],
    *,
    issuer_sec_hint: str = "",
) -> list[AnsweredQuestion]:
    """Run the answer phase for a section (with optional schema-repair retries)."""

    settings = get_settings()
    client = get_client()

    user_message = _build_user_message(
        company, section_no, section_name, questions, issuer_sec_hint=issuer_sec_hint
    )

    structured = _structured_json_with_search_supported(settings.gemini_model)
    logger.info(
        "Answering section %d (%s) with %d question(s) for '%s' (model=%s, "
        "google_search=on, structured_json_schema=%s)",
        section_no,
        section_name,
        len(questions),
        company,
        settings.gemini_model,
        structured,
    )

    contents: list[types.Content] = [
        types.Content(
            role="user",
            parts=[types.Part.from_text(text=user_message)],
        ),
    ]

    # Large sections + many URL sources exceed 4k tokens; 2.5 Flash allows much higher.
    _cfg: dict = {
        "system_instruction": _SYSTEM_PROMPT,
        "tools": google_search_tools(),
        "max_output_tokens": 32_768,
    }
    if _structured_json_with_search_supported(settings.gemini_model):
        _cfg["response_mime_type"] = "application/json"
        _cfg["response_json_schema"] = KYC_ANSWER_RESPONSE_JSON_SCHEMA
    answer_config = types.GenerateContentConfig(**_cfg)
    serial_nos = [q.serial_no for q in questions]
    last_response: types.GenerateContentResponse | None = None

    for schema_attempt in range(ANSWER_SCHEMA_MAX_ATTEMPTS):
        try:
            response = await generate_content_with_overload_retry(
                client,
                settings,
                model=settings.gemini_model,
                contents=contents,
                config=answer_config,
            )
        except Exception as exc:  # noqa: BLE001 - surface any LLM failure as empty section
            logger.exception(
                "Gemini answer call failed for section %d: %s", section_no, exc
            )
            return [AnsweredQuestion(q.serial_no, "", []) for q in questions]

        _log_answer_usage(section_no, response)

        if response.candidates:
            fr = response.candidates[0].finish_reason
            if fr == types.FinishReason.UNEXPECTED_TOOL_CALL:
                logger.warning(
                    "section %d (%s): branch=unexpected_tool_finish (%s); "
                    "Google Search may be unavailable for this API key/model.",
                    section_no,
                    section_name,
                    fr,
                )
                return [AnsweredQuestion(q.serial_no, "", []) for q in questions]

        last_response = response
        parsed = _try_parse_answer_payload(response, questions)
        if parsed is not None:
            parsed = merge_answer_sources_with_grounding_metadata(
                parsed,
                response,
                enabled=settings.answer_sources_use_grounding_metadata,
            )
            return _apply_declarations_public_notice(section_no, parsed)

        logger.debug(
            "Answer response for section %d missing valid 'items' or empty "
            "payload (schema attempt %d/%d)",
            section_no,
            schema_attempt + 1,
            ANSWER_SCHEMA_MAX_ATTEMPTS,
        )
        if schema_attempt + 1 >= ANSWER_SCHEMA_MAX_ATTEMPTS:
            break

        contents.append(
            types.Content(
                role="model",
                parts=[types.Part.from_text(text=extract_text(response))],
            )
        )
        contents.append(
            types.Content(
                role="user",
                parts=[
                    types.Part.from_text(
                        text=_repair_schema_user_message(len(questions), serial_nos)
                    )
                ],
            )
        )

    diag = summarise_response_for_logs(last_response) if last_response else "no_response"
    text_preview_len = (
        len(extract_text(last_response).strip()) if last_response else 0
    )
    logger.warning(
        "section %d (%s): exhausted answer schema retries; returning empty rows. "
        "branch=schema_retries_exhausted last_turn=[%s] answer_text_chars=%d "
        "structured_json_schema=%s. If last_turn shows finish_reason=OTHER, "
        "parts=0, or web_queries=0 repeatedly, set GEMINI_MODEL_ANSWER in "
        "app/config.py to a Gemini 3 "
        "id (see .env.example). Set LOG_LEVEL=DEBUG for parse detail.",
        section_no,
        section_name,
        diag,
        text_preview_len,
        structured,
    )
    return [AnsweredQuestion(q.serial_no, "", []) for q in questions]
