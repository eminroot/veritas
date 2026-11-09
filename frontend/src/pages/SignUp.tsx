import React, { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import { Building2, Eye, EyeOff, HandHeart, Lock, Mail, User } from "lucide-react";
import AuthShell from "@/components/auth/AuthShell";
import DemoSignIn from "@/components/auth/DemoSignIn";
import { GoogleAuthButton } from "@/components/GoogleAuthButton";
import { Btn } from "@/components/lp/primitives";
import { rememberAccountType, useAuth, type AccountType } from "@/contexts/AuthContext";
import { SpinIcon } from "./Login";

/**
 * Creating an account, for the two kinds of people Veritas serves: donors, and staff of
 * the organisations that receive donations. The choice decides what comes after: a donor
 * goes straight to their dashboard; an organisation is asked for its legal details and
 * documents next (onboarding), and can raise money once Veritas has verified it.
 */
const TYPES: { key: AccountType; icon: React.ElementType; title: string; sub: string }[] = [
  { key: "donor", icon: HandHeart, title: "I want to donate", sub: "Give to verified projects and follow every manat" },
  { key: "organisation", icon: Building2, title: "I represent an organisation", sub: "Register a charity, foundation or public union" },
];

/** 0..4: length, letters and digits, mixed case, a symbol. */
function strength(pw: string) {
  let s = 0;
  if (pw.length >= 8) s++;
  if (/[A-Za-z]/.test(pw) && /\d/.test(pw)) s++;
  if (/[a-z]/.test(pw) && /[A-Z]/.test(pw)) s++;
  if (/[^A-Za-z0-9]/.test(pw) || pw.length >= 14) s++;
  return s;
}
const STRENGTH = ["Too short", "Weak", "Fair", "Good", "Strong"];

export default function SignUp() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const { signUp, user, googleAvailable } = useAuth();
  const [type, setType] = useState<AccountType>(params.get("as") === "organisation" ? "organisation" : "donor");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [agree, setAgree] = useState(false);
  const [show, setShow] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const score = useMemo(() => strength(password), [password]);

  // Signed in already, or just now: the console's guard takes it from here (onboarding,
  // for organisations).
  useEffect(() => {
    if (user) navigate("/dashboard", { replace: true });
  }, [user, navigate]);

  const validate = () => {
    const next: Record<string, string> = {};
    if (!name.trim()) next.name = "Enter your name";
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) next.email = "Enter a valid email address";
    if (password.length < 8) next.password = "Use at least 8 characters";
    else if (score < 2) next.password = "Mix letters and numbers";
    if (confirm !== password) next.confirm = "The passwords do not match";
    if (!agree) next.agree = "Please accept the terms to continue";
    setErrors(next);
    return Object.keys(next).length === 0;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!validate()) return;
    setBusy(true);
    // Before the account exists, so the new account picks it up as it signs in.
    rememberAccountType(type);
    const { error: err } = await signUp(email.trim(), password, name.trim());
    setBusy(false);
    if (err) setError(err.message);
  };

  const field = (key: string) => "field__wrap" + (errors[key] ? " is-bad" : "");
  const clear = (key: string) => setErrors((p) => ({ ...p, [key]: "" }));

  return (
    <AuthShell
      title="Create your account"
      subtitle={type === "donor" ? "A minute to sign up, then give to any verified project." : "Your account first; your organisation's details come next."}
      alt={{ to: "/login", quiet: "Have an account?", cta: "Sign in" }}
      pitch={type === "organisation" ? "Raise money that donors can watch you spend, milestone by milestone." : undefined}
    >
      <DemoSignIn />
      <div className="v-types" role="radiogroup" aria-label="Account type">
        {TYPES.map((t) => (
          <button
            key={t.key}
            type="button"
            role="radio"
            aria-checked={type === t.key}
            className={"v-type" + (type === t.key ? " on" : "")}
            onClick={() => setType(t.key)}
          >
            <span className="v-type__ico">
              <t.icon aria-hidden="true" />
            </span>
            <span className="v-type__say">
              <b>{t.title}</b>
              <span>{t.sub}</span>
            </span>
          </button>
        ))}
      </div>

      {googleAvailable ? (
        <>
          <GoogleAuthButton
            label="Sign up with Google"
            onError={(message) => setError(message)}
            // Remembered before Google opens, for the account the sign-in brings back.
            onStart={() => rememberAccountType(type)}
          />
          <div className="lp-or">or sign up with email</div>
        </>
      ) : null}

      <form className="auth-form" onSubmit={handleSubmit} noValidate>
        <label className="field">
          <span className="field__label">{type === "organisation" ? "Your name (the person signing up)" : "Your name"}</span>
          <span className={field("name")}>
            <User strokeWidth={1.6} />
            <input autoComplete="name" value={name} onChange={(e) => (setName(e.target.value), clear("name"))} placeholder="Aysel Məmmədova" />
          </span>
          {errors.name && <span className="field__err">{errors.name}</span>}
        </label>

        <label className="field">
          <span className="field__label">Email</span>
          <span className={field("email")}>
            <Mail strokeWidth={1.6} />
            <input type="email" autoComplete="email" value={email} onChange={(e) => (setEmail(e.target.value), clear("email"))} placeholder="you@example.com" />
          </span>
          {errors.email && <span className="field__err">{errors.email}</span>}
        </label>

        <div className="field-row">
          <label className="field">
            <span className="field__label">Password</span>
            <span className={field("password")}>
              <Lock strokeWidth={1.6} />
              <input
                type={show ? "text" : "password"}
                autoComplete="new-password"
                value={password}
                onChange={(e) => (setPassword(e.target.value), clear("password"))}
                placeholder="At least 8 characters"
              />
              <button type="button" className="field__eye" onClick={() => setShow((v) => !v)} aria-label={show ? "Hide password" : "Show password"}>
                {show ? <EyeOff size={17} /> : <Eye size={17} />}
              </button>
            </span>
            {errors.password ? (
              <span className="field__err">{errors.password}</span>
            ) : password ? (
              <span className="v-strength" data-score={score}>
                <i />
                <i />
                <i />
                <i />
                <em>{STRENGTH[score]}</em>
              </span>
            ) : null}
          </label>

          <label className="field">
            <span className="field__label">Repeat it</span>
            <span className={field("confirm")}>
              <Lock strokeWidth={1.6} />
              <input type={show ? "text" : "password"} autoComplete="new-password" value={confirm} onChange={(e) => (setConfirm(e.target.value), clear("confirm"))} placeholder="Same again" />
            </span>
            {errors.confirm && <span className="field__err">{errors.confirm}</span>}
          </label>
        </div>

        <label className="checkbox-row">
          <input type="checkbox" checked={agree} onChange={(e) => (setAgree(e.target.checked), clear("agree"))} />
          <span>
            I agree to the <Link to="/terms">terms</Link> and the <Link to="/privacy">privacy policy</Link>.
            {errors.agree ? <em className="field__err" style={{ display: "block" }}>{errors.agree}</em> : null}
          </span>
        </label>

        <AnimatePresence>
          {error && (
            <motion.div className="lp-alert lp-alert--error" role="alert" initial={{ opacity: 0, y: -4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
              {error}
            </motion.div>
          )}
        </AnimatePresence>

        <Btn type="submit" size="wide" label={busy ? "Creating your account…" : "Create account"} icon={busy ? SpinIcon : undefined} disabled={busy} />
      </form>

      <div className="lp-auth__switch">
        Already have an account? <Link to="/login">Sign in</Link>
      </div>
    </AuthShell>
  );
}
