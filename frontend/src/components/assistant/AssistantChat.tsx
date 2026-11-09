import React, { useEffect, useRef, useState } from "react";
import { ArrowUp, RotateCcw, Sparkles, X } from "lucide-react";
import { ApiError } from "@/lib/api";
import { askAssistant, getAssistantStatus, MAX_QUESTION, type ChatTurn } from "@/lib/assistant";
import "./assistant.css";

/** The conversation lives in this tab only, like a support chat. */
const STORE = "veritas.assistant.v1";
const KEPT = 30;

const SUGGESTIONS = [
  "Where does my donation go?",
  "How does the blockchain keep it transparent?",
  "What happens if a project stops?",
  "How do I know the photos are real?",
];

function load(): ChatTurn[] {
  try {
    const turns: unknown = JSON.parse(sessionStorage.getItem(STORE) || "[]");
    if (!Array.isArray(turns)) return [];
    return turns
      .filter(
        (t): t is ChatTurn =>
          !!t && (t.role === "user" || t.role === "assistant") && typeof t.text === "string",
      )
      .slice(-KEPT);
  } catch {
    return [];
  }
}

function save(turns: ChatTurn[]) {
  try {
    sessionStorage.setItem(STORE, JSON.stringify(turns.slice(-KEPT)));
  } catch {
    // Private windows can refuse storage: the chat still works, it just is not kept.
  }
}

/** Whether the API has a key, asked once per page load. */
let availability: Promise<boolean> | null = null;
function isAvailable(): Promise<boolean> {
  availability ??= getAssistantStatus()
    .then((s) => s.available)
    .catch(() => true);
  return availability;
}

function problem(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.code === "assistant_unavailable")
      return "The assistant is not switched on yet. It answers once the team adds its key.";
    if (err.code === "invalid_request") return `Keep the question under ${MAX_QUESTION.toLocaleString("en")} characters.`;
    if (err.offline || err.code === "timeout") return "The assistant could not be reached. Check the connection and try again.";
    return err.message;
  }
  return "Something went wrong. Try again.";
}

/** Plain text with short lists and **bold**, built as React elements: no HTML is ever injected. */
function Reply({ text }: { text: string }) {
  const blocks: React.ReactNode[] = [];
  let list: string[] = [];
  const flush = () => {
    if (list.length) blocks.push(<ul key={`l${blocks.length}`}>{list.map((item, i) => <li key={i}>{inline(item)}</li>)}</ul>);
    list = [];
  };
  for (const line of text.split("\n")) {
    const item = line.match(/^\s*(?:[-*•]|\d+[.)])\s+(.*)$/);
    if (item) {
      list.push(item[1]);
      continue;
    }
    flush();
    if (line.trim()) blocks.push(<p key={`p${blocks.length}`}>{inline(line)}</p>);
  }
  flush();
  return <>{blocks}</>;
}

function inline(text: string): React.ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*)/g).map((part, i) =>
    part.startsWith("**") && part.endsWith("**") && part.length > 4 ? <strong key={i}>{part.slice(2, -2)}</strong> : part,
  );
}

export function AssistantChat({
  compact = false,
  autoFocus = false,
  onClose,
}: {
  /** The small panel the corner button opens, with its own header. */
  compact?: boolean;
  autoFocus?: boolean;
  onClose?: () => void;
}) {
  const [turns, setTurns] = useState<ChatTurn[]>(load);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [available, setAvailable] = useState(true);
  const listRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    let live = true;
    isAvailable().then((ok) => live && setAvailable(ok));
    return () => {
      live = false;
    };
  }, []);

  useEffect(() => {
    save(turns);
    const list = listRef.current;
    if (list) list.scrollTop = list.scrollHeight;
  }, [turns, busy]);

  useEffect(() => {
    if (autoFocus) inputRef.current?.focus();
  }, [autoFocus]);

  const send = async (text: string) => {
    const question = text.trim().slice(0, MAX_QUESTION);
    if (!question || busy) return;
    const history = turns;
    setError(null);
    setTurns([...history, { role: "user", text: question }]);
    setDraft("");
    setBusy(true);
    try {
      const answer = await askAssistant(question, history);
      setTurns((now) => [...now, { role: "assistant", text: answer.reply, sig: answer.sig }]);
    } catch (err) {
      // Take the question back, so it can be sent again as it was.
      setTurns(history);
      setDraft(question);
      setError(problem(err));
      if (err instanceof ApiError && err.code === "assistant_unavailable") setAvailable(false);
    } finally {
      setBusy(false);
      inputRef.current?.focus();
    }
  };

  const restart = () => {
    setTurns([]);
    setError(null);
    inputRef.current?.focus();
  };

  return (
    <section className={"vchat" + (compact ? " vchat--compact" : "")} aria-label="Ask Veritas">
      {compact && (
        <header className="vchat__head">
          <span className="vchat__badge" aria-hidden="true">
            <Sparkles size={16} />
          </span>
          <div className="vchat__titles">
            <strong>Ask Veritas</strong>
            <span>Giving, escrow, proof and the blockchain</span>
          </div>
          {turns.length > 0 && (
            <button type="button" className="vchat__icon" onClick={restart} aria-label="Start a new conversation" title="New conversation">
              <RotateCcw size={16} />
            </button>
          )}
          {onClose && (
            <button type="button" className="vchat__icon" onClick={onClose} aria-label="Close the assistant" title="Close">
              <X size={18} />
            </button>
          )}
        </header>
      )}

      <div className="vchat__list" ref={listRef} aria-live="polite">
        {turns.length === 0 && (
          <div className="vchat__hello">
            <p>
              Hello! Ask me how Veritas works: where your money waits, how the work is proven and how the blockchain keeps
              every step public.
            </p>
            <div className="vchat__chips">
              {SUGGESTIONS.map((s) => (
                <button key={s} type="button" className="vchat__chip" onClick={() => send(s)} disabled={busy || !available}>
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}
        {turns.map((t, i) => (
          <div key={i} className={"vchat__msg vchat__msg--" + t.role}>
            {t.role === "assistant" ? <Reply text={t.text} /> : <p>{t.text}</p>}
          </div>
        ))}
        {busy && (
          <div className="vchat__msg vchat__msg--assistant vchat__msg--typing" aria-label="The assistant is writing">
            <span />
            <span />
            <span />
          </div>
        )}
      </div>

      {(error || !available) && (
        <p className="vchat__error" role="alert">
          {error || "The assistant is not switched on yet. It answers once the team adds its key."}
        </p>
      )}

      <form
        className="vchat__form"
        onSubmit={(e) => {
          e.preventDefault();
          send(draft);
        }}
      >
        <textarea
          ref={inputRef}
          className="vchat__input"
          value={draft}
          maxLength={MAX_QUESTION}
          rows={compact ? 1 : 2}
          placeholder="Ask a question about Veritas"
          aria-label="Your question"
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              send(draft);
            }
          }}
        />
        <button type="submit" className="vchat__send" disabled={busy || !draft.trim() || !available} aria-label="Send">
          <ArrowUp size={18} />
        </button>
      </form>
      {!compact && turns.length > 0 && (
        <p className="vchat__note">
          <button type="button" className="vchat__link" onClick={restart}>
            Start a new conversation
          </button>
        </p>
      )}
    </section>
  );
}
