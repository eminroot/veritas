import React, { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  ArrowLeft,
  ArrowRight,
  BadgeCheck,
  Camera,
  Check,
  CircleAlert,
  FileText,
  FolderKanban,
  HardHat,
  Layers,
  ListChecks,
  MapPin,
  Plus,
  Rocket,
  Sparkles,
  Trash2,
} from "lucide-react";
import { Notice, Page, PageHead, Panel, Tag } from "@/components/console/kit";
import { ApiError } from "@/lib/api";
import { manat } from "@/lib/money";
import {
  CATEGORIES,
  PROOF_KINDS,
  emptyStage,
  examplePlan,
  fromDraft,
  getDraft,
  getPublished,
  lineAmount,
  listContractors,
  listOfficers,
  planTotal,
  publishDraft,
  saveDraft,
  siteSquare,
  stageAmount,
  stepOf,
  toDraft,
  wherePath,
  type Contractor,
  type Line,
  type Officer,
  type Plan,
  type Problem,
  type ProofLine,
  type Published,
  type Stage,
} from "@/lib/passport";
import "@/styles/planner.css";

/**
 * Plan a project, for a verified organisation: the Passport donors will give against. Six
 * steps, saved as you type; the API answers each save with whatever still stops it from being
 * published, and each step shows its own. Publishing fixes the plan for good: its fingerprint
 * is what the blockchain and every later check hold the project to.
 */

const STEPS = [
  { key: "project", label: "Project", icon: FolderKanban },
  { key: "stages", label: "Stages & budget", icon: Layers },
  { key: "proof", label: "Proof", icon: Camera },
  { key: "people", label: "Contractor & officer", icon: HardHat },
  { key: "site", label: "Site", icon: MapPin },
  { key: "check", label: "Check & publish", icon: Rocket },
] as const;
type StepKey = (typeof STEPS)[number]["key"];

const PLACES = [
  { name: "Bakı", lat: "40.40930", lng: "49.86710" },
  { name: "Gəncə", lat: "40.68280", lng: "46.36060" },
  { name: "Şəki", lat: "41.19190", lng: "47.17060" },
  { name: "Lənkəran", lat: "38.75290", lng: "48.84750" },
  { name: "Quba", lat: "41.36110", lng: "48.51340" },
];
const SIZES = ["50", "100", "200", "400"];

function Field({ label, hint, children, wide = false }: { label: string; hint?: string; children: React.ReactNode; wide?: boolean }) {
  return (
    <label className={"pl-field" + (wide ? " pl-field--wide" : "")}>
      <span className="pl-field__label">{label}</span>
      {children}
      {hint ? <span className="pl-field__hint">{hint}</span> : null}
    </label>
  );
}

function Problems({ items, onGo }: { items: Problem[]; onGo?: (step: StepKey) => void }) {
  if (!items.length) return null;
  return (
    <ul className="pl-problems">
      {items.map((p, i) => (
        <li key={`${p.path}-${i}`}>
          <CircleAlert aria-hidden="true" />
          <span>
            <b>{wherePath(p.path)}</b> {p.message}
          </span>
          {onGo ? (
            <button type="button" onClick={() => onGo(stepOf(p.path))}>
              Fix
            </button>
          ) : null}
        </li>
      ))}
    </ul>
  );
}

export default function ProjectPlanner() {
  const { projectId = "" } = useParams();
  const [base, setBase] = useState<Record<string, unknown> | null>(null);
  const [plan, setPlan] = useState<Plan | null>(null);
  const [problems, setProblems] = useState<Problem[]>([]);
  const [contractors, setContractors] = useState<Contractor[]>([]);
  const [officers, setOfficers] = useState<Officer[]>([]);
  const [step, setStep] = useState<StepKey>("project");
  const [saving, setSaving] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const [loadError, setLoadError] = useState<string | null>(null);
  const [publishedAlready, setPublishedAlready] = useState(false);
  const [published, setPublished] = useState<Published | null>(null);
  const [publishedTitle, setPublishedTitle] = useState<string | null>(null);
  const [publishing, setPublishing] = useState(false);
  const [publishError, setPublishError] = useState<string | null>(null);
  const touched = useRef(false);

  useEffect(() => {
    let live = true;
    (async () => {
      try {
        const [draft, cs, os] = await Promise.all([getDraft(projectId), listContractors(), listOfficers()]);
        if (!live) return;
        // A new project's draft has no stages yet; save the blank first stage shown, so the
        // list of what is missing matches the page.
        if (!Array.isArray(draft.draft.milestones)) touched.current = true;
        setBase(draft.draft);
        setPlan(fromDraft(draft.draft));
        setProblems(draft.problems);
        setContractors(cs.filter((c) => c.status === "verified"));
        setOfficers(os);
      } catch (err) {
        if (!live) return;
        if (err instanceof ApiError && err.code === "no_draft") {
          // Already published: show its title and fingerprint from the public record.
          setPublishedAlready(true);
          getPublished(projectId)
            .then((p) => {
              if (!live) return;
              setPublished(p.passport);
              setPublishedTitle(p.title);
            })
            .catch(() => undefined);
        } else setLoadError(err instanceof Error ? err.message : "The plan could not be loaded.");
      }
    })();
    return () => {
      live = false;
    };
  }, [projectId]);

  // Save a moment after the last change.
  useEffect(() => {
    if (!plan || !base || !touched.current) return undefined;
    setSaving("saving");
    const timer = window.setTimeout(async () => {
      try {
        const out = await saveDraft(projectId, toDraft(plan, base, contractors, officers));
        setProblems(out.problems);
        setSaving("saved");
      } catch {
        setSaving("error");
      }
    }, 700);
    return () => window.clearTimeout(timer);
  }, [plan, base, contractors, officers, projectId]);

  const update = (fn: (p: Plan) => Plan) => {
    touched.current = true;
    setPublishError(null);
    setPlan((p) => (p ? fn(p) : p));
  };
  const setStage = (i: number, patch: Partial<Stage>) =>
    update((p) => ({ ...p, stages: p.stages.map((s, k) => (k === i ? { ...s, ...patch } : s)) }));
  const setLine = (i: number, j: number, patch: Partial<Line>) =>
    setStage(i, { lines: plan ? plan.stages[i].lines.map((l, k) => (k === j ? { ...l, ...patch } : l)) : [] });
  const setProof = (i: number, j: number, patch: Partial<ProofLine>) =>
    setStage(i, { proof: plan ? plan.stages[i].proof.map((l, k) => (k === j ? { ...l, ...patch } : l)) : [] });

  const publish = async () => {
    if (!plan || !base) return;
    setPublishing(true);
    setPublishError(null);
    try {
      const out = await saveDraft(projectId, toDraft(plan, base, contractors, officers));
      setProblems(out.problems);
      if (out.problems.length) {
        setPublishError("Some things still need fixing first; they are listed above.");
        return;
      }
      setPublished(await publishDraft(projectId));
    } catch (err) {
      setPublishError(err instanceof Error ? err.message : "It could not be published. Try again.");
    } finally {
      setPublishing(false);
    }
  };

  const back = (
    <Link to="/organisation/projects" className="pl-back">
      Projects
    </Link>
  );

  if (publishedAlready || published) {
    return (
      <Page>
        <PageHead eyebrow={back} icon={FolderKanban} title={plan?.title || publishedTitle || "Published project"} />
        <Panel className="pl-done">
          <span className="pl-done__badge" aria-hidden="true">
            <BadgeCheck />
          </span>
          <h2>Published. Donors can give to it now.</h2>
          <p>
            The plan is fixed: its stages, budget, proof, contractor and officer can only change through an amendment that
            donors vote on. When a stage's work is done, your field team captures the proof in the Veritas app.
          </p>
          {published ? (
            <dl className="pl-done__ids">
              <div>
                <dt>Fingerprint (SHA-256)</dt>
                <dd>{published.sha256}</dd>
              </div>
              <div>
                <dt>IPFS address</dt>
                <dd>{published.cid}</dd>
              </div>
            </dl>
          ) : null}
          <Link to="/organisation/projects" className="btn btn--primary">
            Back to projects
          </Link>
        </Panel>
      </Page>
    );
  }

  if (loadError || !plan) {
    return (
      <Page>
        <PageHead eyebrow={back} icon={FolderKanban} title="Plan a project" />
        {loadError ? <Notice tone="warn">{loadError}</Notice> : <Panel>Loading the plan…</Panel>}
      </Page>
    );
  }

  const count = (key: StepKey) => problems.filter((p) => stepOf(p.path) === key).length;
  const index = STEPS.findIndex((s) => s.key === step);
  const mine = problems.filter((p) => stepOf(p.path) === step);
  const square = siteSquare(plan.site);

  return (
    <Page>
      <PageHead
        eyebrow={back}
        icon={FolderKanban}
        title={plan.title || "A new project"}
        sub="Saved as you type. Veritas lists anything missing; publish when nothing is."
        actions={
          <>
            <span className={"pl-saved pl-saved--" + saving}>
              {saving === "saving" ? "Saving…" : saving === "saved" ? "Saved" : saving === "error" ? "Not saved" : "Draft"}
            </span>
            <button type="button" className="btn btn--ghost" onClick={() => update(() => examplePlan(contractors[0], officers[0]))}>
              <Sparkles />
              Fill in an example
            </button>
          </>
        }
      />

      <nav className="pl-steps" aria-label="Steps">
        {STEPS.map((s, i) => {
          const n = count(s.key);
          return (
            <button key={s.key} type="button" className={"pl-step" + (s.key === step ? " is-on" : "") + (i < index ? " is-past" : "")} onClick={() => setStep(s.key)}>
              <span className="pl-step__ico">{i < index && !n ? <Check /> : <s.icon />}</span>
              <span className="pl-step__label">{s.label}</span>
              {n ? <span className="pl-step__count">{n}</span> : null}
            </button>
          );
        })}
      </nav>

      <Panel className="pl-panel">
        {step === "project" ? (
          <div className="pl-form">
            <Field label="Project title" hint="What a donor will see first, in one line." wide>
              <input value={plan.title} maxLength={200} onChange={(e) => update((p) => ({ ...p, title: e.target.value }))} placeholder="A new roof for School No. 3 in Şəki" />
            </Field>
            <Field label="What it does" hint="Two or three sentences: the problem, and what will be different when it is done." wide>
              <textarea rows={4} value={plan.summary} onChange={(e) => update((p) => ({ ...p, summary: e.target.value }))} />
            </Field>
            <div className="pl-field pl-field--wide">
              <span className="pl-field__label">Cause</span>
              <div className="pl-chips">
                {CATEGORIES.map((c) => (
                  <button key={c.value} type="button" className={plan.category === c.value ? "is-on" : ""} onClick={() => update((p) => ({ ...p, category: c.value }))}>
                    {c.label}
                  </button>
                ))}
              </div>
            </div>
          </div>
        ) : null}

        {step === "stages" ? (
          <div className="pl-stack">
            {plan.stages.map((s, i) => (
              <article className="pl-stage" key={i}>
                <header className="pl-stage__head">
                  <span className="pl-num">{i + 1}</span>
                  <input className="pl-stage__title" value={s.title} onChange={(e) => setStage(i, { title: e.target.value })} placeholder={`Stage ${i + 1}: what it is called`} />
                  <span className="pl-stage__amount">{manat(stageAmount(s), { exact: true })}</span>
                  {plan.stages.length > 1 ? (
                    <button type="button" className="pl-icon" aria-label={`Remove stage ${i + 1}`} onClick={() => update((p) => ({ ...p, stages: p.stages.filter((_, k) => k !== i) }))}>
                      <Trash2 />
                    </button>
                  ) : null}
                </header>
                <div className="pl-grid2">
                  <Field label="What will be done">
                    <textarea rows={2} value={s.deliverable} onChange={(e) => setStage(i, { deliverable: e.target.value })} />
                  </Field>
                  <Field label="How">
                    <textarea rows={2} value={s.method} onChange={(e) => setStage(i, { method: e.target.value })} />
                  </Field>
                  <Field label="Work starts">
                    <input type="date" value={s.opens} onChange={(e) => setStage(i, { opens: e.target.value })} />
                  </Field>
                  <Field label="Proof due by">
                    <input type="date" value={s.closes} onChange={(e) => setStage(i, { closes: e.target.value })} />
                  </Field>
                </div>
                <div className="pl-lines" role="group" aria-label={`Budget of stage ${i + 1}`}>
                  <div className="pl-lines__head" aria-hidden="true">
                    <span>Item</span>
                    <span>Quantity</span>
                    <span>Unit</span>
                    <span>Unit price, ₼</span>
                    <span>Amount</span>
                    <span />
                  </div>
                  {s.lines.map((l, j) => (
                    <div className="pl-lines__row" key={j}>
                      {/* The captions show only on narrow screens, where the heading row is hidden. */}
                      <label className="pl-cell">
                        <span aria-hidden="true">Item</span>
                        <input aria-label="Item" value={l.item} onChange={(e) => setLine(i, j, { item: e.target.value })} placeholder="Roofing sheets" />
                      </label>
                      <label className="pl-cell">
                        <span aria-hidden="true">Quantity</span>
                        <input aria-label="Quantity" inputMode="numeric" value={l.quantity} onChange={(e) => setLine(i, j, { quantity: e.target.value })} />
                      </label>
                      <label className="pl-cell">
                        <span aria-hidden="true">Unit</span>
                        <input aria-label="Unit" value={l.unit} onChange={(e) => setLine(i, j, { unit: e.target.value })} placeholder="m²" />
                      </label>
                      <label className="pl-cell">
                        <span aria-hidden="true">Unit price, ₼</span>
                        <input aria-label="Unit price in manat" inputMode="decimal" value={l.price} onChange={(e) => setLine(i, j, { price: e.target.value })} placeholder="0.00" />
                      </label>
                      <span className="pl-lines__amount">{manat(lineAmount(l), { exact: true })}</span>
                      <button
                        type="button"
                        className="pl-icon"
                        aria-label="Remove this line"
                        disabled={s.lines.length === 1}
                        onClick={() => setStage(i, { lines: s.lines.filter((_, k) => k !== j) })}
                      >
                        <Trash2 />
                      </button>
                    </div>
                  ))}
                </div>
                <button type="button" className="pl-add" onClick={() => setStage(i, { lines: [...s.lines, { item: "", quantity: "1", unit: "piece", price: "" }] })}>
                  <Plus /> Add a budget line
                </button>
              </article>
            ))}
            <div className="pl-stack__foot">
              <button type="button" className="btn btn--ghost" onClick={() => update((p) => ({ ...p, stages: [...p.stages, emptyStage(p.stages.length)] }))}>
                <Plus /> Add a stage
              </button>
              <span className="pl-total">
                Total <b>{manat(planTotal(plan), { exact: true })}</b>
              </span>
            </div>
          </div>
        ) : null}

        {step === "proof" ? (
          <div className="pl-stack">
            <p className="pl-lead">
              For each stage, what the field team must send before its money can be released. Every stage needs photos: the day's
              code is read from one of them, and Veritas checks where and when each was taken.
            </p>
            {plan.stages.map((s, i) => (
              <article className="pl-stage" key={i}>
                <header className="pl-stage__head">
                  <span className="pl-num">{i + 1}</span>
                  <b className="pl-stage__name">{s.title || `Stage ${i + 1}`}</b>
                </header>
                {s.proof.map((p, j) => (
                  <div className="pl-proof" key={j}>
                    <select aria-label="Kind of proof" value={p.kind} onChange={(e) => setProof(i, j, { kind: e.target.value as ProofLine["kind"] })}>
                      {PROOF_KINDS.map((k) => (
                        <option key={k.value} value={k.value}>
                          {k.label}
                        </option>
                      ))}
                    </select>
                    <input aria-label="What it must show" value={p.description} onChange={(e) => setProof(i, j, { description: e.target.value })} placeholder="What it must show" />
                    <input aria-label="How many at least" className="pl-proof__count" inputMode="numeric" value={p.count} onChange={(e) => setProof(i, j, { count: e.target.value })} />
                    <button type="button" className="pl-icon" aria-label="Remove this proof" disabled={s.proof.length === 1} onClick={() => setStage(i, { proof: s.proof.filter((_, k) => k !== j) })}>
                      <Trash2 />
                    </button>
                  </div>
                ))}
                <button type="button" className="pl-add" onClick={() => setStage(i, { proof: [...s.proof, { kind: "document", description: "", count: "1" }] })}>
                  <Plus /> Add proof
                </button>
              </article>
            ))}
          </div>
        ) : null}

        {step === "people" ? (
          <div className="pl-stack">
            <div className="pl-field pl-field--wide">
              <span className="pl-field__label">Contractor, paid straight from escrow</span>
              {contractors.length ? (
                <div className="pl-cards">
                  {contractors.map((c) => (
                    <button key={c.id} type="button" className={"pl-card" + (plan.contractor === c.voen ? " is-on" : "")} onClick={() => update((p) => ({ ...p, contractor: c.voen }))}>
                      <HardHat aria-hidden="true" />
                      <span>
                        <b>{c.legal_name}</b>
                        <em>VÖEN {c.voen} · verified</em>
                      </span>
                    </button>
                  ))}
                </div>
              ) : (
                <Notice tone="warn">
                  Your organisation has no verified contractor yet. Register the company that will do the work; Veritas checks its
                  VÖEN and bank account, and then it can be named here.
                </Notice>
              )}
            </div>
            <div className="pl-field pl-field--wide">
              <span className="pl-field__label">Verification Officer, who approves each stage</span>
              <div className="pl-cards">
                {officers.map((o) => (
                  <button key={o.id} type="button" className={"pl-card" + (plan.officer === o.address ? " is-on" : "")} onClick={() => update((p) => ({ ...p, officer: o.address }))}>
                    <BadgeCheck aria-hidden="true" />
                    <span>
                      <b>{o.name}</b>
                      <em>{o.organisation}</em>
                    </span>
                  </button>
                ))}
              </div>
              <span className="pl-field__hint">Independent of your organisation and of the contractor, from an audit firm.</span>
            </div>
          </div>
        ) : null}

        {step === "site" ? (
          <div className="pl-site">
            <div className="pl-form">
              <div className="pl-field pl-field--wide">
                <span className="pl-field__label">Start from a city</span>
                <div className="pl-chips">
                  {PLACES.map((pl) => (
                    <button key={pl.name} type="button" className={plan.site.lat === pl.lat && plan.site.lng === pl.lng ? "is-on" : ""} onClick={() => update((p) => ({ ...p, site: { ...p.site, lat: pl.lat, lng: pl.lng } }))}>
                      {pl.name}
                    </button>
                  ))}
                </div>
              </div>
              <Field label="Latitude">
                <input inputMode="decimal" value={plan.site.lat} onChange={(e) => update((p) => ({ ...p, site: { ...p.site, lat: e.target.value } }))} placeholder="40.68280" />
              </Field>
              <Field label="Longitude">
                <input inputMode="decimal" value={plan.site.lng} onChange={(e) => update((p) => ({ ...p, site: { ...p.site, lng: e.target.value } }))} placeholder="46.36060" />
              </Field>
              <div className="pl-field pl-field--wide">
                <span className="pl-field__label">Size of the site</span>
                <div className="pl-chips">
                  {SIZES.map((sz) => (
                    <button key={sz} type="button" className={plan.site.size === sz ? "is-on" : ""} onClick={() => update((p) => ({ ...p, site: { ...p.site, size: sz } }))}>
                      {sz} m
                    </button>
                  ))}
                </div>
                <span className="pl-field__hint">Photos taken outside it fail the place check, so keep it to where the work is.</span>
              </div>
            </div>
            <figure className="pl-sitemap" aria-label="The site">
              <svg viewBox="0 0 200 160" aria-hidden="true">
                <defs>
                  <pattern id="pl-grid" width="14" height="14" patternUnits="userSpaceOnUse">
                    <path d="M14 0H0V14" fill="none" stroke="rgba(36,36,38,.08)" strokeWidth="1" />
                  </pattern>
                </defs>
                <rect width="200" height="160" rx="12" fill="url(#pl-grid)" />
                {square ? (
                  <>
                    <rect x="60" y="40" width="80" height="80" rx="4" className="pl-sitemap__area" />
                    <path d="M100 84c-7-9-10-13-10-17a10 10 0 0 1 20 0c0 4-3 8-10 17z" className="pl-sitemap__pin" />
                    <circle cx="100" cy="67" r="3.4" fill="#fff" />
                    <text x="100" y="136" textAnchor="middle" className="pl-sitemap__label">
                      {plan.site.size} m × {plan.site.size} m
                    </text>
                  </>
                ) : (
                  <text x="100" y="84" textAnchor="middle" className="pl-sitemap__label">
                    Choose where the work is
                  </text>
                )}
              </svg>
              {square ? <figcaption>The same outline goes into every stage.</figcaption> : null}
            </figure>
          </div>
        ) : null}

        {step === "check" ? (
          <div className="pl-stack">
            <div className="pl-summary">
              <div>
                <span>Total</span>
                <b>{manat(planTotal(plan), { exact: true })}</b>
              </div>
              <div>
                <span>Stages</span>
                <b>{plan.stages.length}</b>
              </div>
              <div>
                <span>Contractor</span>
                <b>{contractors.find((c) => c.voen === plan.contractor)?.legal_name ?? "Not chosen"}</b>
              </div>
              <div>
                <span>Officer</span>
                <b>{officers.find((o) => o.address === plan.officer)?.name ?? "Not chosen"}</b>
              </div>
            </div>
            <ol className="pl-review">
              {plan.stages.map((s, i) => (
                <li key={i}>
                  <span className="pl-num">{i + 1}</span>
                  <span>
                    <b>{s.title || `Stage ${i + 1}`}</b>
                    <em>
                      {s.opens || "?"} to {s.closes || "?"} · {s.proof.length} kinds of proof
                    </em>
                  </span>
                  <b className="pl-review__amount">{manat(stageAmount(s), { exact: true })}</b>
                </li>
              ))}
            </ol>
            {problems.length ? (
              <>
                <p className="pl-lead">
                  <ListChecks aria-hidden="true" /> {problems.length} {problems.length === 1 ? "thing" : "things"} to fix before it can be published:
                </p>
                <Problems items={problems} onGo={setStep} />
              </>
            ) : (
              <Notice tone="lime" icon={Check}>
                Nothing missing. Publishing fixes the plan: from then on, money only moves the way it says.
              </Notice>
            )}
            {publishError ? <p className="pl-error">{publishError}</p> : null}
            <div className="pl-publish">
              <button type="button" className="btn btn--primary" disabled={publishing || problems.length > 0 || saving === "saving"} onClick={() => void publish()}>
                <Rocket />
                {publishing ? "Publishing…" : "Publish the project"}
              </button>
              <Tag tone={problems.length ? "warn" : "ok"} icon={problems.length ? CircleAlert : Check}>
                {problems.length ? `${problems.length} to fix` : "Ready"}
              </Tag>
            </div>
          </div>
        ) : null}

        {step !== "check" && mine.length ? (
          <div className="pl-here">
            <p className="pl-lead">
              <FileText aria-hidden="true" /> Still missing on this step:
            </p>
            <Problems items={mine} />
          </div>
        ) : null}

        <footer className="pl-nav">
          <button type="button" className="btn btn--ghost" disabled={index === 0} onClick={() => setStep(STEPS[Math.max(0, index - 1)].key)}>
            <ArrowLeft /> Back
          </button>
          {index < STEPS.length - 1 ? (
            <button type="button" className="btn btn--primary" onClick={() => setStep(STEPS[index + 1].key)}>
              Next: {STEPS[index + 1].label} <ArrowRight />
            </button>
          ) : null}
        </footer>
      </Panel>
    </Page>
  );
}
