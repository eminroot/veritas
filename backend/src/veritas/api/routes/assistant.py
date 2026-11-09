"""The assistant: questions about Veritas, answered by an OpenAI model.

Public: no sign-in needed. Each visitor is limited to a few questions a minute and a day,
and all visitors together to a daily number of model calls (veritas.assistant.limits).
"""

from __future__ import annotations

import threading
from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field

from veritas.assistant.config import AssistantSettings
from veritas.assistant.guard import MAX_MESSAGE_CHARS, MAX_REPLY_CHARS
from veritas.assistant.service import Assistant, Turn

router = APIRouter(prefix="/v1/assistant", tags=["assistant"])
_setup = threading.Lock()


class TurnIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["user", "assistant"]
    text: str = Field(max_length=MAX_REPLY_CHARS)
    sig: str | None = Field(default=None, max_length=128)
    """For the assistant's replies: the sig that came with them."""


class QuestionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)
    history: list[TurnIn] = Field(default_factory=list, max_length=20)
    """The conversation so far, oldest first. Only the last few messages are used."""


class AnswerOut(BaseModel):
    reply: str
    sig: str
    """Send it back with this reply in `history`, or the reply is left out."""


class StatusOut(BaseModel):
    available: bool


def assistant_of(request: Request) -> Assistant:
    """The app's assistant, made on first use from the environment."""
    state = request.app.state
    assistant = getattr(state, "assistant", None)
    if assistant is None:
        with _setup:
            assistant = getattr(state, "assistant", None)
            if assistant is None:
                assistant = Assistant(AssistantSettings(), signing_key=state.settings.hmac_key())
                state.assistant = assistant
    return assistant


@router.get("", response_model=StatusOut, summary="Is the assistant switched on")
def status(request: Request) -> StatusOut:
    return StatusOut(available=assistant_of(request).available)


@router.post("/messages", response_model=AnswerOut, summary="Ask the assistant a question")
def ask(body: QuestionIn, request: Request) -> AnswerOut:
    visitor = request.client.host if request.client else "unknown"
    history = [Turn(role=t.role, text=t.text, sig=t.sig) for t in body.history]
    answer = assistant_of(request).ask(visitor, body.message, history)
    return AnswerOut(reply=answer.reply, sig=answer.sig)
