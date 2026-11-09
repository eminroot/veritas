import React from "react";
import { Ban, Building2, Camera, FileCheck2, HardHat, Lock } from "lucide-react";
import { LpHero, LpPage } from "@/components/lp/LpChrome";
import OrgSection from "@/components/lp/OrgSection";
import { Btn, Eyebrow, Rv } from "@/components/lp/primitives";

/** For organisations: who can raise money on Veritas, what verification involves and how
 *  the money reaches the work. Replaces BestByte's pricing page. */
const FACTS = [
  {
    icon: FileCheck2,
    title: "What Veritas checks",
    body: "That the organisation is registered and active (VÖEN and state registration), that its charter allows the work, and that the director is who they say.",
  },
  {
    icon: HardHat,
    title: "Contractors are verified too",
    body: "The company doing the work registers with its VÖEN and IBAN. Escrow pays it directly, milestone by milestone.",
  },
  {
    icon: Lock,
    title: "You never handle donations",
    body: "Gifts go into the project's escrow, not your bank account. That is what lets donors trust a project they have never visited.",
  },
  {
    icon: Camera,
    title: "Your field team proves the work",
    body: "Members you invite photograph each milestone with the Veritas app. You review the blurred photos and sign the evidence before it is published.",
  },
  {
    icon: Ban,
    title: "What we do not accept",
    body: "Personal appeals, unregistered groups, and projects without a contractor and a site that can be photographed.",
  },
];

export default function Organisations() {
  return (
    <LpPage>
      <LpHero
        wide
        eyebrow={<Eyebrow icon={Building2}>For organisations</Eyebrow>}
        title="Raise money that donors can watch you spend."
        lead="Registered charities, foundations and public unions apply, get verified, and publish projects split into milestones. Each milestone is paid to the contractor when your evidence passes the checks."
      >
        <Btn to="/signup?as=organisation" label="Register your organisation" size="lg" />
      </LpHero>

      <OrgSection heading={false} />

      <section className="lp-sec lp-sec--pad">
        <div className="lp-shell">
          <div className="lp-bento__head">
            <Rv as="h2" className="lp-d3">
              Good to know before you apply
            </Rv>
          </div>
          <div className="v-facts">
            {FACTS.map((f, i) => (
              <Rv key={f.title} y={26} delay={i * 70} className="v-fact">
                <span className="v-fact__ico">
                  <f.icon aria-hidden="true" />
                </span>
                <h3 className="lp-d5">{f.title}</h3>
                <p>{f.body}</p>
              </Rv>
            ))}
          </div>
        </div>
      </section>
    </LpPage>
  );
}
