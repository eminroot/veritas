import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@/contexts/AuthContext";
import { apiFetch } from "@/lib/api";
import type { Qapik } from "@/lib/money";
import { projectOf } from "@/data/projects";
import { SAMPLE_DONATIONS, type DonationKind } from "@/data/sample-account";
import type { CauseKey } from "@/data/causes";

/**
 * The signed-in person's donations: their own from the API, or, while they have none yet
 * (or the API is out of reach), the sample portfolio every account starts with, so the
 * dashboard always has something to show. Callers get one shape either way, plus
 * `sample`, which every page that shows them must surface ("Sample data").
 */
export type DonationRow = {
  id: string;
  projectId: string;
  projectTitle: string;
  /** Link to the project page, when the web app has one for it. */
  projectHref: string | null;
  photo: string | null;
  place: string | null;
  cause: CauseKey | null;
  date: string;
  kind: DonationKind;
  amount: Qapik;
  released: Qapik;
  inEscrow: Qapik;
  refunded: Qapik;
  receipt: string | null;
};

type ApiLeaf = { milestone: number; milestone_title: string; milestone_status: string; amount_qapik: number; status: string };
type ApiDonation = {
  id: string;
  project_id: string;
  amount_qapik: number;
  refunded_qapik: number;
  kind: string;
  status: string;
  created_at: string;
  allocations: ApiLeaf[];
};
type ApiProject = { id: string; title: string | null };

/** Paid out of escrow: the backend's milestone states after the money left it. */
const RELEASED_STATES = new Set(["released", "paid"]);

function fromSample(): DonationRow[] {
  return SAMPLE_DONATIONS.map((d) => {
    const p = projectOf(d.projectId);
    return {
      id: d.id,
      projectId: d.projectId,
      projectTitle: p?.title ?? d.projectId,
      projectHref: p ? `/projects/${p.id}` : null,
      photo: p?.photo ?? null,
      place: p?.place ?? null,
      cause: p?.cause ?? null,
      date: d.date,
      kind: d.kind,
      amount: d.amount,
      released: d.released,
      inEscrow: d.inEscrow,
      refunded: d.refunded,
      receipt: d.receipt,
    };
  });
}

async function fromApi(): Promise<DonationRow[]> {
  const donations = await apiFetch<ApiDonation[]>("/v1/donations");
  const ids = [...new Set(donations.map((d) => d.project_id))];
  const titles = new Map<string, string>();
  await Promise.all(
    ids.map(async (id) => {
      try {
        const p = await apiFetch<ApiProject>(`/v1/projects/${id}`, { auth: false });
        if (p.title) titles.set(id, p.title);
      } catch {
        /* an unpublished or removed project keeps its id as the label */
      }
    })
  );
  return donations.map((d) => {
    const released = d.allocations
      .filter((a) => RELEASED_STATES.has(a.milestone_status))
      .reduce((s, a) => s + a.amount_qapik, 0);
    const refunded = d.refunded_qapik;
    return {
      id: d.id,
      projectId: d.project_id,
      projectTitle: titles.get(d.project_id) ?? `Project ${d.project_id.slice(0, 8)}`,
      projectHref: null,
      photo: null,
      place: null,
      cause: null,
      date: d.created_at.slice(0, 10),
      kind: d.kind === "pay_on_proof" ? "pay_on_proof" : "card",
      amount: d.amount_qapik,
      released,
      refunded,
      inEscrow: Math.max(0, d.amount_qapik - released - refunded),
      receipt: null,
    };
  });
}

export function useMyDonations() {
  const { user, api } = useAuth();
  const live = api.status === "connected";
  const query = useQuery({
    queryKey: ["my-donations", user?.id, live],
    queryFn: fromApi,
    enabled: Boolean(user) && live,
  });
  if (!live || (query.isSuccess && query.data.length === 0)) {
    return { rows: fromSample(), sample: true, loading: false, error: null as string | null };
  }
  return {
    rows: query.data ?? [],
    sample: false,
    loading: query.isPending,
    error: query.error ? (query.error as Error).message : null,
  };
}

export function sumDonations(rows: DonationRow[]) {
  return rows.reduce(
    (t, r) => ({
      given: t.given + r.amount,
      released: t.released + r.released,
      inEscrow: t.inEscrow + r.inEscrow,
      refunded: t.refunded + r.refunded,
      projects: t.projects.add(r.projectId),
    }),
    { given: 0, released: 0, inEscrow: 0, refunded: 0, projects: new Set<string>() }
  );
}
