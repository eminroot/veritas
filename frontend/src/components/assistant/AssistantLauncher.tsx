import { useEffect, useState } from "react";
import { useLocation } from "react-router-dom";
import { MessageCircle, X } from "lucide-react";
import { AssistantChat } from "./AssistantChat";

/** The chat button in the bottom right corner of every page, and the panel it opens. */
export function AssistantLauncher() {
  const { pathname } = useLocation();
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  // The assistant's own page already shows the chat.
  if (pathname.startsWith("/assistant")) return null;

  return (
    <div className="vchat-root">
      {open && (
        <div className="vchat-pop" role="dialog" aria-label="Ask Veritas">
          <AssistantChat compact autoFocus onClose={() => setOpen(false)} />
        </div>
      )}
      <button
        type="button"
        className={"vchat-fab" + (open ? " is-open" : "")}
        aria-label={open ? "Close the assistant" : "Ask Veritas a question"}
        aria-expanded={open}
        title={open ? "Close" : "Ask Veritas"}
        onClick={() => setOpen((o) => !o)}
      >
        {open ? <X size={24} /> : <MessageCircle size={26} />}
      </button>
    </div>
  );
}
