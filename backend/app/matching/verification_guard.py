"""
LLM advisory check for FOUND-report verification questions.

leak_check.py catches answers that literally appear in the public text.
This catches the semantic version the string match misses -- e.g. the
description enumerates the wallet's contents and the question is "what's
inside the wallet?". It's advisory only: the finder can override it, and
any API/parsing failure fails open (leaked=False), so a flaky model can
never block a submission.
"""

import asyncio
import json
import logging

from google import genai
from google.genai import types

from app.core.config import settings

logger = logging.getLogger("findit.verification_guard")

_MODEL = "gemini-3.1-flash-lite"
_client = genai.Client(api_key=settings.gemini_api_key) if settings.gemini_api_key else None

_PROMPT = """You review verification questions for a campus lost-and-found.

A FOUND item has a PUBLIC description that anyone browsing can read, plus a
private verification question + answer used to confirm the true owner.

The question is only useful if a random person reading the public
description CANNOT answer it. Flag it as leaked when the public text makes
the answer obvious or directly states it.

PUBLIC TEXT:
{public_text}

VERIFICATION QUESTION:
{question}

EXPECTED ANSWER:
{answer}

Respond with JSON only: {{"leaked": <true|false>, "reason": "<short reason, one sentence>"}}
"""

_RESPONSE_SCHEMA = types.Schema(
    type=types.Type.OBJECT,
    properties={
        "leaked": types.Schema(type=types.Type.BOOLEAN),
        "reason": types.Schema(type=types.Type.STRING),
    },
    required=["leaked", "reason"],
)


async def llm_leak_check(*, public_text: str, question: str, answer: str) -> dict:
    """Returns {"leaked": bool, "reason": str}. Fails open on any error."""
    if _client is None or not question.strip() or not answer.strip():
        return {"leaked": False, "reason": ""}

    prompt = _PROMPT.format(
        public_text=public_text.strip() or "(none)",
        question=question.strip(),
        answer=answer.strip(),
    )

    try:
        resp = await asyncio.to_thread(
            _client.models.generate_content,
            model=_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=_RESPONSE_SCHEMA,
                temperature=0,
            ),
        )
        data = json.loads(resp.text)
        return {
            "leaked": bool(data.get("leaked", False)),
            "reason": str(data.get("reason", "")).strip(),
        }
    except Exception:
        logger.warning("verification guard LLM check failed; failing open", exc_info=True)
        return {"leaked": False, "reason": ""}
