/**
 * The Veritas assistant: questions about how Veritas works, answered by the API with an
 * OpenAI model. The key stays on the server; this only sends the question and the
 * conversation so far. The assistant's replies come with a signature the API checks when
 * they are sent back, so they cannot be edited on the way.
 */
import { apiFetch } from "@/lib/api";

export type ChatTurn = { role: "user" | "assistant"; text: string; sig?: string };
export type AssistantAnswer = { reply: string; sig: string };

/** As long as the API accepts; longer questions are refused there anyway. */
export const MAX_QUESTION = 1000;
/** Earlier messages sent with a question; the API uses the last eight. */
export const HISTORY_SENT = 8;

export const getAssistantStatus = () =>
  apiFetch<{ available: boolean }>("/v1/assistant", { auth: false });

export const askAssistant = (message: string, history: ChatTurn[]) =>
  apiFetch<AssistantAnswer>("/v1/assistant/messages", {
    method: "POST",
    auth: false,
    body: {
      message,
      history: history.slice(-HISTORY_SENT).map(({ role, text, sig }) => (sig ? { role, text, sig } : { role, text })),
    },
  });
