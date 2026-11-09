import React, { useEffect, useRef, useState } from "react";
import { ChevronDown, Download, FileSpreadsheet, FileText } from "lucide-react";
import { fileBase, type Portfolio } from "@/lib/portfolio";
import "./portfolio.css";

type Fonts = { regular: Uint8Array; medium: Uint8Array };

/** The PDF's font files, fetched once and only when someone exports. */
let fonts: Promise<Fonts> | null = null;
function loadFonts(): Promise<Fonts> {
  const get = async (name: string) => {
    const res = await fetch(`${import.meta.env.BASE_URL}fonts/${name}`);
    if (!res.ok) throw new Error(`${name}: ${res.status}`);
    return new Uint8Array(await res.arrayBuffer());
  };
  if (!fonts) {
    fonts = Promise.all([get("Roboto-Regular.ttf"), get("Roboto-Medium.ttf")]).then(([regular, medium]) => ({ regular, medium }));
    fonts.catch(() => {
      fonts = null; // try again next time
    });
  }
  return fonts;
}

function save(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 30_000);
}

/**
 * Export a portfolio as a PDF report or an Excel workbook. `build` makes the portfolio at
 * the moment of the click, so the file has the figures on screen then; the writers load
 * only when they are first used.
 */
export function ExportMenu({ build, label = "Export" }: { build: () => Portfolio; label?: string }) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState<"pdf" | "xlsx" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const root = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const away = (e: PointerEvent) => {
      if (!root.current?.contains(e.target as Node)) setOpen(false);
    };
    const key = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("pointerdown", away);
    document.addEventListener("keydown", key);
    return () => {
      document.removeEventListener("pointerdown", away);
      document.removeEventListener("keydown", key);
    };
  }, [open]);

  const run = async (kind: "pdf" | "xlsx") => {
    setOpen(false);
    setBusy(kind);
    setError(null);
    try {
      const portfolio = build();
      const report = await import("@/lib/export/report");
      const blob = kind === "pdf" ? await report.pdfReport(portfolio, await loadFonts()) : report.xlsxReport(portfolio);
      save(blob, `${fileBase(portfolio)}.${kind}`);
    } catch {
      setError("The file could not be made. Try again.");
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="pf-export" ref={root}>
      <button
        type="button"
        className="btn btn--ghost"
        aria-haspopup="menu"
        aria-expanded={open}
        disabled={busy !== null}
        onClick={() => setOpen((o) => !o)}
      >
        {busy ? <span className="pf-spinner" aria-hidden="true" /> : <Download />}
        {busy ? (busy === "pdf" ? "Making the PDF…" : "Making the workbook…") : label}
        <ChevronDown className="pf-export__chev" aria-hidden="true" />
      </button>
      {open ? (
        <div className="pf-export__menu" role="menu">
          <button type="button" role="menuitem" onClick={() => void run("pdf")}>
            <span className="pf-export__ico" aria-hidden="true">
              <FileText />
            </span>
            <span>
              <b>PDF report</b>
              <em>Designed for reading and printing</em>
            </span>
          </button>
          <button type="button" role="menuitem" onClick={() => void run("xlsx")}>
            <span className="pf-export__ico pf-export__ico--xl" aria-hidden="true">
              <FileSpreadsheet />
            </span>
            <span>
              <b>Excel workbook</b>
              <em>Every figure, ready to sort and filter</em>
            </span>
          </button>
        </div>
      ) : null}
      {error ? (
        <p className="pf-export__err" role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}
