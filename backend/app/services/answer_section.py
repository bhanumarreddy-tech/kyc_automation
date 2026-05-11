"""Per-section "answer with web search" Claude call.

For each KYC section we make a single Claude call that:

* Has the ``web_search_20250305`` server-side tool available so it can pull
  fresh information from the public internet.
* Returns a strict JSON object listing the answer and citation links for
  every question in the section.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from app.config import get_settings
from app.questions import KYCQuestion
from app.services.claude_client import get_client, parse_json_response

logger = logging.getLogger(__name__)


_SYSTEM_PROMPT = (
    "You are a senior KYC / KYB analyst at a commercial bank. For each "
    "question you receive, produce a terse, factual answer about the named "
    "company. Use the web_search tool to find authoritative sources "
    "(official registries, the company's own website, regulatory filings, "
    "reputable news outlets).\n"
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
    "6. Evaluate each question independently. For public-record "
    "   facts about the named company (registration numbers, "
    "   headquarters address, date of incorporation, listing venue, "
    "   ticker symbol, named executives, lines of business, "
    "   geographies, public financials, DBAs, etc.), answer from "
    "   web_search results AND your training-data knowledge - "
    "   whichever is more reliable. Cite web_search sources when "
    "   you used them. DO NOT default to \"Not found\" for "
    "   public-record facts about a well-known public company; "
    "   your training data on such facts is acceptable when "
    "   web_search does not surface a clean citation in this call. "
    "   Return the exact string \"Not found\" (case-sensitive) "
    "   with an empty sources list ONLY for questions that require "
    "   information only the applicant company can supply - "
    "   forward-looking commitments, intent to consent to "
    "   monitoring, signed declarations, the specific source of "
    "   funds for an account-opening transaction, private internal "
    "   documents, or facts that have never been disclosed "
    "   publicly.\n"
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
        f"Answer the following KYC questions about this company. Use the "
        f"web_search tool to find authoritative sources, and also use "
        f"your training-data knowledge for well-known public-record "
        f"facts (registration IDs, addresses, dates, tickers, "
        f"executives, financials, etc.). Reserve \"Not found\" for "
        f"questions that only the applicant company itself can answer "
        f"(declarations, intent to consent, the specific source of "
        f"funds for the account being opened, private documents).\n\n"
        f"Questions:\n" + "\n".join(question_lines) + "\n\n"
        f"{_RESPONSE_FORMAT_INSTRUCTIONS}"
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
        "Answering section %d (%s) with %d question(s) for '%s'",
        section_no,
        section_name,
        len(questions),
        company,
    )

    tools = [
        {
            "type": "web_search_20250305",
            "name": "web_search",
            "max_uses": settings.max_web_searches,
        }
    ]

    prefill = "{"
    messages = [
        {"role": "user", "content": user_message},
        {"role": "assistant", "content": prefill},
    ]

    try:
        response = await client.messages.create(
            model=settings.anthropic_model,
            max_tokens=8192,
            system=_SYSTEM_PROMPT,
            tools=tools,
            messages=messages,
        )
    except Exception as exc:  # noqa: BLE001 - surface any LLM failure as empty section
        logger.exception(
            "Claude answer call failed for section %d: %s", section_no, exc
        )
        return [AnsweredQuestion(q.serial_no, "", []) for q in questions]

    usage = getattr(response, "usage", None)
    web_search_calls = sum(
        1
        for block in (getattr(response, "content", []) or [])
        if getattr(block, "type", None) == "server_tool_use"
        and getattr(block, "name", None) == "web_search"
    )
    logger.info(
        "section %d answer usage: input=%s, output=%s, stop_reason=%s, web_searches=%d",
        section_no,
        getattr(usage, "input_tokens", None) if usage is not None else None,
        getattr(usage, "output_tokens", None) if usage is not None else None,
        getattr(response, "stop_reason", None),
        web_search_calls,
    )

    try:
        data = parse_json_response(response, prefill=prefill)
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
