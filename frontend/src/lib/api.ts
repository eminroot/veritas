/**
 * The Veritas API (backend/, FastAPI), as the web app uses it.
 *
 * The API signs people in itself: an email and a password (POST /v1/auth/signup and
 * /v1/auth/login), or Google, where Firebase signs the person in to Google and the app
 * trades the Firebase ID token at POST /v1/auth/firebase. Either way the answer is a Veritas
 * session, whose bearer token every API call carries. Logging out ends it.
 *
 * Errors come back in one shape from every endpoint,
 *   {"error": {"code": "snake_case", "message": "One sentence a person can read.", "details": []}},
 * so `ApiError` carries the code to switch on and a message that can be shown as it is.
 */

/**
 * Where the API lives. Empty means the app's own origin: in development the Vite dev
 * server proxies /v1 and /health to the backend (vite.config.ts), and in production the
 * web server in front of both does the same (nginx.conf). Set VITE_API_URL only when the
 * API is on another origin, and allow that origin in the backend's CORS setting.
 */
function resolveApiBase(): string {
  const raw = String(import.meta.env.VITE_API_URL ?? "").trim();
  // A whole "KEY=value" line pasted into a hosting dashboard's value box is an easy mistake.
  const cleaned = raw.replace(/^\s*VITE_API_URL\s*=\s*/i, "").trim().replace(/\/+$/, "");
  if (cleaned && !/^https?:\/\//i.test(cleaned)) {
    console.error(`[api] VITE_API_URL must be an absolute URL such as https://api.example.az, not ${JSON.stringify(raw)}.`);
    return "";
  }
  return cleaned;
}

export const API_BASE = resolveApiBase();

const REQUEST_TIMEOUT_MS = 20_000;

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code: string,
    readonly details: unknown[] = []
  ) {
    super(message);
    this.name = "ApiError";
  }

  /** The API could not be reached at all, as opposed to answering with an error. A proxy's
   *  own error page (502 from nginx, 500 from the dev server) counts as not reached. */
  get offline() {
    return this.status === 0 || this.code === "unreachable";
  }
}

/* ------------------------------------------------------------------ the session */

export type VeritasUser = {
  id: string;
  phone: string | null;
  email: string | null;
  has_password: boolean;
  has_google: boolean;
  display_name: string | null;
  is_admin?: boolean;
};

/** The sign-in: the API's bearer token, and the account it was given for. */
export type Session = { token: string; expiresAt: string; user: VeritasUser };

export const SESSION_KEY = "veritas.session";
/** Fired on window whenever this tab signs in or out, so the app can follow. */
export const SESSION_EVENT = "veritas:session";

// Where storage is blocked (some private modes), the session lives as long as the page.
let memorySession: string | null = null;

function readStored(): string | null {
  try {
    return localStorage.getItem(SESSION_KEY);
  } catch {
    return memorySession;
  }
}

function writeStored(value: string | null) {
  memorySession = value;
  try {
    if (value) localStorage.setItem(SESSION_KEY, value);
    else localStorage.removeItem(SESSION_KEY);
  } catch {
    /* kept in memory instead */
  }
}

/**
 * The session lives in localStorage, so it survives reloads and new tabs until it expires
 * or the person signs out; a tab signing in or out changes every tab (the storage event).
 */
export function getSession(): Session | null {
  try {
    const raw = readStored();
    if (!raw) return null;
    const s = JSON.parse(raw) as Session;
    if (!s?.token || !s.user?.id || !(Date.parse(s.expiresAt) > Date.now() + 30_000)) {
      writeStored(null);
      return null;
    }
    return s;
  } catch {
    return null;
  }
}

export function setSession(s: Session | null) {
  writeStored(s ? JSON.stringify(s) : null);
  window.dispatchEvent(new Event(SESSION_EVENT));
}

/* ------------------------------------------------------------------ requests */

type FetchOptions = Omit<RequestInit, "body"> & {
  /** JSON-encoded unless it is FormData. */
  body?: unknown;
  /** Send the Veritas session's bearer token. Default true. */
  auth?: boolean;
};

export async function apiFetch<T = unknown>(path: string, options: FetchOptions = {}): Promise<T> {
  const { body, auth = true, headers: given, ...init } = options;
  const headers = new Headers(given);
  let payload: BodyInit | undefined;
  if (body instanceof FormData) payload = body;
  else if (body !== undefined) {
    payload = JSON.stringify(body);
    headers.set("Content-Type", "application/json");
  }
  const session = auth ? getSession() : null;
  if (session) headers.set("Authorization", `Bearer ${session.token}`);

  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, { ...init, headers, body: payload, signal: controller.signal });
  } catch (err) {
    const timedOut = (err as { name?: string } | null)?.name === "AbortError";
    throw new ApiError(
      timedOut ? "The Veritas API did not answer in time." : "The Veritas API could not be reached.",
      0,
      timedOut ? "timeout" : "offline"
    );
  } finally {
    window.clearTimeout(timer);
  }

  if (res.status === 204) return undefined as T;
  const text = await res.text();
  let data: unknown = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    // An HTML page where JSON was expected: a proxy or the SPA fallback answered instead.
    throw new ApiError("The Veritas API is not answering at this address.", res.status || 0, "not_the_api");
  }
  if (!res.ok) {
    const e = (data as { error?: { message?: string; code?: string; details?: unknown[] } } | null)?.error;
    // The API answers every error in its own shape; anything else came from whatever stands
    // in front of it while it is down.
    if (!e) throw new ApiError("The Veritas API could not be reached.", res.status, "unreachable");
    // The token this call carried does not work any more: the session has ended.
    if (res.status === 401 && session && getSession()?.token === session.token) setSession(null);
    throw new ApiError(e.message || `Request failed (${res.status}).`, res.status, e.code || "error", e.details || []);
  }
  return data as T;
}

/* ------------------------------------------------------------------ accounts */

export type Membership = { charity_id: string; charity_name: string; charity_status: string; role: string };

export type Me = {
  user: VeritasUser;
  is_admin: boolean;
  memberships: Membership[];
  officer: unknown | null;
};

type TokenOut = { access_token: string; token_type: "bearer"; expires_at: string; user: VeritasUser };

/** Every way of signing in answers with a token: keep it, and the account it is for. */
async function signInWith(path: string, body: unknown): Promise<Session> {
  const out = await apiFetch<TokenOut>(path, { method: "POST", body, auth: false });
  const session = { token: out.access_token, expiresAt: out.expires_at, user: out.user };
  setSession(session);
  return session;
}

export const signUpWithPassword = (email: string, password: string, displayName: string | null) =>
  signInWith("/v1/auth/signup", { email, password, display_name: displayName });

export const logInWithPassword = (email: string, password: string) => signInWith("/v1/auth/login", { email, password });

/** Sign in to the shared demo donor or demo organisation, with no password. Only where the
 *  API runs with VERITAS_DEMO_LOGIN on. */
export const logInDemo = (kind: "donor" | "organisation") => signInWith("/v1/auth/demo", { kind });

/** Trade a Firebase ID token from a Google sign-in. The first time links or makes the account. */
export const exchangeFirebaseToken = (idToken: string) => signInWith("/v1/auth/firebase", { id_token: idToken });

/** The API emails a link to set a new password, if an account has this email; it says the same either way. */
export const requestPasswordReset = (email: string) =>
  apiFetch("/v1/auth/password-reset", { method: "POST", body: { email }, auth: false });

/** Set a new password with the emailed link's token. Signs in, and ends every other session. */
export const confirmPasswordReset = (token: string, password: string) =>
  signInWith("/v1/auth/password-reset/confirm", { token, password });

export const changePassword = (currentPassword: string, newPassword: string) =>
  apiFetch("/v1/me/password", { method: "POST", body: { current_password: currentPassword, new_password: newPassword } });

export const getMe = () => apiFetch<Me>("/v1/me");

export const updateMe = (displayName: string | null) => apiFetch<Me>("/v1/me", { method: "PATCH", body: { display_name: displayName } });

export async function logOutApi() {
  if (!getSession()) return;
  try {
    await apiFetch("/v1/auth/logout", { method: "POST" });
  } catch {
    /* the session ends locally either way */
  } finally {
    setSession(null);
  }
}

/* ------------------------------------------------------------------ organisations */

/** What the backend needs to start a charity's registration (POST /v1/charities). */
export type CharityIn = {
  legal_name: string;
  voen: string;
  legal_form: string;
  legal_address: string;
  director_name: string;
  contact_email: string;
  contact_phone: string;
  website?: string | null;
};

export type CharityOut = CharityIn & {
  id: string;
  status: "draft" | "submitted" | "verified" | "rejected" | "suspended" | string;
  submitted_at: string | null;
  verified_at: string | null;
  review_notes: string | null;
  documents?: { id: string; kind: string; filename: string }[];
};

/** Kinds of document the backend accepts for an organisation's verification. */
export const DOCUMENT_KINDS = [
  { kind: "registration", label: "State registration certificate" },
  { kind: "charter", label: "Charter" },
  { kind: "tax_registration", label: "Tax registration (VÖEN) certificate" },
  { kind: "director_id", label: "Director's ID card" },
  { kind: "bank_letter", label: "Bank letter" },
  { kind: "other", label: "Other" },
] as const;

export const createCharity = (body: CharityIn) => apiFetch<CharityOut>("/v1/charities", { method: "POST", body });

export const getCharity = (id: string) => apiFetch<CharityOut>(`/v1/charities/${id}`);

export function uploadCharityDocument(id: string, kind: string, file: File) {
  const form = new FormData();
  form.set("kind", kind);
  form.set("file", file);
  return apiFetch(`/v1/charities/${id}/documents`, { method: "POST", body: form });
}

export const submitCharity = (id: string) => apiFetch<CharityOut>(`/v1/charities/${id}/submit`, { method: "POST" });
