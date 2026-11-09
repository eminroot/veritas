import React, { useState } from "react";
import { Link } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import { Mail, MailCheck } from "lucide-react";
import AuthShell from "@/components/auth/AuthShell";
import { Btn } from "@/components/lp/primitives";
import { useAuth } from "@/contexts/AuthContext";
import { SpinIcon } from "./Login";

export default function ForgotPassword() {
  const { sendPasswordReset, googleAvailable } = useAuth();
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) return setError("Enter a valid email address");
    setBusy(true);
    // The same answer whether or not an account exists, so nobody can probe for one.
    const { error: err } = await sendPasswordReset(email.trim());
    setBusy(false);
    if (err) setError(err.message);
    else setSent(true);
  };

  return (
    <AuthShell
      solo
      title={sent ? "Check your email" : "Forgot your password?"}
      subtitle={sent ? `If an account exists for ${email}, a link to set a new password is on its way.` : "Enter your email and we will send you a secure link to set a new one."}
      alt={{ to: "/login", quiet: "Remembered it?", cta: "Sign in" }}
    >
      <AnimatePresence mode="wait">
        {!sent ? (
          <motion.form key="form" className="auth-form" onSubmit={handleSubmit} noValidate initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
            <label className="field">
              <span className="field__label">Email</span>
              <span className={"field__wrap" + (error ? " is-bad" : "")}>
                <Mail strokeWidth={1.6} />
                <input
                  type="email"
                  autoComplete="email"
                  value={email}
                  onChange={(e) => {
                    setEmail(e.target.value);
                    setError("");
                  }}
                  placeholder="you@example.com"
                />
              </span>
              {error && <span className="field__err">{error}</span>}
            </label>
            <Btn type="submit" size="wide" label={busy ? "Sending…" : "Send reset link"} icon={busy ? SpinIcon : undefined} disabled={busy} />
          </motion.form>
        ) : (
          <motion.div key="sent" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="v-sent">
            <span className="v-sent__ico">
              <MailCheck />
            </span>
            <ol className="v-sent__steps">
              <li>Open the email (check spam too)</li>
              <li>Follow the link to set a new password</li>
              <li>Sign in with it</li>
            </ol>
            <div className="lp-auth__actions">
              <Btn to="/login" label="Back to sign in" />
              <Btn
                type="button"
                variant="quiet"
                label="Use another email"
                onClick={() => {
                  setSent(false);
                  setEmail("");
                }}
              />
            </div>
          </motion.div>
        )}
      </AnimatePresence>
      {googleAvailable ? (
        <div className="lp-auth__switch">
          Signed up with Google? <Link to="/login">Continue with Google</Link> instead.
        </div>
      ) : null}
    </AuthShell>
  );
}
