import React from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import { ArrowRight } from "lucide-react";

/* ============================================================
   The console's primitives — the shapes `styles/console.css` gives
   meaning to, as components so a page cannot get the markup subtly
   wrong. Ported from the class vocabulary of MuhAI's console:
   page / page-head, panel, stat, tag, seg, meter, empty, notice.
   ============================================================ */

export function Page({ children, className = "", ...rest }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={"page " + className} {...rest}>
      {children}
    </div>
  );
}

export function PageHead({
  eyebrow,
  icon: Icon,
  title,
  sub,
  actions,
}: {
  eyebrow?: React.ReactNode;
  icon?: React.ElementType;
  title: React.ReactNode;
  sub?: React.ReactNode;
  actions?: React.ReactNode;
}) {
  return (
    <header className="page-head">
      <div className="page-head__text">
        {eyebrow ? (
          <span className="page-eyebrow">
            {Icon ? <Icon size={15} strokeWidth={1.6} /> : null}
            {eyebrow}
          </span>
        ) : null}
        <h1 className="page-title">{title}</h1>
        {sub ? <p className="page-sub">{sub}</p> : null}
      </div>
      {actions ? <div className="page-actions">{actions}</div> : null}
    </header>
  );
}

export function Panel({
  title,
  sub,
  icon: Icon,
  action,
  children,
  className = "",
  flush = false,
  tone,
  ...rest
}: {
  title?: React.ReactNode;
  sub?: React.ReactNode;
  icon?: React.ElementType;
  action?: React.ReactNode;
  children?: React.ReactNode;
  className?: string;
  flush?: boolean;
  tone?: "tint" | "dark";
} & Omit<React.HTMLAttributes<HTMLElement>, "title">) {
  return (
    <section
      className={["panel", flush && "panel--flush", tone && `panel--${tone}`, className].filter(Boolean).join(" ")}
      {...rest}
    >
      {title ? (
        <div className="panel-head">
          <div className="panel-head__text">
            <h2 className="panel-title">
              {Icon ? <Icon size={16} strokeWidth={1.6} /> : null}
              {title}
            </h2>
            {sub ? <p className="panel-sub">{sub}</p> : null}
          </div>
          {action}
        </div>
      ) : null}
      {children}
    </section>
  );
}

export function Tag({
  tone,
  children,
  icon: Icon,
}: {
  tone?: "ok" | "warn" | "stop" | "info" | "dark" | "lime";
  children: React.ReactNode;
  icon?: React.ElementType;
}) {
  return (
    <span className={"tag" + (tone ? ` tag--${tone}` : "")}>
      {Icon ? <Icon size={12} strokeWidth={1.8} /> : null}
      {children}
    </span>
  );
}

export function Stat({
  label,
  value,
  unit,
  icon: Icon,
  lime = false,
  tag,
  foot,
  className = "",
}: {
  label: React.ReactNode;
  value: React.ReactNode;
  unit?: React.ReactNode;
  icon?: React.ElementType;
  lime?: boolean;
  tag?: React.ReactNode;
  foot?: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={"stat " + className}>
      <div className="stat__top">
        {Icon ? (
          <span className={"stat__icon" + (lime ? " stat__icon--lime" : "")}>
            <Icon size={17} strokeWidth={1.6} />
          </span>
        ) : null}
        <span className="stat__label">{label}</span>
        {tag ? <span style={{ marginLeft: "auto" }}>{tag}</span> : null}
      </div>
      <div className="stat__value">
        {value}
        {unit ? <small>{unit}</small> : null}
      </div>
      {foot ? <div className="stat__foot">{foot}</div> : null}
    </div>
  );
}

/** A segmented control. The live pill is one lime element that slides
 *  between options (shared layoutId), like the rail's tile. */
export function Seg<T extends string>({
  options,
  value,
  onChange,
  id,
  tint = false,
}: {
  options: { value: T; label: React.ReactNode; dot?: string }[];
  value: T;
  onChange: (v: T) => void;
  id: string;
  tint?: boolean;
}) {
  return (
    <div className={"seg" + (tint ? " seg--tint" : "")} role="group">
      {options.map((o) => {
        const on = o.value === value;
        return (
          <button key={o.value} className={on ? "is-active" : ""} aria-pressed={on} onClick={() => onChange(o.value)}>
            {on && (
              <motion.span
                layoutId={`seg-${id}`}
                className="seg__fill"
                transition={{ type: "spring", stiffness: 520, damping: 42 }}
              />
            )}
            {o.dot ? <span className="seg__dot" style={{ background: o.dot }} /> : null}
            <span>{o.label}</span>
          </button>
        );
      })}
    </div>
  );
}

/** The same control as links, for tabs that are routes. */
export function SegLinks({
  options,
  active,
  id,
}: {
  options: { to: string; label: React.ReactNode; dot?: string }[];
  active: string;
  id: string;
}) {
  return (
    <nav className="seg" aria-label="Sections">
      {options.map((o) => {
        const on = o.to === active;
        return (
          <Link key={o.to} to={o.to} className={on ? "is-active" : ""} aria-current={on ? "page" : undefined}>
            {on && (
              <motion.span
                layoutId={`seg-${id}`}
                className="seg__fill"
                transition={{ type: "spring", stiffness: 520, damping: 42 }}
              />
            )}
            {o.dot ? <span className="seg__dot" style={{ background: o.dot }} /> : null}
            <span>{o.label}</span>
          </Link>
        );
      })}
    </nav>
  );
}

export function Meter({ value, color, delay = 0 }: { value: number; color?: string; delay?: number }) {
  const [w, setW] = React.useState(0);
  React.useEffect(() => {
    const t = window.setTimeout(() => setW(Math.max(0, Math.min(100, value))), 60 + delay);
    return () => window.clearTimeout(t);
  }, [value, delay]);
  return (
    <div className="meter" role="progressbar" aria-valuenow={Math.round(value)} aria-valuemin={0} aria-valuemax={100}>
      <i style={{ width: `${w}%`, background: color }} />
    </div>
  );
}

export function Empty({
  icon: Icon,
  title,
  body,
  action,
}: {
  icon?: React.ElementType;
  title: React.ReactNode;
  body?: React.ReactNode;
  action?: React.ReactNode;
}) {
  return (
    <div className="empty">
      {Icon ? (
        <span className="empty__icon">
          <Icon size={22} strokeWidth={1.5} />
        </span>
      ) : null}
      <h3>{title}</h3>
      {body ? <p>{body}</p> : null}
      {action ? <div style={{ marginTop: 10 }}>{action}</div> : null}
    </div>
  );
}

export function Notice({
  icon: Icon,
  tone,
  children,
  action,
}: {
  icon?: React.ElementType;
  tone?: "warn" | "stop" | "lime";
  children: React.ReactNode;
  action?: React.ReactNode;
}) {
  return (
    <div className={"notice" + (tone ? ` notice--${tone}` : "")}>
      {Icon ? (
        <span className="notice__icon">
          <Icon size={17} strokeWidth={1.6} />
        </span>
      ) : null}
      <div className="notice__text">{children}</div>
      {action}
    </div>
  );
}

export function MoreLink({ to, children }: { to: string; children: React.ReactNode }) {
  return (
    <Link to={to} className="link-btn">
      {children}
      <ArrowRight size={14} />
    </Link>
  );
}

/** Rise-in for a stack of cards: one short entrance, then stillness. */
export function Rise({
  children,
  delay = 0,
  className,
  style,
}: {
  children: React.ReactNode;
  delay?: number;
  className?: string;
  style?: React.CSSProperties;
}) {
  return (
    <motion.div
      className={className}
      style={style}
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.45, ease: [0.16, 1, 0.3, 1], delay }}
    >
      {children}
    </motion.div>
  );
}

export const fmt = (n: number, digits = 0) =>
  Number.isFinite(n) ? n.toLocaleString("en-US", { maximumFractionDigits: digits, minimumFractionDigits: digits }) : "n/a";
