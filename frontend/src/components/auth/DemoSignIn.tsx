import React, { useState } from "react";
import { Building2, HandHeart, Loader2 } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import type { AccountType } from "@/contexts/AuthContext";

const DEMOS: { kind: AccountType; icon: React.ElementType; title: string; body: string }[] = [
  { kind: "donor", icon: HandHeart, title: "Demo donor", body: "Give, and follow every manat" },
  { kind: "organisation", icon: Building2, title: "Demo organisation", body: "Verified: plan and publish a project" },
];

/**
 * One click into a shared demo account, a donor or a verified organisation, with no email
 * or password. The sign-in page's own effect takes it on to the dashboard.
 */
export default function DemoSignIn() {
  const { signInDemo } = useAuth();
  const [busy, setBusy] = useState<AccountType | null>(null);
  const [error, setError] = useState<string | null>(null);

  const go = async (kind: AccountType) => {
    setBusy(kind);
    setError(null);
    const { error: err } = await signInDemo(kind);
    setBusy(null);
    if (err) setError(err.message);
  };

  return (
    <section className="auth-demo" aria-label="Try the demo">
      <p className="auth-demo__k">Just looking? Try the demo, no sign-up needed</p>
      <div className="auth-demo__row">
        {DEMOS.map((d) => (
          <button key={d.kind} type="button" className="auth-demo__btn" onClick={() => void go(d.kind)} disabled={busy !== null}>
            <span className="auth-demo__ico" aria-hidden="true">
              {busy === d.kind ? <Loader2 className="spin" /> : <d.icon />}
            </span>
            <span className="auth-demo__text">
              <b>{d.title}</b>
              <em>{d.body}</em>
            </span>
          </button>
        ))}
      </div>
      {error ? (
        <p className="auth-demo__err" role="alert">
          {error}
        </p>
      ) : null}
    </section>
  );
}
