import React, { useCallback, useRef, useState } from "react";
import { Link } from "react-router-dom";
import {
  ArrowLeft,
  ArrowUpRight,
  BadgeCheck,
  Camera,
  CircleCheck,
  HandHeart,
  Layers,
  Link2,
  Lock,
  MessagesSquare,
  Play,
  Plus,
  RotateCcw,
  Scale,
  ShieldCheck,
  Sparkles,
  Target,
  Users,
  Vote,
  Wallet,
} from "lucide-react";
import { Arrow, Btn, Eyebrow, Rv, clamp01, smooth, useScrollVar } from "@/components/lp/primitives";
import { LpPage, useReplayLandingTour } from "@/components/lp/LpChrome";
import OrgSection from "@/components/lp/OrgSection";
import PhotoArc from "@/components/lp/PhotoArc";
import MapSection from "@/components/lp/MapSection";
import {
  AppMock,
  ChecksMock,
  CrowdMock,
  EscrowMock,
  EvidenceShowcase,
  GiveMock,
  GrowthMock,
  ProofMock,
  ReconcileMock,
  RefundMock,
  ReleaseMock,
  VoteMock,
} from "@/components/lp/mocks";
import { useFirstVisitTour } from "@/components/tour/Tour";
import { LANDING_TOUR } from "@/components/tour/tours";
import { CAUSES } from "@/data/causes";

/* ============================================================
   The landing page — MuhAI's marketing page through BestByte, with
   Veritas's story in it.

   Hero band (tinted) with a 3D stage that assembles on scroll, the
   curved photo strip of projects, a cause strip, a statement that lights
   word by word, four sticky slabs (give, escrow, proof, release), a bento
   of six, a dark showcase of the evidence checks, the donation map, the
   organisations' four steps, a dark rail of protections, a FAQ
   with a category rail and a dark closing band.

   The first visit plays the guided tour (components/tour). Every element
   it points at carries a `data-tour` attribute.
   ============================================================ */

const heroMap = (rect: DOMRect, vh: number) => smooth(clamp01((vh * 0.8 - rect.top) / (vh * 0.95)));
const sayMap = (rect: DOMRect, vh: number) => clamp01((vh * 0.6 - rect.top) / (vh * 0.95));

const NAV: [string, string][] = [
  ["#how", "How it works"],
  ["/donate", "Causes"],
  ["#map", "Map"],
  ["#orgs", "Organisations"],
  ["#faq", "FAQ"],
];

const STRIP = ["education", "water", "housing", "health", "environment", "emergency"];

const SAY =
  "Veritas holds every donation in escrow, splits it across the project's milestones, and releases each part to the builder only when photos from the site prove the work is done.";

const TRIO: [React.ElementType, string, string][] = [
  [BadgeCheck, "Verified organisations", "Registration, documents and director checked"],
  [Lock, "Escrow by default", "Held milestone by milestone, on-chain"],
  [Camera, "Paid on proof", "Photos from the site, checked five ways"],
];

const SLABS = [
  {
    badge: "Give",
    icon: HandHeart,
    title: "Give to a project, not a promise.",
    body: "Pick a verified organisation's project and an amount, once or as Pay-on-Proof: then your card is charged only when a milestone is approved.",
    foot: "Every gift gets a receipt you can check without trusting Veritas",
    Art: GiveMock,
  },
  {
    badge: "Escrow",
    icon: Lock,
    title: "Your money waits until the work is done.",
    body: "Each gift is split across the project's milestones and locked in an escrow contract. Nobody can move it outside the rules, Veritas included.",
    foot: "Released one milestone at a time, never all at once",
    Art: EscrowMock,
  },
  {
    badge: "Proof",
    icon: Camera,
    title: "Photos from the site, checked five ways.",
    body: "The field team photographs the work with the Veritas app. Each photo is checked for place, time, reuse, the checklist and tampering before anyone sees it.",
    foot: "Faces and number plates are blurred before anything is published",
    Art: ChecksMock,
  },
  {
    badge: "Release",
    icon: Sparkles,
    title: "Paid to the builder, or back to you.",
    body: "An officer approves checked evidence and the milestone's money goes straight to the contractor. If a project stops, every donor's share comes back.",
    foot: "The organisation never touches the money; the contractor is paid directly",
    Art: ReleaseMock,
  },
];
const SLAB_BG = ["/img/community-shovels.jpg", "/img/children-listening.jpg", "/img/builder-frame.jpg", "/img/builders-smiling.jpg"];

const BENTO = [
  { badge: "Fundraising", icon: Wallet, title: "Every manat raised, in the open", body: "Each project's money is shown as it arrives, released, held or still needed.", Art: GrowthMock },
  { badge: "Crowd", icon: Users, title: "Thousands of small gifts", body: "Most donations are under ₼50. Together they rebuild homes.", Art: CrowdMock },
  { badge: "Proof", icon: Link2, title: "A receipt you can check yourself", body: "Your gift's place in the escrow is recorded on-chain, with the proof that it is yours.", Art: ProofMock },
  { badge: "Refunds", icon: RotateCcw, title: "Your money comes back", body: "If a project stops, choose a refund to your card or a similar project.", Art: RefundMock },
  { badge: "Votes", icon: Vote, title: "Donors decide the big changes", body: "A new contractor or a changed plan needs the donors' vote.", Art: VoteMock },
  { badge: "Reconciled", icon: Scale, title: "Three numbers, one answer", body: "Every day the bank, the ledger and the escrow must agree. If they ever do not, releases freeze.", Art: ReconcileMock },
];
/* Three columns of alternating tall/short cards; column 2 starts short so no seam runs
   straight across the section. [card, height, wash] */
const BENTO_COLS: [number, "tall" | "short", "a" | "b" | "c"][][] = [
  [
    [0, "tall", "a"],
    [4, "short", "c"],
  ],
  [
    [1, "short", "b"],
    [3, "tall", "a"],
  ],
  [
    [2, "tall", "c"],
    [5, "short", "b"],
  ],
];

const SHOW: [React.ElementType, string, string][] = [
  [Camera, "Captured on site", "The Veritas app shows a one-time code and records where and when every photo was taken."],
  [ShieldCheck, "Checked five ways", "Place, time, reuse, the checklist and tampering, each with a reason when it fails."],
  [Link2, "Anchored on-chain", "The evidence's fingerprint is recorded before any money moves, so it cannot be swapped later."],
];

const SPOT = [
  {
    icon: Lock,
    title: "Escrow",
    body: "Donations are held by a smart contract, split by milestone. It pays only the contractor, only for an approved milestone, and refunds donors if a project stops.",
    facts: [
      ["Held in", "vAZN, backed 1:1 by manat"],
      ["Released", "Milestone by milestone"],
      ["Refunds", "Back to the card"],
    ],
  },
  {
    icon: Camera,
    title: "Evidence checks",
    body: "Every photo is checked before a person reviews it: was it taken on the site, during the session, never used before, covering the checklist, and unchanged?",
    facts: [
      ["Checks", "5, each explained"],
      ["Privacy", "Faces and plates blurred"],
      ["Originals", "Kept private"],
    ],
  },
  {
    icon: BadgeCheck,
    title: "Officer review",
    body: "A Veritas officer approves each milestone against its checked evidence and invoices. Big changes to a project go to the donors' vote.",
    facts: [
      ["Approves", "Each milestone"],
      ["Donors vote on", "Contractor or plan changes"],
      ["Overrides", "Recorded and public"],
    ],
  },
  {
    icon: Link2,
    title: "On-chain record",
    body: "Each donation batch, receipt, evidence fingerprint and payment is recorded on a public blockchain, so anyone can check the numbers without asking Veritas.",
    facts: [
      ["Network", "Polygon"],
      ["Personal data", "Never on-chain"],
      ["Reconciled", "Daily, against the bank"],
    ],
  },
];

const FAQ = {
  tabs: ["Donors", "Escrow & refunds", "Organisations", "Safety & privacy"],
  groups: [
    [
      { q: "What is Veritas?", a: "A way to give to charity projects in Azerbaijan and see exactly where the money goes. Your donation waits in escrow and is paid to the contractor milestone by milestone, only when photos from the site prove the work is done." },
      { q: "Who can I give to?", a: "Only organisations: registered public unions, foundations and charities that Veritas has verified, never personal appeals. Each project names its organisation and its contractor." },
      { q: "Do I need an account?", a: "To keep receipts, follow your projects and vote, yes. Sign up with your email and a password, or with Google, in under a minute." },
    ],
    [
      { q: "What does 'held in escrow' mean?", a: "Your money is locked in a smart contract and split across the project's milestones. It can only go to the contractor for an approved milestone, or back to donors if the project stops. Not even Veritas can move it outside those rules." },
      { q: "What if a project stops?", a: "Every donor's share that has not been paid out comes back. You choose a refund to your card or moving it to a similar project; if you do not choose in time, the project's stated default applies." },
      { q: "What is Pay-on-Proof?", a: "A pledge instead of a one-off gift: your card is charged a fixed amount each time a milestone of the project is approved, so you only ever pay for proven work." },
    ],
    [
      { q: "Can my organisation raise money here?", a: "If it is a registered public union, foundation or charity in Azerbaijan, yes. Register it, upload its documents for verification, then publish projects with milestones." },
      { q: "Who receives the money?", a: "The contractor doing the work, straight from escrow, once each milestone is approved. The organisation plans the project and proves the work; it never handles donors' money." },
      { q: "How is a milestone proven?", a: "Your field team photographs the work with the Veritas app. The photos are checked automatically, blurred where needed, signed by your organisation and reviewed by an officer." },
    ],
    [
      { q: "Is my personal information public?", a: "No. Nothing personal goes on-chain or into the public evidence. Your receipt names a key, not you, and published photos have faces and number plates blurred." },
      { q: "How do I know the photos are real?", a: "Each one is captured in the app with a one-time code, its place and time are checked against the site, it is compared with every photo ever submitted, and its fingerprint is recorded on-chain." },
      { q: "What happens if I lose my phone?", a: "Your receipts can be moved to a new key. The move waits 48 hours, during which your old key can refuse it, so someone with your number alone cannot take them." },
    ],
  ],
};

export default function Landing() {
  const stage = useRef<HTMLDivElement>(null);
  const sayRef = useRef<HTMLDivElement>(null);
  const track = useRef<HTMLDivElement>(null);

  useScrollVar(stage, heroMap);
  useScrollVar(sayRef, sayMap);

  const [tab, setTab] = useState(0);
  const [open, setOpen] = useState(0);
  const [slide, setSlide] = useState(0);

  useFirstVisitTour(LANDING_TOUR, 1100);
  const replay = useReplayLandingTour();

  const words = SAY.split(/\s+/);
  const groups = FAQ.groups[tab] || [];

  const onTrack = useCallback(() => {
    const el = track.current;
    if (!el) return;
    const max = el.scrollWidth - el.clientWidth;
    setSlide(max <= 0 ? 0 : Math.round((el.scrollLeft / max) * (SPOT.length - 1)));
  }, []);

  const move = (dir: number) => {
    const el = track.current;
    if (!el) return;
    const card = el.querySelector(".lp-rcard");
    const step = card ? card.getBoundingClientRect().width + 20 : el.clientWidth;
    el.scrollBy({ left: dir * step, behavior: "smooth" });
  };

  return (
    <LpPage links={NAV}>
      {/* ---------- hero ---------- */}
      <header className="lp-hero">
        <div className="lp-shell">
          <div className="lp-hero__head">
            <Rv y={30} delay={20}>
              <Eyebrow icon={ShieldCheck}>Transparent giving · Azerbaijan</Eyebrow>
            </Rv>
            <Rv as="h1" y={48} delay={60} className="lp-d1 lp-hero__title">
              Every manat, proven.
            </Rv>
            <Rv as="p" y={72} delay={120} className="lp-lead lp-hero__lead">
              Give to verified organisations' projects. Your money waits in escrow and reaches the builder only when photos
              from the site prove each milestone is done.
            </Rv>
            <Rv y={96} delay={180} className="lp-hero__cta">
              <span data-tour="lp-cta" style={{ display: "inline-flex" }}>
                <Btn to="/donate" label="Donate" size="lg" />
              </span>
              <div className="lp-trust">
                <div className="lp-trust__row" aria-hidden="true">
                  {[HandHeart, Lock, Camera, BadgeCheck].map((I, i) => (
                    <span className="lp-trust__dot" key={i}>
                      <I style={{ width: 14, height: 14 }} />
                    </span>
                  ))}
                </div>
                <button className="lp-tourlink" onClick={replay}>
                  <i>
                    <Play />
                  </i>
                  Take the 1-minute tour
                </button>
              </div>
            </Rv>
          </div>
        </div>

        <div className="lp-shell">
          <Rv y={128} delay={240} className="lp-rv--zoom">
            <div className="lp-stage" ref={stage} data-tour="lp-stage">
              <AppMock live />
            </div>
          </Rv>
        </div>
      </header>

      {/* ---------- the curved photo strip ---------- */}
      <section className="lp-sec v-arcsec" aria-labelledby="arc-title">
        <div className="lp-shell v-arcsec__head">
          <Rv>
            <Eyebrow icon={Layers} tone="flat">
              Being built now
            </Eyebrow>
          </Rv>
          <Rv as="h2" delay={60} className="lp-d3" id="arc-title">
            Real places, real work, every milestone in view
          </Rv>
        </div>
        <Rv y={40} delay={80}>
          <PhotoArc />
        </Rv>
      </section>

      {/* ---------- cause strip ---------- */}
      <section className="lp-sec lp-strip" id="causes">
        <div className="lp-shell">
          <Rv className="lp-strip__bar">
            <p>Give to the causes that matter to you</p>
            <Link className="lp-strip__link" to="/donate">
              <i>
                <ArrowUpRight />
              </i>
              See all {CAUSES.length} causes
            </Link>
          </Rv>
          <Rv delay={80} className="lp-strip__panel">
            {STRIP.map((k) => {
              const c = CAUSES.find((x) => x.key === k)!;
              return (
                <Link className="lp-strip__item v-strip__link" key={k} to={`/causes/${k}`}>
                  <c.icon />
                  <span>{c.label}</span>
                </Link>
              );
            })}
          </Rv>
        </div>
      </section>

      {/* ---------- statement + pinned slabs ---------- */}
      <section className="lp-sec lp-stack" id="how">
        <div className="lp-stack__pin">
          <div className="lp-say" ref={sayRef}>
            <div className="lp-shell" data-tour="lp-how">
              <h2 className="lp-say__text" style={{ "--n": words.length } as React.CSSProperties}>
                {words.map((w, i) => (
                  <span className="lp-say__w" key={i} style={{ "--i": i } as React.CSSProperties}>
                    {w}
                    {i < words.length - 1 ? " " : ""}
                  </span>
                ))}
              </h2>
              <div className="lp-say__trio">
                {TRIO.map(([I, b, s]) => (
                  <div className="lp-say__cell" key={b}>
                    <span className="lp-say__ico">
                      <I size={20} />
                    </span>
                    <div style={{ minWidth: 0 }}>
                      <b>{b}</b>
                      <span>{s}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div className="lp-slabs">
            {SLABS.map((s, i) => {
              const Art = s.Art;
              return (
                <div className={"lp-slab" + (i % 2 ? " lp-slab--flip" : "")} key={s.badge}>
                  <div className="lp-shell" style={{ width: "100%" }}>
                    <div className="lp-slab__card" data-tour={i === 0 ? "lp-slab" : undefined}>
                      <div className="lp-slab__say">
                        <Eyebrow icon={s.icon} tone="flat">
                          {s.badge}
                        </Eyebrow>
                        <h3 className="lp-d4">{s.title}</h3>
                        <p className="lp-lead">{s.body}</p>
                        <div className="lp-slab__foot">
                          <CircleCheck />
                          {s.foot}
                        </div>
                      </div>
                      <div className="lp-slab__art v-slab__photo" style={{ "--art": `url(${SLAB_BG[i % SLAB_BG.length]})` } as React.CSSProperties}>
                        <span className="lp-slab__ghost lp-slab__ghost--a" aria-hidden="true" />
                        <span className="lp-slab__ghost lp-slab__ghost--b" aria-hidden="true" />
                        <div className="lp-slab__mock">
                          <Art />
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      {/* ---------- bento ---------- */}
      <section className="lp-sec lp-sec--pad lp-bento">
        <div className="lp-shell">
          <div className="lp-bento__head">
            <Rv>
              <Eyebrow icon={Layers} tone="flat">
                In the open
              </Eyebrow>
            </Rv>
            <Rv as="h2" delay={60} className="lp-d3">
              Nothing about your gift is hidden from you
            </Rv>
            <Rv as="p" delay={120} className="lp-lead">
              Six things a donor usually has to take on trust, shown instead.
            </Rv>
          </div>

          <div className="lp-bento__grid" data-tour="lp-bento">
            {BENTO_COLS.map((col, ci) => (
              <div className="lp-bento__col" key={ci}>
                {col.map(([i, size, tone], ri) => {
                  const c = BENTO[i];
                  const Art = c.Art;
                  return (
                    <Rv key={c.title} y={32} delay={ci * 90 + ri * 60} className={"lp-bcard lp-bcard--" + size + " lp-bcard--" + tone}>
                      <Eyebrow icon={c.icon}>{c.badge}</Eyebrow>
                      <h3 className="lp-d5 lp-bcard__title">{c.title}</h3>
                      <p className="lp-bcard__body">{c.body}</p>
                      <div className="lp-bcard__art">
                        <Art />
                      </div>
                    </Rv>
                  );
                })}
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ---------- showcase: proof from the site ---------- */}
      <section className="lp-sec lp-show" id="proof">
        <div className="lp-show__slab lp-dark">
          <div className="lp-show__head">
            <Rv>
              <Eyebrow icon={Camera} tone="dark">
                Proof, not promises
              </Eyebrow>
            </Rv>
            <Rv as="h2" delay={60} className="lp-d3">
              See the work before the builder is paid.
            </Rv>
            <Rv as="p" delay={120} className="lp-lead lp-lead--dark">
              Photos from the site, checked five ways and blurred where they need to be, with a report that says exactly what
              passed and why.
            </Rv>
          </div>

          <Rv delay={160} className="lp-show__frame">
            <div className="lp-show__glass">
              <div className="lp-show__clip" style={{ height: "auto" }}>
                <EvidenceShowcase />
              </div>
            </div>
          </Rv>

          <div className="lp-show__list">
            {SHOW.map(([I, t, d], i) => (
              <Rv key={t} delay={i * 90} className="lp-show__cell">
                <b>
                  <i>
                    <I size={16} />
                  </i>
                  {t}
                </b>
                <span>{d}</span>
              </Rv>
            ))}
          </div>
        </div>
      </section>

      {/* ---------- the donation map ---------- */}
      <MapSection />

      {/* ---------- organisations ---------- */}
      <OrgSection />

      {/* ---------- protections rail ---------- */}
      <section className="lp-sec lp-rail">
        <div className="lp-rail__slab lp-dark">
          <div className="lp-rail__head">
            <div>
              <Rv>
                <Eyebrow icon={Target} tone="dark">
                  Protections
                </Eyebrow>
              </Rv>
              <Rv as="h2" delay={60} className="lp-d3">
                Four locks on every gift
              </Rv>
              <Rv as="p" delay={120} className="lp-lead lp-lead--dark">
                Drag through what stands between your money and anyone who would misuse it.
              </Rv>
            </div>
          </div>

          <div className="lp-rail__track" ref={track} onScroll={onTrack}>
            {SPOT.map((c, i) => (
              <article className={"lp-rcard lp-rcard--" + (i % 4)} key={c.title}>
                <div className="lp-rcard__say">
                  <h3 className="lp-d4">{c.title}</h3>
                  <p>{c.body}</p>
                </div>
                <div className="lp-rcard__facts">
                  <div className="lp-rcard__art" aria-hidden="true">
                    <c.icon />
                  </div>
                  {c.facts.map(([k, v]) => (
                    <div className="lp-rcard__fact" key={k}>
                      <span>{k}</span>
                      <b>{v}</b>
                    </div>
                  ))}
                </div>
              </article>
            ))}
          </div>

          <div className="lp-rail__foot">
            <div className="lp-rail__nav">
              <button onClick={() => move(-1)} aria-label="Previous">
                <ArrowLeft />
              </button>
              <button onClick={() => move(1)} aria-label="Next">
                <Arrow />
              </button>
            </div>
            <div className="lp-rail__bar" aria-hidden="true">
              {SPOT.map((c, i) => (
                <i key={c.title} className={i === slide ? "on" : ""} />
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* ---------- faq ---------- */}
      <section className="lp-sec lp-sec--pad lp-faq" id="faq">
        <div className="lp-shell">
          <div className="lp-faq__head">
            <Rv>
              <Eyebrow icon={MessagesSquare} tone="flat">
                FAQ
              </Eyebrow>
            </Rv>
            <Rv as="h2" delay={60} className="lp-d3">
              Questions, <em>answered</em>
            </Rv>
            <Rv as="p" delay={120} className="lp-lead">
              The things people ask before they give for the first time.
            </Rv>
          </div>

          <div className="lp-faq__grid" data-tour="lp-faq">
            <Rv className="lp-faq__side">
              {FAQ.tabs.map((x, i) => (
                <button
                  key={x}
                  className={i === tab ? "on" : ""}
                  onClick={() => {
                    setTab(i);
                    setOpen(0);
                  }}
                >
                  {x}
                </button>
              ))}
            </Rv>

            <div className="lp-faq__list">
              {groups.map((q, i) => (
                <Rv key={q.q} delay={i * 60} className={"lp-q" + (open === i ? " on" : "")}>
                  <button className="lp-q__btn" onClick={() => setOpen(open === i ? -1 : i)} aria-expanded={open === i}>
                    {q.q}
                    <i>
                      <Plus />
                    </i>
                  </button>
                  <div className="lp-q__body">
                    <div>
                      <p>{q.a}</p>
                    </div>
                  </div>
                </Rv>
              ))}

              <Rv delay={120} className="lp-ask">
                <div className="lp-ask__text">
                  <Eyebrow icon={MessagesSquare}>Still deciding?</Eyebrow>
                  <h3 className="lp-d4">Follow one project first</h3>
                  <p className="lp-lead">Open any project and read its milestones, evidence and payments before you give a manat.</p>
                </div>
                <Btn to="/donate" label="Browse causes" />
              </Rv>
            </div>
          </div>
        </div>
      </section>

      {/* ---------- closing ---------- */}
      <div className="lp-closewrap">
        <section className="lp-close lp-dark">
          <div className="lp-close__head">
            <Rv as="h2" className="lp-d2">
              Give where you can see it.
            </Rv>
            <Rv as="p" delay={60} className="lp-lead lp-lead--dark">
              Choose a cause, follow every milestone, and know exactly where your money is.
            </Rv>
            <Rv delay={120}>
              <Btn to="/donate" label="Donate" variant="lime" size="lg" />
            </Rv>
          </div>
          <Rv delay={160} className="lp-close__stage">
            <AppMock />
          </Rv>
        </section>
      </div>
    </LpPage>
  );
}
