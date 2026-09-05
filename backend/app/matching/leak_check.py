"""
Guards against a self-defeating verification question on a FOUND report:
the finder picks a question whose answer is already sitting in the public
description ("gold necklace" / "what colour is it?" -> "gold"), so anyone
browsing can pass the claim check.

This is the cheap, deterministic first pass -- exact substring + token
recovery. The semantic cases it can't see ("what's inside the wallet?"
with the contents spelled out in the description) are caught separately by
the LLM advisory check in verification_guard.py.
"""

import re

# Small, deliberately conservative stop-list: words so common that their
# presence in the public text says nothing about whether the *answer* leaked.
_STOP = {
    "the", "a", "an", "is", "it", "in", "on", "of", "with", "and", "or",
    "to", "my", "this", "that", "was", "has", "have", "had", "for", "near",
    "at", "by", "its", "as", "be", "am", "are", "no", "yes", "not", "i",
    "found", "lost", "item", "colour", "color",
}


def _tokens(text: str) -> set[str]:
    """Lowercased alphanumeric tokens, minus stop-words and 1-char noise."""
    return {
        t
        for t in re.findall(r"[a-z0-9]+", (text or "").lower())
        if len(t) >= 2 and t not in _STOP
    }


def answer_leaks(answer: str, *public_parts: str) -> bool:
    """
    True when the verification answer is substantially recoverable from the
    text a claimant can already see.

    Two rules, either is enough:
      1. verbatim -- the whole answer (>=3 chars) appears in the public text
      2. recovery -- >=80% of the answer's meaningful tokens appear publicly
    """
    ans = (answer or "").strip().lower()
    if not ans:
        return False

    public = " ".join(p or "" for p in public_parts).lower()

    if len(ans) >= 3 and ans in public:
        return True

    ans_tokens = _tokens(ans)
    if not ans_tokens:
        return False

    hits = ans_tokens & _tokens(public)
    return len(hits) / len(ans_tokens) >= 0.8
