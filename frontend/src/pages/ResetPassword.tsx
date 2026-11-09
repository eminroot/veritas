import React, { useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { Eye, EyeOff, KeyRound, Lock } from "lucide-react";
import AuthShell from "@/components/auth/AuthShell";
import { Btn } from "@/components/lp/primitives";
import { useAuth } from "@/contexts/AuthContext";
import { SpinIcon } from "./Login";

/**
 * Setting a new password from the emailed link. The link carries a one-time token in its
 * fragment (#token=...), which browsers never send to a server or in a Referer header; the
 * page reads it, takes it out of the address bar, and sends it with the new password. That
 * signs the person in and ends every other session of the account.
 */
export default function ResetPassword() {
  const location = useLocation();
  const navigate = useNavigate();
  const { confirmReset } = useAuth();
  const [token] = useState(() => new URLSearchParams(location.hash.slice(1)).get("token") ?? "");
  const [linkError, setLinkError] = useState<string | null>(token ? null : "This link is incomplete. Ask for a new one.");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [show, setShow] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // The token opens the account: keep it out of the history and of a copied address.
  useEffect(() => {
    if (location.hash) navigate(location.pathname, { replace: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (password.length < 8 || !/[A-Za-z]/.test(password) || !/\d/.test(password)) {
      return setError("Use at least 8 characters, with letters and numbers.");
    }
    if (password !== confirm) return setError("The passwords do not match.");
    setBusy(true);
    const { error: err } = await confirmReset(token, password);
    setBusy(false);
    if (!err) return navigate("/dashboard", { replace: true });
    if (err.code === "reset_link_invalid") setLinkError(err.message);
    else setError(err.message);
  };

  if (linkError) {
    return (
      <AuthShell solo title="This link does not work" subtitle={linkError} alt={{ to: "/login", quiet: "Know it?", cta: "Sign in" }}>
        <Btn to="/forgot-password" label="Send a new link" size="wide" />
      </AuthShell>
    );
  }

  return (
    <AuthShell solo title="Choose a new password" subtitle="Then you are signed in, and signed out everywhere else." alt={{ to: "/login", quiet: "Remembered it?", cta: "Sign in" }}>
      <form className="auth-form" onSubmit={submit} noValidate>
        <label className="field">
          <span className="field__label">New password</span>
          <span className="field__wrap">
            <KeyRound strokeWidth={1.6} />
            <input type={show ? "text" : "password"} autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="At least 8 characters" />
            <button type="button" className="field__eye" onClick={() => setShow((v) => !v)} aria-label={show ? "Hide password" : "Show password"}>
              {show ? <EyeOff size={17} /> : <Eye size={17} />}
            </button>
          </span>
        </label>
        <label className="field">
          <span className="field__label">Repeat it</span>
          <span className="field__wrap">
            <Lock strokeWidth={1.6} />
            <input type={show ? "text" : "password"} autoComplete="new-password" value={confirm} onChange={(e) => setConfirm(e.target.value)} placeholder="Same again" />
          </span>
        </label>
        {error ? (
          <div className="lp-alert lp-alert--error" role="alert">
            {error}
          </div>
        ) : null}
        <Btn type="submit" size="wide" label={busy ? "Saving…" : "Save the new password"} icon={busy ? SpinIcon : undefined} disabled={busy} />
      </form>
      <div className="lp-auth__switch">
        <Link to="/forgot-password">Send a new link instead</Link>
      </div>
    </AuthShell>
  );
}
