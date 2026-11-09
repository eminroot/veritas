"""Answering one question: limits, guards, the model call, and signed replies.

The web app keeps the conversation and sends it back with each question. A visitor could
edit it, so the assistant's earlier replies come back with an HMAC that only the server can
make, and a reply without a valid one is left out: nobody can put words in its mouth. The
visitor's own earlier questions go in as theirs, and are checked like a new question.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal

import httpx

from veritas.assistant import guard, knowledge
from veritas.assistant.config import AssistantSettings
from veritas.assistant.limits import Limiter
from veritas.services.errors import TooManyRequests, Unavailable, Unprocessable

log = logging.getLogger("veritas.assistant")

MAX_TURNS = 8
"""Earlier messages sent to the model with a new question, newest first kept."""


@dataclass(frozen=True)
class Turn:
    role: Literal["user", "assistant"]
    text: str
    sig: str | None = None


@dataclass(frozen=True)
class Answer:
    reply: str
    sig: str


class Assistant:
    def __init__(
        self,
        settings: AssistantSettings,
        signing_key: bytes,
        client: httpx.Client | None = None,
        limiter: Limiter | None = None,
    ) -> None:
        self.settings = settings
        self.client = client or httpx.Client(
            base_url=settings.openai_base_url, timeout=settings.openai_timeout_seconds
        )
        self.limiter = limiter or Limiter(
            settings.assistant_per_minute,
            settings.assistant_per_day,
            settings.assistant_daily_budget,
        )
        self._key = hmac.new(signing_key, b"veritas-assistant-replies", hashlib.sha256).digest()
        self.canary = "VRT-" + secrets.token_hex(6).upper()
        self.instructions = knowledge.instructions(self.canary)

    @property
    def available(self) -> bool:
        return self.settings.enabled

    def sign(self, text: str) -> str:
        return hmac.new(self._key, text.encode("utf-8"), hashlib.sha256).hexdigest()

    def ask(self, visitor: str, message: str, history: Sequence[Turn] = ()) -> Answer:
        if not self.available:
            raise Unavailable("assistant_unavailable", "The assistant is not switched on yet.")
        question = guard.clean(message)
        if not question:
            raise Unprocessable("empty_question", "Write a question first.")
        refused = self.limiter.take(visitor)
        if refused and refused.reason == "budget":
            raise TooManyRequests(
                "assistant_daily_limit",
                "The assistant has answered as many questions as it can today. Try again tomorrow.",
                details=[{"retry_after": refused.retry_after}],
                headers={"Retry-After": str(refused.retry_after)},
            )
        if refused:
            wait = _wait(refused.retry_after)
            raise TooManyRequests(
                "assistant_rate_limited",
                f"That is a lot of questions in a short time. Try again in {wait}.",
                details=[{"retry_after": refused.retry_after}],
                headers={"Retry-After": str(refused.retry_after)},
            )
        if guard.looks_like_injection(question):
            log.info("assistant: refused an instruction in a question")
            return self._answer(guard.REFUSAL)
        reply = self._call(self._earlier(history), question)
        if guard.leaks(reply, self.canary):
            log.warning("assistant: withheld an answer that gave away its rules")
            reply = guard.REFUSAL
        return self._answer(reply)

    def _answer(self, reply: str) -> Answer:
        return Answer(reply=reply, sig=self.sign(reply))

    def _earlier(self, history: Sequence[Turn]) -> list[dict[str, str]]:
        kept: list[dict[str, str]] = []
        for turn in history:
            if turn.role == "assistant":
                if turn.sig and hmac.compare_digest(turn.sig, self.sign(turn.text)):
                    kept.append({"role": "assistant", "content": turn.text})
                continue
            text = guard.clean(turn.text)
            if text and not guard.looks_like_injection(text):
                kept.append({"role": "user", "content": text})
        return kept[-MAX_TURNS:]

    def _call(self, earlier: list[dict[str, str]], question: str) -> str:
        assert self.settings.openai_api_key is not None
        body: dict[str, Any] = {
            "model": self.settings.openai_model,
            "instructions": self.instructions,
            "input": [*earlier, {"role": "user", "content": question}],
            "max_output_tokens": self.settings.assistant_max_output_tokens,
            "store": False,
        }
        if self.settings.openai_reasoning_effort:
            body["reasoning"] = {"effort": self.settings.openai_reasoning_effort}
        headers = {"Authorization": f"Bearer {self.settings.openai_api_key.get_secret_value()}"}
        try:
            res = self.client.post("responses", json=body, headers=headers)
        except httpx.HTTPError as exc:
            log.warning("assistant: the model could not be reached (%s)", type(exc).__name__)
            raise _busy() from None
        if res.status_code != 200:
            # Never log the body: it can echo the question back.
            log.warning("assistant: the model answered %s", res.status_code)
            raise _busy()
        try:
            text = _output_text(res.json())
        except ValueError:
            raise _busy() from None
        return text[: guard.MAX_REPLY_CHARS].strip() or guard.NO_ANSWER


def _output_text(data: Any) -> str:
    """The text of a Responses API answer: every output_text part of every message."""
    parts: list[str] = []
    output = data.get("output") if isinstance(data, dict) else None
    for item in output or []:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        for part in item.get("content") or []:
            if isinstance(part, dict) and part.get("type") == "output_text":
                parts.append(str(part.get("text") or ""))
            elif isinstance(part, dict) and part.get("type") == "refusal":
                parts.append(guard.REFUSAL)
    return "\n".join(p for p in parts if p)


def _busy() -> Unavailable:
    return Unavailable(
        "assistant_busy",
        "The assistant could not answer just now. Try again in a minute.",
        headers={"Retry-After": "30"},
    )


def _wait(seconds: int) -> str:
    if seconds < 90:
        return f"{seconds} seconds"
    if seconds < 5400:
        return f"{round(seconds / 60)} minutes"
    return f"{round(seconds / 3600)} hours"
