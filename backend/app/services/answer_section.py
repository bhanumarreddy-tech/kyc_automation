"""Per-section "answer with web search" Claude call.

For each KYC section we make a single Claude call that:

* Registers the configured server-side web search tool (default
  ``web_search_20260209`` with dynamic filtering for Opus 4.7 / Sonnet 4.6;
  override via ``WEB_SEARCH_TOOL_TYPE``).
* Returns a strict JSON object listing the answer and citation links for
  every question in the section.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from app.config import Settings, get_settings
from app.questions import KYCQuestion
from app.services.claude_client import get_client, parse_json_response

logger = logging.getLogger(__name__)


_SYSTEM_PROMPT = (
    "You are a senior KYC / KYB analyst at a commercial bank. For each "
    "question you receive, produce a terse, factual answer about the named "
    "company that is GROUNDED IN LIVE WEB SOURCES.\n"
    "\n"
    "WEB SEARCH IS MANDATORY:\n"
    "- You MUST use the web_search tool before answering. Plan your "
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
    "- Every non-'Not found' answer MUST be supported by at least one "
    "  web_search result that you actually retrieved this turn, and that "
    "  URL MUST appear in the 'sources' list for the question. Do NOT "
    "  cite a URL you did not fetch.\n"
    "- Your training-data knowledge is a tie-breaker only: use it to "
    "  disambiguate or sanity-check what the web returned, never as the "
    "  primary source. If web_search does not surface a fact in this "
    "  turn, run another search rather than falling back to memory.\n"
    "- Return the exact string \"Not found\" (case-sensitive) with an "
    "  empty sources list ONLY for questions that no public source can "
    "  answer - forward-looking commitments, intent to consent to "
    "  monitoring, signed declarations, the specific source of funds "
    "  for the account being opened, or other private/internal facts "
    "  that the applicant company itself must supply.\n"
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
    'the literal "Not found">,\n'
    '      "sources": [ { "title": <string>, "url": <string> }, ... ]\n'
    "    }\n"
    "  ]\n"
    "}\n"
    "Include exactly one entry per question. Only list sources you "
    "actually used to support the answer. Reminder: the 'answer' field "
    "must not restate the company name or the question, and must not "
    "begin with filler phrases such as 'The company...', 'It is...', or "
    "'The X is...'."
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
) -> str:
    question_lines = [
        f"  - serial_no={q.serial_no}: {q.question}" for q in questions
    ]
    return (
        f"Company: {company}\n"
        f"Section {section_no}: {section_name}\n\n"
        f"Answer the following KYC questions about this company. You "
        f"MUST use the web_search tool to ground every answer in live, "
        f"authoritative sources before responding - do not answer from "
        f"memory. Plan a small batch of searches that together cover "
        f"all the questions below (e.g. one query for registry / "
        f"incorporation facts, one for executives, one for financials, "
        f"etc.), and run additional searches if a question is still "
        f"unanswered. Cite only URLs you actually retrieved this turn. "
        f"Reserve \"Not found\" for questions that only the applicant "
        f"company itself can answer (declarations, intent to consent, "
        f"the specific source of funds for the account being opened, "
        f"private documents).\n\n"
        f"Questions:\n" + "\n".join(question_lines) + "\n\n"
        f"{_RESPONSE_FORMAT_INSTRUCTIONS}"
    )


def _summarise_blocks(content: list) -> str:
    """Compact 'type[:name]' summary of response content blocks for logs."""
    parts: list[str] = []
    for block in content or []:
        block_type = getattr(block, "type", None) or "?"
        name = getattr(block, "name", None)
        parts.append(f"{block_type}:{name}" if name else block_type)
    return ",".join(parts) if parts else "<empty>"


def build_web_search_tool(settings: Settings) -> dict[str, object]:
    """Build the server ``web_search`` tool dict for :meth:`messages.create`."""
    spec: dict[str, object] = {
        "type": settings.web_search_tool_type,
        "name": "web_search",
        "max_uses": settings.max_web_searches,
    }
    if settings.web_search_direct_only:
        # Disables dynamic code-exec filtering path; required for some ZDR
        # setups per Anthropic server-tools docs.
        spec["allowed_callers"] = ["direct"]
    return spec


def _count_web_searches(response: object) -> int:
    """Authoritative web-search count: prefer typed usage, fall back to blocks.

    Per Anthropic docs the canonical count is
    ``usage.server_tool_use.web_search_requests``; we still cross-check by
    counting ``server_tool_use`` blocks named ``web_search`` so a mismatch
    shows up in logs.
    """
    usage = getattr(response, "usage", None)
    server_tool_use = getattr(usage, "server_tool_use", None) if usage else None
    typed = getattr(server_tool_use, "web_search_requests", None)
    if isinstance(typed, int):
        return typed
    return sum(
        1
        for block in (getattr(response, "content", []) or [])
        if getattr(block, "type", None) == "server_tool_use"
        and getattr(block, "name", None) == "web_search"
    )


async def answer_section(
    company: str,
    section_no: int,
    section_name: str,
    questions: list[KYCQuestion],
) -> list[AnsweredQuestion]:
    """Make one Claude call for a section and return the parsed answers."""

    settings = get_settings()
    client = get_client()

    user_message = _build_user_message(company, section_no, section_name, questions)

    logger.info(
        "Answering section %d (%s) with %d question(s) for '%s' "
        "(model=%s, web_search_tool=%s, max_uses=%d, direct_only=%s)",
        section_no,
        section_name,
        len(questions),
        company,
        settings.anthropic_model,
        settings.web_search_tool_type,
        settings.max_web_searches,
        settings.web_search_direct_only,
    )

    tools = [build_web_search_tool(settings)]

    # NOTE: no assistant prefill. With the web_search server tool the model
    # needs to start its turn with a server_tool_use block, not text. A
    # prefilled "{" forces the response to begin with a text block and was
    # observed to make the model either skip web_search entirely or emit a
    # malformed (client-style) tool_use that the API can't run server-side.
    # We rely on the JSON instructions in the prompt + parse_json_response's
    # fallback ("first { ... last }") to recover the JSON payload.
    messages: list[dict[str, object]] = [
        {"role": "user", "content": user_message},
    ]

    # Loop to handle the documented pause_turn flow: long server-tool turns
    # may be paused by Anthropic and must be resubmitted as-is for the model
    # to continue. Cap the loop defensively so a stuck turn can't spin.
    max_continuations = 4
    response = None
    for attempt in range(max_continuations + 1):
        try:
            response = await client.messages.create(
                model=settings.anthropic_model,
                # JSON for a full section can be long (multi-line answers,
                # many source URLs). 4096 keeps headroom while staying below
                # typical max-output caps.
                max_tokens=4096,
                system=_SYSTEM_PROMPT,
                tools=tools,
                messages=messages,
            )
        except Exception as exc:  # noqa: BLE001 - surface any LLM failure as empty section
            logger.exception(
                "Claude answer call failed for section %d: %s", section_no, exc
            )
            return [AnsweredQuestion(q.serial_no, "", []) for q in questions]

        stop_reason = getattr(response, "stop_reason", None)
        if stop_reason != "pause_turn":
            break

        logger.info(
            "section %d hit pause_turn (attempt %d), continuing turn",
            section_no,
            attempt + 1,
        )
        messages.append({"role": "assistant", "content": response.content})

    usage = getattr(response, "usage", None)
    web_search_calls = _count_web_searches(response)
    content_blocks = getattr(response, "content", []) or []
    logger.info(
        "section %d answer usage: input=%s, output=%s, stop_reason=%s, "
        "web_searches=%d, blocks=[%s]",
        section_no,
        getattr(usage, "input_tokens", None) if usage is not None else None,
        getattr(usage, "output_tokens", None) if usage is not None else None,
        getattr(response, "stop_reason", None),
        web_search_calls,
        _summarise_blocks(content_blocks),
    )

    if getattr(response, "stop_reason", None) == "tool_use":
        # The model emitted a client-style tool_use block we can't service
        # (we only register server tools). This is almost always a sign that
        # the org doesn't have web_search enabled in the Claude Console, so
        # the API silently demoted the server tool to a client tool. Log
        # the offending tool name(s) so the cause is obvious in the logs.
        client_tool_names = sorted(
            {
                str(getattr(b, "name", "") or "?")
                for b in content_blocks
                if getattr(b, "type", None) == "tool_use"
            }
        )
        logger.warning(
            "section %d response stopped on a client tool_use call (%s); "
            "web_search may not be enabled for this Anthropic org. "
            "Returning empty answers for this section.",
            section_no,
            ", ".join(client_tool_names) or "<unknown>",
        )
        return [AnsweredQuestion(q.serial_no, "", []) for q in questions]

    try:
        data = parse_json_response(response)
    except (json.JSONDecodeError, ValueError):
        logger.warning(
            "Could not parse JSON from answer call for section %d", section_no
        )
        return [AnsweredQuestion(q.serial_no, "", []) for q in questions]

    items = data.get("items") if isinstance(data, dict) else None
    if not isinstance(items, list):
        logger.warning(
            "Answer response for section %d missing 'items' list", section_no
        )
        return [AnsweredQuestion(q.serial_no, "", []) for q in questions]

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

    return [
        by_serial.get(q.serial_no, AnsweredQuestion(q.serial_no, "", []))
        for q in questions
    ]
