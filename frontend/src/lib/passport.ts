import { apiFetch } from "@/lib/api";
import { parseManat, type Qapik } from "@/lib/money";

/**
 * A project's Passport as the planner edits it, and the API calls around it. The form keeps
 * what people type (text), `toDraft` turns it into the Passport JSON the API checks
 * (backend: veritas/passport/models.py), and `fromDraft` reads a saved draft back. The API
 * answers every save with the problems still in the way, in plain words, so the form never
 * has to repeat its rules: it shows them.
 */

export const CATEGORIES = [
  { value: "education", label: "Education" },
  { value: "health", label: "Health" },
  { value: "water", label: "Water" },
  { value: "housing", label: "Housing" },
  { value: "environment", label: "Environment" },
  { value: "community", label: "Community" },
  { value: "emergency", label: "Emergency" },
  { value: "other", label: "Other" },
] as const;
export type Category = (typeof CATEGORIES)[number]["value"];

export const PROOF_KINDS = [
  { value: "photo", label: "Photos" },
  { value: "video", label: "Video" },
  { value: "invoice", label: "Invoice" },
  { value: "fiscal_receipt", label: "e-kassa receipt" },
  { value: "document", label: "Other document" },
] as const;
export type ProofKind = (typeof PROOF_KINDS)[number]["value"];

export type Line = { item: string; quantity: string; unit: string; price: string };
export type ProofLine = { kind: ProofKind; description: string; count: string };
export type Stage = {
  title: string;
  deliverable: string;
  method: string;
  opens: string;
  closes: string;
  lines: Line[];
  proof: ProofLine[];
};
export type Site = { lat: string; lng: string; size: string };
export type Plan = {
  title: string;
  summary: string;
  category: Category | "";
  contractor: string;
  officer: string;
  site: Site;
  stages: Stage[];
};

export type Problem = { path: string; message: string };
type Json = Record<string, unknown>;
export type DraftOut = { project_id: string; version: number; draft: Json; problems: Problem[]; updated_at: string };
export type CharityProject = {
  id: string;
  status: string;
  title: string | null;
  draft_version: number | null;
  published_version: number | null;
  created_at: string;
};
export type Contractor = { id: string; legal_name: string; voen: string; status: string; registry_status: string };
export type Officer = { id: string; name: string; organisation: string; address: string; status: string };
export type Published = { version: number; sha256: string; cid: string; published_at: string; url: string };

export const listProjects = (charityId: string) => apiFetch<CharityProject[]>(`/v1/charities/${charityId}/projects`);
export const startProject = (charityId: string) =>
  apiFetch<{ id: string }>("/v1/projects", { method: "POST", body: { charity_id: charityId } });
export const getDraft = (projectId: string) => apiFetch<DraftOut>(`/v1/projects/${projectId}/passport`);
export const saveDraft = (projectId: string, draft: Json) =>
  apiFetch<DraftOut>(`/v1/projects/${projectId}/passport`, { method: "PUT", body: draft });
export const publishDraft = (projectId: string) => apiFetch<Published>(`/v1/projects/${projectId}/publish`, { method: "POST" });
/** A published project as anyone can read it: here, its title and the Passport's fingerprint. */
export const getPublished = (projectId: string) =>
  apiFetch<{ id: string; title: string | null; passport: Published }>(`/v1/projects/${projectId}`);
export const listContractors = () => apiFetch<Contractor[]>("/v1/contractors");
export const listOfficers = () => apiFetch<Officer[]>("/v1/officers");

const whole = (text: string) => {
  const n = Number(String(text).replace(/[\s,]/g, ""));
  return Number.isFinite(n) && n > 0 ? Math.floor(n) : 0;
};

export const lineAmount = (l: Line): Qapik => whole(l.quantity) * (parseManat(l.price) ?? 0);
export const stageAmount = (s: Stage): Qapik => s.lines.reduce((t, l) => t + lineAmount(l), 0);
export const planTotal = (p: Plan): Qapik => p.stages.reduce((t, s) => t + stageAmount(s), 0);

const day = (offset: number) => {
  const d = new Date();
  d.setDate(d.getDate() + offset);
  return d.toISOString().slice(0, 10);
};

export function emptyStage(index: number): Stage {
  const opens = 14 + index * 45;
  return {
    title: "",
    deliverable: "",
    method: "",
    opens: day(opens),
    closes: day(opens + 40),
    lines: [{ item: "", quantity: "1", unit: "job", price: "" }],
    proof: [
      { kind: "photo", description: "Photos of the finished work, with the day's code in one of them", count: "4" },
      { kind: "invoice", description: "The contractor's invoice for this stage", count: "1" },
      { kind: "fiscal_receipt", description: "The e-kassa receipt for that invoice", count: "1" },
    ],
  };
}

export function emptyPlan(): Plan {
  return { title: "", summary: "", category: "", contractor: "", officer: "", site: { lat: "", lng: "", size: "100" }, stages: [emptyStage(0)] };
}

/** A filled-in example, so a first look shows a complete plan. */
export function examplePlan(contractor?: Contractor, officer?: Officer): Plan {
  const stage = (index: number, title: string, deliverable: string, method: string, lines: Line[], proof: ProofLine[]): Stage => ({
    ...emptyStage(index),
    title,
    deliverable,
    method,
    lines,
    proof,
  });
  const receipts: ProofLine[] = [
    { kind: "invoice", description: "The contractor's invoice for this stage", count: "1" },
    { kind: "fiscal_receipt", description: "The e-kassa receipt for that invoice", count: "1" },
  ];
  return {
    title: "A safe playground for Kindergarten No. 9 in Gəncə",
    summary:
      "The kindergarten's yard is bare concrete with a broken climbing frame. This turns it into a fenced playground with a soft surface, new equipment and benches for parents.",
    category: "education",
    contractor: contractor?.voen ?? "",
    officer: officer?.address ?? "",
    site: { lat: "40.68280", lng: "46.36060", size: "100" },
    stages: [
      stage(
        0,
        "Ground works and the safety surface",
        "The yard levelled, drained and covered with a rubber safety surface.",
        "Break up the old concrete, level and drain the ground, then lay 180 m² of rubber tiles.",
        [
          { item: "Breaking up, levelling and drainage", quantity: "1", unit: "job", price: "2400" },
          { item: "Rubber safety tiles", quantity: "180", unit: "m²", price: "38" },
        ],
        [{ kind: "photo", description: "The levelled ground and the finished surface", count: "6" }, ...receipts]
      ),
      stage(
        1,
        "Play equipment",
        "A climbing frame and a set of four swings, fixed to the ground.",
        "Supply certified equipment for ages 3 to 6 and anchor it in concrete footings.",
        [
          { item: "Climbing frame with a slide", quantity: "1", unit: "piece", price: "5900" },
          { item: "Swings, set of four", quantity: "1", unit: "set", price: "2300" },
          { item: "Footings and installation", quantity: "1", unit: "job", price: "1200" },
        ],
        [
          { kind: "photo", description: "The fitted equipment from every side", count: "6" },
          { kind: "video", description: "A short video of the swings and the frame in use", count: "1" },
          ...receipts,
        ]
      ),
      stage(
        2,
        "Fence and benches",
        "A 1.2 m fence around the playground and six benches.",
        "Put up a powder-coated steel fence with a self-closing gate, then fix the benches.",
        [
          { item: "Steel fence, 1.2 m", quantity: "120", unit: "m", price: "45" },
          { item: "Benches", quantity: "6", unit: "piece", price: "260" },
        ],
        [{ kind: "photo", description: "The fence, the gate and the benches", count: "4" }, ...receipts]
      ),
    ],
  };
}

/** The site as the Passport takes it: a square around the point, `size` metres a side. */
export function siteSquare(site: Site): { type: "Polygon"; coordinates: number[][][] } | undefined {
  const lat = Number(site.lat);
  const lng = Number(site.lng);
  const size = Number(site.size);
  if (!Number.isFinite(lat) || !Number.isFinite(lng) || !Number.isFinite(size) || size <= 0 || !site.lat || !site.lng) return undefined;
  const dLat = size / 2 / 111_320;
  const dLng = size / 2 / (111_320 * Math.cos((lat * Math.PI) / 180));
  const r = (n: number) => Math.round(n * 1e6) / 1e6;
  const ring = [
    [lng - dLng, lat - dLat],
    [lng + dLng, lat - dLat],
    [lng + dLng, lat + dLat],
    [lng - dLng, lat + dLat],
    [lng - dLng, lat - dLat],
  ].map(([x, y]) => [r(x), r(y)]);
  return { type: "Polygon", coordinates: [ring] };
}

/** The Passport JSON for this plan, on top of what the API put in the draft (its id,
 *  version and charity). Anything left empty goes as it is, and the API names it. */
export function toDraft(plan: Plan, base: Json, contractors: Contractor[], officers: Officer[]): Json {
  const site = siteSquare(plan.site);
  const milestones = plan.stages.map((s, index) => {
    const budget = s.lines.map((l) => {
      const quantity = whole(l.quantity);
      const unit = parseManat(l.price) ?? 0;
      return { item: l.item.trim(), quantity, unit: l.unit.trim(), unit_price_qapik: unit, amount_qapik: quantity * unit };
    });
    return {
      index,
      title: s.title.trim(),
      deliverable: s.deliverable.trim(),
      method: s.method.trim(),
      amount_qapik: budget.reduce((t, b) => t + b.amount_qapik, 0),
      budget,
      proof: s.proof.map((p) => ({ kind: p.kind, description: p.description.trim(), min_count: Math.max(1, whole(p.count)) })),
      window: { opens: s.opens, closes: s.closes },
      ...(site ? { site } : {}),
    };
  });
  const contractor = contractors.find((c) => c.voen === plan.contractor);
  const officer = officers.find((o) => o.address === plan.officer);
  const draft: Json = {
    format: base.format ?? "veritas.passport/1",
    project_id: base.project_id,
    version: base.version,
    charity: base.charity,
    title: plan.title.trim(),
    summary: plan.summary.trim(),
    currency: "AZN",
    total_qapik: milestones.reduce((t, m) => t + m.amount_qapik, 0),
    milestones,
  };
  if (plan.category) draft.category = plan.category;
  if (contractor) draft.contractor = { legal_name: contractor.legal_name, voen: contractor.voen };
  if (officer) draft.officer = { name: officer.name, organisation: officer.organisation, address: officer.address };
  return draft;
}

const text = (v: unknown) => (typeof v === "string" ? v : v == null ? "" : String(v));
const list = (v: unknown): Json[] => (Array.isArray(v) ? (v as Json[]) : []);

/** A saved draft back into the form. */
export function fromDraft(d: Json): Plan {
  const milestones = list(d.milestones);
  if (!milestones.length) return emptyPlan();
  const ring = (milestones[0].site as { coordinates?: number[][][] } | undefined)?.coordinates?.[0] ?? [];
  let site: Site = { lat: "", lng: "", size: "100" };
  if (ring.length >= 4) {
    const lats = ring.map((p) => p[1]);
    const lngs = ring.map((p) => p[0]);
    const lat = (Math.min(...lats) + Math.max(...lats)) / 2;
    site = {
      lat: lat.toFixed(5),
      lng: ((Math.min(...lngs) + Math.max(...lngs)) / 2).toFixed(5),
      size: String(Math.round((Math.max(...lats) - Math.min(...lats)) * 111_320)),
    };
  }
  const contractor = d.contractor as Json | undefined;
  const officer = d.officer as Json | undefined;
  return {
    title: text(d.title),
    summary: text(d.summary),
    category: (text(d.category) as Category) || "",
    contractor: text(contractor?.voen),
    officer: text(officer?.address),
    site,
    stages: milestones.map((m) => {
      const window = (m.window as Json | undefined) ?? {};
      return {
        title: text(m.title),
        deliverable: text(m.deliverable),
        method: text(m.method),
        opens: text(window.opens),
        closes: text(window.closes),
        lines: list(m.budget).map((b) => ({
          item: text(b.item),
          quantity: text(b.quantity),
          unit: text(b.unit),
          price: typeof b.unit_price_qapik === "number" ? (b.unit_price_qapik / 100).toFixed(2) : "",
        })),
        proof: list(m.proof).map((p) => ({ kind: (text(p.kind) as ProofKind) || "photo", description: text(p.description), count: text(p.min_count) || "1" })),
      };
    }),
  };
}

/** Which step of the planner a problem belongs to, from where the API says it is. */
export function stepOf(path: string): "project" | "stages" | "proof" | "people" | "site" | "check" {
  if (/^(title|summary|category)\b/.test(path)) return "project";
  if (/^(contractor|officer)\b/.test(path)) return "people";
  if (/\.site\b/.test(path)) return "site";
  if (/\.proof\b/.test(path)) return "proof";
  if (/^milestones\b/.test(path)) return "stages";
  return "check";
}

// The Passport's field names, as the planner labels them.
type Names = Record<string, string>;
const TOP_NAMES: Names = {
  title: "project title",
  summary: "what it does",
  category: "cause",
  contractor: "contractor",
  officer: "verification officer",
  charity: "organisation",
  total_qapik: "total",
  milestones: "stages",
};
const STAGE_NAMES: Names = {
  title: "name",
  deliverable: "what will be done",
  method: "how",
  amount_qapik: "amount",
  window: "dates",
  opens: "work starts",
  closes: "proof due by",
  site: "site",
  budget: "budget",
  proof: "proof",
};
const LINE_NAMES: Names = { item: "item", quantity: "quantity", unit: "unit", unit_price_qapik: "unit price", amount_qapik: "amount" };
const PROOF_NAMES: Names = { kind: "kind", description: "what it shows", min_count: "how many" };
const PARTY_NAMES: Names = { legal_name: "name", voen: "VÖEN", name: "name", organisation: "firm", address: "wallet address" };
const LISTS: Record<string, [string, Names]> = {
  milestones: ["stage", STAGE_NAMES],
  budget: ["budget line", LINE_NAMES],
  proof: ["proof item", PROOF_NAMES],
};

/** "milestones[0].budget[1].unit_price_qapik" as "Stage 1, budget line 2, unit price". */
export function wherePath(path: string): string {
  if (!path) return "The whole plan";
  const own = (o: object, key: string) => Object.prototype.hasOwnProperty.call(o, key);
  const parts: string[] = [];
  let names = TOP_NAMES;
  const segments = path.split(".");
  for (const [i, segment] of segments.entries()) {
    // "window.closes" reads as "proof due by" alone.
    if (segment === "window" && i < segments.length - 1) continue;
    const item = /^(\w+)\[(\d+)\]$/.exec(segment);
    if (item && own(LISTS, item[1])) {
      const [label, inner] = LISTS[item[1]];
      parts.push(`${label} ${Number(item[2]) + 1}`);
      names = inner;
      continue;
    }
    parts.push(own(names, segment) ? names[segment] : segment.replace(/_qapik$/, "").replace(/_/g, " "));
    if (names === TOP_NAMES && ["contractor", "officer", "charity"].includes(segment)) names = PARTY_NAMES;
  }
  const text = parts.join(", ");
  return text.charAt(0).toUpperCase() + text.slice(1);
}
