import React from "react";
import { Building2, Camera, CircleCheck, FileCheck2, FolderKanban } from "lucide-react";
import { Btn, Eyebrow, Rv } from "./primitives";

/* For organisations: who can raise money on Veritas and the four steps to a published
   project. Shared by the landing page and /organisations, so the two cannot drift. */

export const ORG_STEPS = [
  {
    icon: Building2,
    title: "Register the organisation",
    body: "Its legal name, VÖEN, legal form and address, the director and a contact.",
  },
  {
    icon: FileCheck2,
    title: "Get verified",
    body: "Upload the registration certificate, charter, VÖEN certificate and the director's ID. Veritas checks every one.",
  },
  {
    icon: FolderKanban,
    title: "Publish a project",
    body: "Split it into milestones with a budget each, name the contractor and draw the site on a map.",
  },
  {
    icon: Camera,
    title: "Prove each milestone",
    body: "Your field team photographs the work with the Veritas app. Checked evidence releases the money to the contractor.",
  },
];

export const ORG_NEEDS = [
  "A registered public union, foundation or charity in Azerbaijan, with a VÖEN",
  "The state registration certificate and the charter",
  "The director's ID card",
  "A contractor for the work, who Veritas verifies too",
];

export default function OrgSection({ heading = true }: { heading?: boolean }) {
  return (
    <section className="lp-sec lp-sec--pad v-orgs" id="orgs">
      <div className="lp-shell">
        {heading && (
          <div className="lp-price__head">
            <Rv>
              <Eyebrow icon={Building2} tone="flat">
                For organisations
              </Eyebrow>
            </Rv>
            <Rv as="h2" delay={60} className="lp-d3">
              Raising money for a project? <span className="lp-price__hi">Prove it</span>, and donors will come.
            </Rv>
            <Rv as="p" delay={120} className="lp-lead">
              Veritas is for organisations, not personal appeals. Registered charities, foundations and public unions apply,
              get verified, and publish projects that donors can follow milestone by milestone.
            </Rv>
          </div>
        )}

        <div className="v-orgsteps" data-tour="lp-orgs">
          {ORG_STEPS.map((s, i) => (
            <Rv key={s.title} y={30} delay={i * 80} className="v-orgstep">
              <span className="v-orgstep__n">0{i + 1}</span>
              <span className="v-orgstep__ico">
                <s.icon aria-hidden="true" />
              </span>
              <h3 className="lp-d5">{s.title}</h3>
              <p>{s.body}</p>
            </Rv>
          ))}
        </div>

        <Rv delay={120} className="v-orgneeds">
          <div>
            <h3 className="lp-d5">What you need to apply</h3>
            <ul>
              {ORG_NEEDS.map((n) => (
                <li key={n}>
                  <CircleCheck aria-hidden="true" />
                  {n}
                </li>
              ))}
            </ul>
          </div>
          <div className="v-orgneeds__cta">
            <Btn to="/signup?as=organisation" label="Register your organisation" />
            <Btn to="/organisations" label="How verification works" variant="quiet" />
          </div>
        </Rv>
      </div>
    </section>
  );
}
