import React, { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import { Bell, BookOpen, CircleHelp, Compass, FolderOpen, Lock, LogOut, Search, Settings as SettingsIcon } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { useTour } from "@/components/tour/Tour";
import { APP_TOUR } from "@/components/tour/tours";
import { useMyDonations, sumDonations } from "@/hooks/useAccount";
import { PROJECTS, projectOf } from "@/data/projects";
import { CAUSES } from "@/data/causes";
import { manat } from "@/lib/money";
import { SETTINGS, destinationsFor } from "./nav";

const POP = {
  initial: { opacity: 0, y: -6 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -6 },
  transition: { duration: 0.16, ease: [0.22, 0.8, 0.3, 1] },
} as const;

export function initials(name = "") {
  const parts = name.trim().split(/[\s._@-]+/).filter(Boolean);
  if (!parts.length) return "V";
  return (parts[0][0] + (parts[1]?.[0] || "")).toUpperCase();
}

type Result = { key: string; label: string; meta: string; to: string; icon: React.ElementType };

type Note = { key: string; tone: "ok" | "warn" | "stop"; title: string; body: string; to: string };

/** What the bell carries: the latest news on every project the person gave to, and a
 *  note when the app is running on sample data. Computed, not stored. */
export function useNotes(): Note[] {
  const { api } = useAuth();
  const { rows, sample } = useMyDonations();
  return useMemo(() => {
    const out: Note[] = [];
    if (api.status === "offline") {
      out.push({ key: "offline", tone: "warn", title: "Showing sample data", body: "The Veritas API could not be reached", to: "/settings" });
    } else if (api.status === "refused") {
      out.push({ key: "refused", tone: "stop", title: "Not connected to Veritas", body: api.message, to: "/settings" });
    }
    const seen = new Set<string>();
    for (const r of rows) {
      if (seen.has(r.projectId)) continue;
      seen.add(r.projectId);
      const update = projectOf(r.projectId)?.updates[0];
      if (update) {
        out.push({ key: `u-${r.projectId}`, tone: "ok", title: r.projectTitle, body: update.text, to: r.projectHref ?? "/donations" });
      }
    }
    if (sample && out.length === 0) {
      out.push({ key: "sample", tone: "warn", title: "Sample data", body: "Your real donations appear once the API is connected", to: "/donations" });
    }
    return out;
  }, [api, rows, sample]);
}

export default function Topbar() {
  const navigate = useNavigate();
  const { user, signOut, accountType, api } = useAuth();
  const { start } = useTour();
  const { rows } = useMyDonations();
  const escrow = sumDonations(rows).inEscrow;
  const notes = useNotes();
  const orgName = api.status === "connected" ? api.me.memberships[0]?.charity_name : undefined;

  const [query, setQuery] = useState("");
  const [cursor, setCursor] = useState(0);
  const [open, setOpen] = useState<null | "help" | "alerts" | "menu">(null);
  const rootRef = useRef<HTMLElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // One outside-click listener closes whichever popover is open.
  useEffect(() => {
    if (!open && !query) return;
    const onDown = (e: MouseEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) {
        setOpen(null);
        setQuery("");
      }
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [open, query]);

  // "/" focuses search from anywhere that is not already a text field.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName;
      if (e.key === "/" && !/INPUT|TEXTAREA|SELECT/.test(tag) && !(e.target as HTMLElement)?.isContentEditable) {
        e.preventDefault();
        inputRef.current?.focus();
      }
      if (e.key === "Escape") setOpen(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const results: Result[] = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (q.length < 1) return [];
    const pages = [...destinationsFor(accountType), SETTINGS]
      .filter((d) => `${d.label} ${d.keywords || ""}`.toLowerCase().includes(q))
      .slice(0, 5)
      .map((d) => ({ key: d.to, label: d.label, meta: "Page", to: d.to, icon: d.icon }));
    const causes = CAUSES.filter((c) => `${c.label} ${c.blurb}`.toLowerCase().includes(q))
      .slice(0, 3)
      .map((c) => ({ key: `c-${c.key}`, label: c.label, meta: "Cause", to: `/causes/${c.key}`, icon: c.icon }));
    const projects = PROJECTS.filter((p) => `${p.title} ${p.place}`.toLowerCase().includes(q))
      .slice(0, 4)
      .map((p) => ({ key: `p-${p.id}`, label: p.title, meta: `Project · ${p.place}`, to: `/projects/${p.id}`, icon: FolderOpen }));
    return [...pages, ...causes, ...projects];
  }, [query, accountType]);

  useEffect(() => setCursor(0), [query]);

  const go = (to: string) => {
    setQuery("");
    setOpen(null);
    inputRef.current?.blur();
    navigate(to);
  };

  const replayTour = () => {
    setOpen(null);
    navigate("/dashboard");
    window.setTimeout(() => start(APP_TOUR), 250);
  };

  const displayName = user?.displayName || user?.email?.split("@")[0] || "Account";
  const role = accountType === "organisation" ? orgName || "Organisation" : "Donor";

  return (
    <header className="topbar" ref={rootRef}>
      <Link to="/dashboard" className="brand" aria-label="Veritas home">
        Veritas
      </Link>

      <div className="topbar__search-wrap" data-tour="search">
        <label className="topbar__search">
          <Search size={15} strokeWidth={1.6} />
          <input
            ref={inputRef}
            placeholder="Search pages, causes, projects…"
            aria-label="Search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "ArrowDown") {
                e.preventDefault();
                setCursor((c) => Math.min(c + 1, results.length - 1));
              } else if (e.key === "ArrowUp") {
                e.preventDefault();
                setCursor((c) => Math.max(c - 1, 0));
              } else if (e.key === "Enter" && results[cursor]) {
                go(results[cursor].to);
              } else if (e.key === "Escape") {
                setQuery("");
                inputRef.current?.blur();
              }
            }}
          />
          {!query && <span className="topbar__kbd">/</span>}
        </label>
        <AnimatePresence>
          {query.trim() && (
            <motion.div className="popover popover--search" {...POP}>
              {results.length === 0 ? (
                <div className="popover__empty">Nothing matches “{query}”.</div>
              ) : (
                results.map((r, i) => (
                  <button
                    key={r.key}
                    className={"popover__row" + (i === cursor ? " is-active" : "")}
                    onMouseEnter={() => setCursor(i)}
                    onClick={() => go(r.to)}
                  >
                    <r.icon size={15} strokeWidth={1.6} />
                    <span className="grow">
                      <span className="popover__title">{r.label}</span>
                      <span className="popover__meta">{r.meta}</span>
                    </span>
                  </button>
                ))
              )}
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      <div className="topbar-meta">
        <Link to="/donations" className="chip optional" data-tour="escrow" title="Your money still waiting in escrow">
          <Lock size={14} strokeWidth={1.6} />
          In escrow <b>{manat(escrow)}</b>
        </Link>

        <div className="topbar__pop-anchor">
          <button
            className="topbar__icon-btn"
            aria-label="Help and tour"
            aria-expanded={open === "help"}
            data-tour="help"
            onClick={() => setOpen(open === "help" ? null : "help")}
          >
            <CircleHelp size={17} strokeWidth={1.6} />
          </button>
          <AnimatePresence>
            {open === "help" && (
              <motion.div className="popover popover--right" {...POP}>
                <div className="popover__label">Help</div>
                <button className="popover__row" onClick={replayTour}>
                  <Compass size={15} />
                  <span className="grow">
                    <span className="popover__title">Replay the tour</span>
                    <span className="popover__meta">A one-minute walk through your account</span>
                  </span>
                </button>
                <button className="popover__row" onClick={() => go("/about")}>
                  <BookOpen size={15} />
                  <span className="grow">
                    <span className="popover__title">How Veritas works</span>
                    <span className="popover__meta">Escrow, evidence checks and refunds</span>
                  </span>
                </button>
                <div className="popover__rule" />
                <div className="popover__label">
                  Press <span className="topbar__kbd">/</span> to search from anywhere
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        <div className="topbar__pop-anchor">
          <button
            className="topbar__icon-btn"
            aria-label={`Notifications${notes.length ? ` (${notes.length})` : ""}`}
            aria-expanded={open === "alerts"}
            data-tour="alerts"
            onClick={() => setOpen(open === "alerts" ? null : "alerts")}
          >
            <Bell size={17} strokeWidth={1.6} />
            {notes.length > 0 && <span className="topbar__notif-dot" />}
          </button>
          <AnimatePresence>
            {open === "alerts" && (
              <motion.div className="popover popover--right" {...POP}>
                <div className="popover__label">Updates</div>
                {notes.length === 0 ? (
                  <div className="popover__empty">Nothing new.</div>
                ) : (
                  notes.slice(0, 8).map((a) => (
                    <button key={a.key} className="popover__row" onClick={() => go(a.to)}>
                      <span className={`popover__dot popover__dot--${a.tone === "ok" ? "warn" : a.tone}`} data-tone={a.tone} />
                      <span className="grow">
                        <span className="popover__title">{a.title}</span>
                        <span className="popover__meta">{a.body}</span>
                      </span>
                    </button>
                  ))
                )}
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        <div className="topbar__pop-anchor">
          <button
            className="topbar__avatar"
            aria-expanded={open === "menu"}
            aria-label="Account menu"
            onClick={() => setOpen(open === "menu" ? null : "menu")}
          >
            <span className="topbar__avatar-img">{initials(displayName)}</span>
            <span className="topbar__avatar-text">
              <span className="topbar__avatar-name">{displayName}</span>
              <span className="topbar__avatar-role">{role}</span>
            </span>
          </button>
          <AnimatePresence>
            {open === "menu" && (
              <motion.div className="popover popover--right" {...POP}>
                <div className="popover__label" style={{ overflow: "hidden", textOverflow: "ellipsis" }}>
                  {user?.email}
                </div>
                <button className="popover__row" onClick={() => go("/settings")}>
                  <SettingsIcon size={15} />
                  <span className="popover__title">Settings</span>
                </button>
                <button className="popover__row" onClick={replayTour}>
                  <Compass size={15} />
                  <span className="popover__title">Replay the tour</span>
                </button>
                <div className="popover__rule" />
                <button
                  className="popover__row popover__row--danger"
                  onClick={async () => {
                    setOpen(null);
                    await signOut();
                    navigate("/login", { replace: true });
                  }}
                >
                  <LogOut size={15} />
                  <span className="popover__title" style={{ color: "inherit" }}>
                    Sign out
                  </span>
                </button>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>
    </header>
  );
}
