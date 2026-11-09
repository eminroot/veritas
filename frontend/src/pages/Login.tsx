import React, { useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import { Eye, EyeOff, Loader2, Lock, Mail } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { GoogleAuthButton } from "@/components/GoogleAuthButton";
import AuthShell from "@/components/auth/AuthShell";
import DemoSignIn from "@/components/auth/DemoSignIn";
import { Btn } from "@/components/lp/primitives";

/** The chip's glyph while the request is out — drawn on the same 24 grid as the arrow it
 *  replaces, so the chip does not resize under the swap. */
export function SpinIcon() {
  return <Loader2 className="spin" width="24" height="24" strokeWidth={1.5} />;
}

export default function Login() {
  const [showPassword, setShowPassword] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [errors, setErrors] = useState<{ email?: string; password?: string }>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();
  const { signIn, user, googleAvailable, googleError } = useAuth();
  const from = (location.state as { from?: string } | null)?.from || "/dashboard";

  // Signed in (here, by Google, or already): the console's guard decides what is next.
  useEffect(() => {
    if (user) navigate(from, { replace: true });
  }, [user, navigate, from]);

  const validate = () => {
    const next: typeof errors = {};
    if (!email.trim()) next.email = "Enter your email address";
    else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) next.email = "That email address is not valid";
    if (!password) next.password = "Enter your password";
    setErrors(next);
    return !next.email && !next.password;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!validate()) return;
    setBusy(true);
    const { error: err } = await signIn(email.trim(), password);
    setBusy(false);
    if (err) setError(err.message);
  };

  return (
    <AuthShell title="Welcome back" subtitle="Sign in to follow your donations and your projects." alt={{ to: "/signup", quiet: "New here?", cta: "Create account" }}>
      <DemoSignIn />
      {googleAvailable ? (
        <>
          <GoogleAuthButton label="Continue with Google" onError={(message) => setError(message)} />
          <div className="lp-or">or with email</div>
        </>
      ) : null}

      <form className="auth-form" onSubmit={handleSubmit} noValidate>
        <label className="field">
          <span className="field__label">Email</span>
          <span className={"field__wrap" + (errors.email ? " is-bad" : "")}>
            <Mail strokeWidth={1.6} />
            <input
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(e) => {
                setEmail(e.target.value);
                setErrors((p) => ({ ...p, email: undefined }));
              }}
              placeholder="you@example.com"
              aria-invalid={Boolean(errors.email)}
            />
          </span>
          {errors.email && <span className="field__err">{errors.email}</span>}
        </label>

        <label className="field">
          <span className="field__label">Password</span>
          <span className={"field__wrap" + (errors.password ? " is-bad" : "")}>
            <Lock strokeWidth={1.6} />
            <input
              type={showPassword ? "text" : "password"}
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => {
                setPassword(e.target.value);
                setErrors((p) => ({ ...p, password: undefined }));
              }}
              placeholder="••••••••"
              aria-invalid={Boolean(errors.password)}
            />
            <button type="button" className="field__eye" onClick={() => setShowPassword((v) => !v)} aria-label={showPassword ? "Hide password" : "Show password"}>
              {showPassword ? <EyeOff size={17} /> : <Eye size={17} />}
            </button>
          </span>
          {errors.password && <span className="field__err">{errors.password}</span>}
        </label>

        <div className="lp-auth__row">
          <span />
          <Link to="/forgot-password">Forgot your password?</Link>
        </div>

        <AnimatePresence>
          {(error || googleError) && (
            <motion.div className="lp-alert lp-alert--error" role="alert" initial={{ opacity: 0, y: -4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
              {error || googleError}
            </motion.div>
          )}
        </AnimatePresence>

        <Btn type="submit" size="wide" label={busy ? "Signing in…" : "Sign in"} icon={busy ? SpinIcon : undefined} disabled={busy} />
      </form>

      <div className="lp-auth__switch">
        New to Veritas? <Link to="/signup">Create an account</Link>
      </div>
    </AuthShell>
  );
}
