import React from "react";
import { Link } from "react-router-dom";
import { Scale } from "lucide-react";
import { LpHero, LpPage } from "@/components/lp/LpChrome";
import { Eyebrow } from "@/components/lp/primitives";

/**
 * Terms and Privacy, in plain language. Both are drafts for the pilot and say so: they
 * have not been through a lawyer yet, and the final versions will replace them before
 * real donations open.
 */

interface Section {
  heading: string;
  body: React.ReactNode;
}

const LAST_UPDATED = "8 November 2026";

const TERMS: Section[] = [
  {
    heading: "1. What Veritas is",
    body: (
      <>
        Veritas lets you give to projects run by organisations that Veritas has verified. Donations are held in escrow and
        paid to each project's contractor milestone by milestone, after evidence from the site has been checked and
        approved. These terms apply to everyone who uses the website or the app.
      </>
    ),
  },
  {
    heading: "2. Your account",
    body: (
      <>
        Sign in with an email address and password, or with Google. Keep your password to yourself, and tell us at once if
        you think someone else has used your account. Veritas checks your password itself and keeps only a scrambled form
        of it; signing in with Google goes through Google Firebase. Your account is created when you sign up, or the first
        time you continue with Google.
      </>
    ),
  },
  {
    heading: "3. Donations",
    body: (
      <>
        A donation is held in escrow and split across the project's milestones. It is released only to the contractor named
        in the project, for an approved milestone. If a project stops, the part not yet paid out is refunded to your card,
        or moved to a similar project if you choose; if you do not choose in time, the project's stated default applies.
        Until card payments open, giving on this site is a preview and nothing is charged.
      </>
    ),
  },
  {
    heading: "4. Organisations",
    body: (
      <>
        Only registered organisations may raise money, and only after Veritas has verified their registration, documents and
        director. An organisation is responsible for the truth of everything it publishes and for the evidence its field team
        submits. Veritas may suspend an organisation whose evidence or documents turn out to be false.
      </>
    ),
  },
  {
    heading: "5. What you may not do",
    body: (
      <>
        Do not submit evidence you did not capture on the site, try to receive money meant for someone else, interfere with
        the service or other people's accounts, or use Veritas to raise money for anything unlawful.
      </>
    ),
  },
  {
    heading: "6. The public record",
    body: (
      <>
        Donation batches, receipts, evidence fingerprints and payments are recorded on a public blockchain so that anyone can
        check them. These records hold no personal data, and by their nature they cannot be edited or deleted.
      </>
    ),
  },
  {
    heading: "7. Changes",
    body: (
      <>
        This is a draft for the pilot. We will publish the final terms before real donations open, and tell you about any
        change that affects money you have given.
      </>
    ),
  },
];

const PRIVACY: Section[] = [
  {
    heading: "1. What we collect",
    body: (
      <>
        Your email address and name (with Google, the name and email address Google shares with us).
        For each donation: the amount, the project and the last four digits of the card. For organisations: the details and
        documents needed to verify them.
      </>
    ),
  },
  {
    heading: "2. What never goes public",
    body: (
      <>
        Nothing personal is written to the blockchain or into published evidence. Your receipt is tied to a key, not to your
        name. Photos from project sites are rebuilt from their pixels with faces and number plates blurred, and their
        metadata removed, before they are published; the originals stay private.
      </>
    ),
  },
  {
    heading: "3. Who processes it",
    body: (
      <>
        If you continue with Google, Google Firebase confirms your Google account to us; passwords never leave Veritas.
        Card payments are processed by a licensed payment provider, which keeps the card
        itself; Veritas never sees a full card number. Organisation documents are stored privately and seen only by the
        Veritas staff who verify them.
      </>
    ),
  },
  {
    heading: "4. How long we keep it",
    body: (
      <>
        Account details for as long as you have an account. Donation records for as long as the law requires financial records
        to be kept. Verification documents for as long as the organisation is on Veritas, and for the retention period the law
        sets after that.
      </>
    ),
  },
  {
    heading: "5. Your rights",
    body: (
      <>
        You can ask for a copy of your personal data, have it corrected, or have your account deleted. Records already on the
        blockchain cannot be deleted, but they contain nothing that identifies you.
      </>
    ),
  },
  {
    heading: "6. Cookies and storage",
    body: (
      <>
        Only what keeps you signed in and remembers the choices you make on the site, such as whether you have seen the tour.
        There are no advertising or cross-site tracking cookies.
      </>
    ),
  },
];

function LegalPage({ title, intro, sections }: { title: string; intro: string; sections: Section[] }) {
  return (
    <LpPage>
      <LpHero
        eyebrow={
          <Eyebrow icon={Scale} tone="">
            Draft for the pilot · last updated {LAST_UPDATED}
          </Eyebrow>
        }
        title={title}
        lead={intro}
      />
      <section className="lp-sec" style={{ paddingBottom: 120 }}>
        <div className="lp-shell">
          <article className="lp-doc">
            {sections.map((s) => (
              <section key={s.heading}>
                <h2>{s.heading}</h2>
                <p>{s.body}</p>
              </section>
            ))}
            <p style={{ marginTop: 40 }}>
              <Link to="/signup" style={{ borderBottom: "1px solid rgba(36,36,38,.25)", color: "#242426" }}>
                ← Back to sign up
              </Link>
            </p>
          </article>
        </div>
      </section>
    </LpPage>
  );
}

export function Terms() {
  return (
    <LegalPage
      title="Terms of Service"
      intro="How Veritas works for donors and organisations, kept short and readable rather than exhaustive."
      sections={TERMS}
    />
  );
}

export function Privacy() {
  return (
    <LegalPage
      title="Privacy Policy"
      intro="What Veritas collects, why, who processes it, and what never becomes public."
      sections={PRIVACY}
    />
  );
}
