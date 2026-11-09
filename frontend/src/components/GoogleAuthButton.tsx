import { useState } from "react";
import { motion, useReducedMotion } from "framer-motion";
import { Loader2 } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";

/** Google's mark. Inlined because the brand guidelines require the exact 4-colour logo,
 *  and lucide has no equivalent. */
function GoogleMark({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 18 18" aria-hidden="true">
      <path fill="#4285F4" d="M17.64 9.2c0-.64-.06-1.25-.16-1.84H9v3.48h4.84a4.14 4.14 0 0 1-1.8 2.72v2.26h2.92c1.7-1.57 2.68-3.88 2.68-6.62Z" />
      <path fill="#34A853" d="M9 18c2.43 0 4.47-.8 5.96-2.18l-2.92-2.26c-.8.54-1.84.86-3.04.86-2.34 0-4.32-1.58-5.02-3.7H.96v2.34A9 9 0 0 0 9 18Z" />
      <path fill="#FBBC05" d="M3.98 10.72a5.4 5.4 0 0 1 0-3.44V4.94H.96a9 9 0 0 0 0 8.12l3.02-2.34Z" />
      <path fill="#EA4335" d="M9 3.58c1.32 0 2.5.46 3.44 1.35l2.58-2.58C13.46.9 11.42 0 9 0A9 9 0 0 0 .96 4.94l3.02 2.34C4.68 5.16 6.66 3.58 9 3.58Z" />
    </svg>
  );
}

interface GoogleAuthButtonProps {
  /** Copy differs between the sign-in and sign-up pages; the call is identical. */
  label?: string;
  onError?: (message: string) => void;
  /** Runs just before Google opens, e.g. to remember the account type being signed up for. */
  onStart?: () => void;
}

/**
 * "Continue with Google": one click instead of a password, for donors and organisation
 * staff alike. Firebase opens Google's account chooser in a popup (or a redirect where
 * popups are blocked); the Veritas API makes the account on the first sign-in, or joins it
 * to the account that already has that email. Not shown without the Firebase web config.
 */
export function GoogleAuthButton({ label = "Continue with Google", onError, onStart }: GoogleAuthButtonProps) {
  const { signInWithGoogle, googleAvailable } = useAuth();
  const reduceMotion = useReducedMotion();
  const [pending, setPending] = useState(false);
  if (!googleAvailable) return null;

  const handleClick = async () => {
    setPending(true);
    onStart?.();
    const { error } = await signInWithGoogle();
    if (error) {
      setPending(false);
      onError?.(error.message);
    }
    // On success the auth state changes and the page moves on by itself.
  };

  const off = pending;
  return (
    <motion.button
      type="button"
      onClick={handleClick}
      disabled={off}
      whileHover={reduceMotion || off ? undefined : { y: -2 }}
      whileTap={reduceMotion || off ? undefined : { scale: 0.985 }}
      transition={{ type: "spring", stiffness: 400, damping: 25 }}
      className="group relative flex h-[50px] w-full items-center justify-center gap-3 rounded-xl border border-ink/[0.12] bg-canvas px-6 text-[15px] text-ink transition-colors hover:border-ink/25 hover:bg-pg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-60"
    >
      {pending ? <Loader2 className="h-5 w-5 animate-spin" /> : <GoogleMark className="h-5 w-5" />}
      <span>{pending ? "Waiting for Google…" : label}</span>
    </motion.button>
  );
}
