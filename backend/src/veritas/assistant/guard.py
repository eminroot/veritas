"""What is refused before the model sees it, and what is checked after.

The rules in knowledge.py are the main defence: the model is told that a visitor's text is
a question, never an instruction, and it has nothing to act on. These checks only catch the
plain attempts early, so they cost no model call, and stop an answer that leaks the rules.
"""

from __future__ import annotations

import re
import unicodedata

MAX_MESSAGE_CHARS = 1000
MAX_REPLY_CHARS = 3000

REFUSAL = (
    "I can only help with questions about Veritas: how giving works, where the money waits, "
    "how the work is proven and how the blockchain keeps the record public."
)
NO_ANSWER = "I could not answer that just now. Try asking it another way."

# Plain attempts to give the model new instructions, in English, Azerbaijani and Russian.
_INJECTION = re.compile(
    "|".join(
        [
            r"\b(ignore|disregard|forget|override|bypass)\b.{0,40}\b(instructions?|rules|prompts?|guidelines|directions)\b",
            r"\b(system|developer|hidden|initial|original)\s+(prompt|message|instructions?)\b",
            r"\b(reveal|print|show|repeat|output|leak|dump)\b.{0,30}\b(your|the)\s+(instructions|prompt|rules|configuration)\b",
            r"\byou\s+(are\s+now|will\s+now|must\s+now)\b",
            r"\bpretend\s+(to\s+be|you\s+are)\b",
            r"\b(jailbreak|dan\s+mode|developer\s+mode)\b",
            r"<\|[a-z_]+\|>|\[/?(inst|sys)\]|<</?sys>>",
            r"^\s*(system|developer|assistant)\s*:",
            r"(t[əe]limat|qayda).{0,30}(unut|n[əe]z[əe]r[əe]\s+alma|yox\s+say)",
            r"(unut|n[əe]z[əe]r[əe]\s+alma|yox\s+say).{0,30}(t[əe]limat|qayda)",
            r"(игнорир|забудь|забыть|отмени).{0,40}(инструкц|правил|промпт)",
            r"(систем\w*\s+промпт)",
        ]
    ),
    re.IGNORECASE | re.MULTILINE,
)

# Control and format characters, except new lines and tabs. They can hide text from a reader.
_HIDDEN = {"Cc", "Cf", "Cs", "Co", "Cn"}


def clean(text: str, limit: int = MAX_MESSAGE_CHARS) -> str:
    """The text as a person would read it: NFKC, no hidden characters, at most `limit` long."""
    text = unicodedata.normalize("NFKC", text)
    text = "".join(c for c in text if c in "\n\t" or unicodedata.category(c) not in _HIDDEN)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()[:limit]


def looks_like_injection(text: str) -> bool:
    return bool(_INJECTION.search(text))


def leaks(reply: str, canary: str) -> bool:
    """True if the answer gives away the rules: the canary, or the rules' own headings."""
    if canary.lower() in reply.lower():
        return True
    headings = ("Facts about Veritas", "How to answer", "Never write this reference")
    return sum(h.lower() in reply.lower() for h in headings) >= 2
