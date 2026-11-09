import React from "react";
import { Compass, EyeOff, Eye, HeartHandshake, Lock, ShieldCheck, Target, Users } from "lucide-react";
import { LpHero, LpPage } from "@/components/lp/LpChrome";
import { AppMock } from "@/components/lp/mocks";
import { Btn, Eyebrow, Rv } from "@/components/lp/primitives";

const PILLARS = [
  {
    icon: Users,
    badge: "Who it is for",
    body: "People in Azerbaijan and abroad who want to give, and the registered organisations that turn those gifts into schools, wells, shelters and homes.",
    tone: "a",
  },
  {
    icon: Target,
    badge: "Mission",
    body: "Make every donation traceable from the donor's card to the finished work, so that trust is something you can check rather than something you are asked for.",
    tone: "c",
  },
  {
    icon: Eye,
    badge: "Principle",
    body: "Show donors everything about their money, and nothing personal about anyone: no names, faces or homes ever go into the public record.",
    tone: "b",
  },
];

const PROCESS = [
  { title: "Give", body: "A donor gives to a verified organisation's project, by card, once or as Pay-on-Proof." },
  { title: "Hold", body: "The money is split by milestone and locked in an escrow contract on-chain." },
  { title: "Prove", body: "The field team photographs the work; five automatic checks and an officer review it." },
  { title: "Release", body: "The milestone's money goes straight to the contractor, or back to donors if the project stops." },
];

const PROMISES = [
  { icon: Lock, title: "Nobody can take the money", body: "Not the organisation, not the contractor, not Veritas. The escrow contract only pays an approved milestone or a refund." },
  { icon: ShieldCheck, title: "Every check explained", body: "When evidence fails a check, the report says which one and why, in plain words." },
  { icon: EyeOff, title: "Private by design", body: "Receipts name keys, not people. Faces and number plates are blurred before a photo is published." },
  { icon: HeartHandshake, title: "Donors have a say", body: "Every approved milestone, a new contractor or a changed plan goes to the donors' vote: one receipt, one vote." },
];

export default function About() {
  return (
    <LpPage>
      <LpHero
        eyebrow={<Eyebrow icon={ShieldCheck}>About Veritas</Eyebrow>}
        title="Giving you can see through."
        lead="Veritas is a donation platform for Azerbaijan where every gift waits in escrow and reaches the builder only when photos from the site prove the work is done."
      />

      <section className="lp-sec lp-sec--tight">
        <div className="lp-shell">
          <div className="lp-bento__grid lp-bento__grid--even">
            {PILLARS.map((c, i) => (
              <Rv key={c.badge} y={28} delay={i * 90} className={"lp-bcard lp-bcard--" + c.tone + " lp-bcard--text"}>
                <Eyebrow icon={c.icon}>{c.badge}</Eyebrow>
                <p>{c.body}</p>
              </Rv>
            ))}
          </div>
        </div>
      </section>

      <section className="lp-sec lp-sec--tight">
        <div className="lp-shell">
          <div className="lp-bento__head">
            <Rv>
              <Eyebrow icon={Compass} tone="flat">
                How it works
              </Eyebrow>
            </Rv>
            <Rv as="h2" delay={60} className="lp-d3">
              Four steps from a gift to a finished roof
            </Rv>
          </div>
          <Rv delay={80} className="lp-steps4">
            {PROCESS.map((s, i) => (
              <div className="lp-step4" key={s.title}>
                <b>0{i + 1}</b>
                <h3>{s.title}</h3>
                <p>{s.body}</p>
              </div>
            ))}
          </Rv>
        </div>
      </section>

      <section className="lp-sec lp-rail">
        <div className="lp-rail__slab lp-dark">
          <div className="lp-rail__head">
            <div>
              <Rv>
                <Eyebrow icon={Lock} tone="dark">
                  Promises
                </Eyebrow>
              </Rv>
              <Rv as="h2" delay={60} className="lp-d3">
                What Veritas guarantees, in code
              </Rv>
            </div>
          </div>
          <div className="lp-shell">
            <div className="lp-show__list lp-show__list--milestones">
              {PROMISES.map((m, i) => (
                <Rv key={m.title} delay={i * 70} className="lp-show__cell">
                  <b>
                    <i>
                      <m.icon size={16} />
                    </i>
                    {m.title}
                  </b>
                  <span>{m.body}</span>
                </Rv>
              ))}
            </div>
          </div>
        </div>
      </section>

      <div className="lp-closewrap lp-closewrap--gap">
        <section className="lp-close lp-dark">
          <div className="lp-close__head">
            <Rv as="h2" className="lp-d2">
              Follow one project before you give.
            </Rv>
            <Rv as="p" delay={60} className="lp-lead lp-lead--dark">
              Every milestone, every check and every payment is open to read.
            </Rv>
            <Rv delay={120}>
              <Btn to="/donate" label="Browse causes" variant="lime" size="lg" />
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
