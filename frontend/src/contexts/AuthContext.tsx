import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import {
  getRedirectResult,
  signInWithPopup,
  signInWithRedirect,
  signOut as firebaseSignOut,
  type User as FirebaseUser,
} from "firebase/auth";
import { auth, googleAvailable, googleProvider } from "@/lib/firebase";
import {
  ApiError,
  SESSION_EVENT,
  SESSION_KEY,
  changePassword as changePasswordApi,
  confirmPasswordReset,
  exchangeFirebaseToken,
  getMe,
  getSession,
  logInDemo,
  logInWithPassword,
  logOutApi,
  requestPasswordReset,
  setSession,
  signUpWithPassword,
  updateMe,
  type Me,
  type Session,
  type VeritasUser,
} from "@/lib/api";

/**
 * Who is signed in, and how far they are connected.
 *
 * A Veritas account signs in with an email and a password, which the Veritas API checks
 * itself, or with Google, through Firebase. Either way the API answers with its own
 * session, and that session is the sign-in: lib/api.ts keeps it across reloads and tabs
 * until it expires or the person signs out. Firebase only vouches for a Google account,
 * once per sign-in, and is signed out of straight after.
 *
 * With a session the app loads /v1/me, the account's charity memberships and officer
 * record. If the API cannot be reached the person stays signed in with what this browser
 * knows, and the console says it is showing sample data; if the API stops accepting the
 * session, they are signed out.
 *
 * Whether someone came to donate or to raise money for an organisation is their own
 * choice, made at sign-up (or on first sign-in with Google). Until the API records it,
 * it is kept per account in this browser; a charity membership on the API always wins.
 */
export type AccountType = "donor" | "organisation";

export interface AppUser {
  id: string;
  email: string;
  displayName: string | null;
  firstName: string | null;
  /** Signs in with a password, which Settings can change. */
  hasPassword: boolean;
  /** Signs in with Google. */
  hasGoogle: boolean;
}

export type ApiState =
  | { status: "idle"; me: null }
  | { status: "connecting"; me: null }
  | { status: "connected"; me: Me }
  /** The API answered and refused. `message` says why. */
  | { status: "refused"; me: null; message: string; code: string }
  /** The API could not be reached; the app runs on sample data. */
  | { status: "offline"; me: null; message: string };

type Result = { error: { message: string; code?: string } | null };

interface AuthContextType {
  user: AppUser | null;
  /** True only while a Google sign-in that went through a full-page redirect is finished. */
  loading: boolean;
  /** "Continue with Google" can be offered: the Firebase web config is there. */
  googleAvailable: boolean;
  /** Why the last Google sign-in by redirect did not work, to show on the sign-in page. */
  googleError: string | null;
  accountType: AccountType | null;
  setAccountType: (t: AccountType) => void;
  api: ApiState;
  /** Load /v1/me again, e.g. once the API can be reached. */
  connectApi: () => Promise<void>;
  signIn: (email: string, password: string) => Promise<Result>;
  /** Sign in to the shared demo donor or demo organisation, with no email or password. */
  signInDemo: (kind: AccountType) => Promise<Result>;
  signUp: (email: string, password: string, displayName?: string) => Promise<Result>;
  signInWithGoogle: () => Promise<Result>;
  signOut: () => Promise<void>;
  /** Ask for an email with a link to set a new password. */
  sendPasswordReset: (email: string) => Promise<Result>;
  /** Set a new password with the token from that link. Signs in. */
  confirmReset: (token: string, password: string) => Promise<Result>;
  changePassword: (current: string, next: string) => Promise<Result>;
  /** Change the name shown on the account. */
  updateName: (name: string) => Promise<Result>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

function toAppUser(u: VeritasUser): AppUser {
  const displayName = u.display_name?.trim() || null;
  return {
    id: u.id,
    email: u.email ?? "",
    displayName,
    firstName: displayName ? displayName.split(/\s+/)[0] : null,
    hasPassword: Boolean(u.has_password),
    hasGoogle: Boolean(u.has_google),
  };
}

const codeOf = (err: unknown) => (err as { code?: string } | null)?.code;

/** The API's errors already say what to do; Firebase's codes need saying in words. */
function describe(err: unknown): string {
  if (err instanceof ApiError) {
    return err.offline || err.code === "not_the_api" || err.code === "timeout"
      ? "Veritas cannot be reached right now. Check your connection and try again."
      : err.message;
  }
  switch (codeOf(err)) {
    case "auth/popup-closed-by-user":
    case "auth/cancelled-popup-request":
      return "Google sign-in was closed before it finished.";
    case "auth/network-request-failed":
      return "No connection. Check your internet and try again.";
    case "auth/too-many-requests":
      return "Too many attempts. Wait a few minutes and try again.";
    case "auth/user-disabled":
      return "This Google account has been disabled.";
    case "auth/unauthorized-domain":
      return "Google sign-in is not allowed from this address yet.";
    case "auth/operation-not-allowed":
      return "Google sign-in is not turned on for Veritas yet.";
    default:
      return (err as { message?: string } | null)?.message || "Something went wrong. Please try again.";
  }
}

const done: Result = { error: null };
const fail = (err: unknown): Result => ({ error: { message: describe(err), code: codeOf(err) } });

const typeKey = (uid: string) => `veritas.accountType.${uid}`;
const PENDING_TYPE = "veritas.pendingAccountType";
/** Set just before a Google sign-in leaves the page by redirect, so the return is expected. */
const GOOGLE_REDIRECT = "veritas.googleRedirect";

/**
 * The account type chosen on the sign-up page, before the account exists. It waits here
 * and is applied to whichever account signs in next in this tab.
 */
export function rememberAccountType(t: AccountType) {
  try {
    sessionStorage.setItem(PENDING_TYPE, t);
  } catch {
    /* storage blocked: onboarding will ask */
  }
}

function readType(uid: string): AccountType | null {
  try {
    const pending = sessionStorage.getItem(PENDING_TYPE);
    if ((pending === "donor" || pending === "organisation") && !localStorage.getItem(typeKey(uid))) {
      localStorage.setItem(typeKey(uid), pending);
    }
    sessionStorage.removeItem(PENDING_TYPE);
    const v = localStorage.getItem(typeKey(uid));
    return v === "donor" || v === "organisation" ? v : null;
  } catch {
    return null;
  }
}

function flag(on: boolean | null): boolean {
  try {
    if (on === true) sessionStorage.setItem(GOOGLE_REDIRECT, "1");
    if (on === false) sessionStorage.removeItem(GOOGLE_REDIRECT);
    return sessionStorage.getItem(GOOGLE_REDIRECT) === "1";
  } catch {
    return false;
  }
}

/** The Google account is proven: trade its token for a Veritas session, then let Firebase go. */
async function finishGoogle(u: FirebaseUser) {
  try {
    await exchangeFirebaseToken(await u.getIdToken());
  } finally {
    if (auth) await firebaseSignOut(auth).catch(() => undefined);
  }
}

/** Keep the stored account up to date with what the API says about it. */
function remember(u: VeritasUser) {
  const s = getSession();
  if (s && s.user.id === u.id && JSON.stringify(s.user) !== JSON.stringify(u)) setSession({ ...s, user: u });
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [session, setSessionState] = useState<Session | null>(() => getSession());
  const [loading, setLoading] = useState(() => Boolean(auth) && flag(null));
  const [googleError, setGoogleError] = useState<string | null>(null);
  const [storedType, setStoredType] = useState<AccountType | null>(() => (session ? readType(session.user.id) : null));
  const [api, setApi] = useState<ApiState>({ status: "idle", me: null });
  const connecting = useRef<Promise<void> | null>(null);
  const user = useMemo(() => (session ? toAppUser(session.user) : null), [session]);
  const userId = session?.user.id ?? null;

  // Follow the stored session: this tab signing in or out, other tabs doing it, and the API
  // ending it (lib/api.ts drops a session the API answers 401 to).
  useEffect(() => {
    const sync = () => setSessionState(getSession());
    const onStorage = (e: StorageEvent) => {
      if (e.key === SESSION_KEY || e.key === null) sync();
    };
    window.addEventListener(SESSION_EVENT, sync);
    window.addEventListener("storage", onStorage);
    return () => {
      window.removeEventListener(SESSION_EVENT, sync);
      window.removeEventListener("storage", onStorage);
    };
  }, []);

  // A Google sign-in that had to leave the page by redirect comes back here.
  useEffect(() => {
    if (!auth || !flag(null)) return;
    flag(false);
    getRedirectResult(auth)
      .then((cred) => (cred ? finishGoogle(cred.user) : undefined))
      .catch((err) => setGoogleError(describe(err)))
      .finally(() => setLoading(false));
  }, []);

  // A different account (or none): its own type, and its own connection to the API.
  useEffect(() => {
    setStoredType(userId ? readType(userId) : null);
    setApi({ status: "idle", me: null });
  }, [userId]);

  const connectApi = useCallback(async () => {
    if (!getSession()) return;
    if (connecting.current) return connecting.current;
    const run = (async () => {
      setApi({ status: "connecting", me: null });
      try {
        const me = await getMe();
        setApi({ status: "connected", me });
        remember(me.user);
      } catch (err) {
        if (!getSession()) {
          // The API ended the session: signed out, and the session listener has seen it.
          setApi({ status: "idle", me: null });
        } else if (err instanceof ApiError && !err.offline && err.code !== "not_the_api") {
          setApi({ status: "refused", me: null, message: err.message, code: err.code });
        } else {
          setApi({ status: "offline", me: null, message: err instanceof Error ? err.message : "The Veritas API could not be reached." });
        }
      } finally {
        connecting.current = null;
      }
    })();
    connecting.current = run;
    return run;
  }, []);

  useEffect(() => {
    if (session && api.status === "idle") void connectApi();
  }, [session, api.status, connectApi]);

  // A donor unless they chose otherwise (at sign-up, or in Settings), or the API knows
  // their organisation: signing in on a new device goes straight to the dashboard.
  const accountType: AccountType | null = useMemo(() => {
    if (!userId) return null;
    if (api.status === "connected" && api.me.memberships.length > 0) return "organisation";
    return storedType ?? "donor";
  }, [userId, api, storedType]);

  const setAccountType = useCallback(
    (t: AccountType) => {
      if (!user) return;
      try {
        localStorage.setItem(typeKey(user.id), t);
      } catch {
        /* kept in memory for this visit */
      }
      setStoredType(t);
    },
    [user]
  );

  const value: AuthContextType = {
    user,
    loading,
    googleAvailable,
    googleError,
    accountType,
    setAccountType,
    api,
    connectApi,

    async signIn(email, password) {
      try {
        await logInWithPassword(email.trim(), password);
        return done;
      } catch (err) {
        return fail(err);
      }
    },

    async signInDemo(kind) {
      try {
        rememberAccountType(kind);
        await logInDemo(kind);
        return done;
      } catch (err) {
        if (err instanceof ApiError && err.code === "demo_off") {
          return { error: { message: "The demo accounts are not switched on for this server.", code: err.code } };
        }
        return fail(err);
      }
    },

    async signUp(email, password, displayName) {
      try {
        await signUpWithPassword(email.trim(), password, displayName?.trim() || null);
        return done;
      } catch (err) {
        return fail(err);
      }
    },

    /**
     * A popup keeps the person on the page. Browsers that block popups (and most in-app
     * webviews) fall back to a full redirect, which the effect above finishes on return.
     */
    async signInWithGoogle() {
      if (!auth) return { error: { message: "Google sign-in is not available here." } };
      setGoogleError(null);
      try {
        const cred = await signInWithPopup(auth, googleProvider);
        await finishGoogle(cred.user);
        return done;
      } catch (err) {
        const code = codeOf(err);
        if (code === "auth/popup-blocked" || code === "auth/operation-not-supported-in-this-environment") {
          try {
            flag(true);
            await signInWithRedirect(auth, googleProvider);
            return done;
          } catch (redirectErr) {
            flag(false);
            return fail(redirectErr);
          }
        }
        return fail(err);
      }
    },

    async signOut() {
      await logOutApi();
      if (auth?.currentUser) await firebaseSignOut(auth).catch(() => undefined);
    },

    async sendPasswordReset(email) {
      try {
        await requestPasswordReset(email.trim());
        return done;
      } catch (err) {
        return fail(err);
      }
    },

    async confirmReset(token, password) {
      try {
        await confirmPasswordReset(token, password);
        return done;
      } catch (err) {
        return fail(err);
      }
    },

    async changePassword(current, next) {
      try {
        await changePasswordApi(current, next);
        return done;
      } catch (err) {
        return fail(err);
      }
    },

    async updateName(name) {
      try {
        const me = await updateMe(name.trim() || null);
        setApi({ status: "connected", me });
        remember(me.user);
        return done;
      } catch (err) {
        return fail(err);
      }
    },
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) throw new Error("useAuth must be used inside an AuthProvider");
  return context;
}
