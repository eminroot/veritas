import type { CharityIn } from "./api";

/**
 * An organisation's application, as this browser knows it.
 *
 * When the Veritas API is reachable the application lives there (POST /v1/charities) and
 * this only remembers its id. When it is not, the details are kept here so nothing typed
 * is lost, marked as not sent; documents cannot be kept in the browser, so they are
 * attached again when the application is sent.
 */
export type OrgDraft = {
  details: CharityIn;
  /** Set once the API accepted the application. */
  charityId?: string;
  status: "saved" | "submitted";
  /** Documents attached when it was sent, by kind. */
  documents: string[];
  savedAt: string;
};

const key = (uid: string) => `veritas.org.${uid}`;

export function readOrgDraft(uid: string | undefined | null): OrgDraft | null {
  if (!uid) return null;
  try {
    const raw = localStorage.getItem(key(uid));
    return raw ? (JSON.parse(raw) as OrgDraft) : null;
  } catch {
    return null;
  }
}

export function saveOrgDraft(uid: string, draft: OrgDraft) {
  try {
    localStorage.setItem(key(uid), JSON.stringify(draft));
  } catch {
    /* storage blocked: the form keeps it for this visit */
  }
}

/* ---------------------------------------------------------------- validation */

export const isVoen = (v: string) => /^\d{10}$/.test(v.replace(/\s+/g, ""));

/** The ways people write Azerbaijani numbers: +994 50 123 45 67, 050-123-45-67, (012) 345 67 89. */
export function normalizePhone(v: string): string | null {
  const digits = v.replace(/[\s().-]/g, "");
  let rest: string | null = null;
  if (/^\+994\d{9}$/.test(digits)) rest = digits.slice(4);
  else if (/^00994\d{9}$/.test(digits)) rest = digits.slice(5);
  else if (/^994\d{9}$/.test(digits)) rest = digits.slice(3);
  else if (/^0\d{9}$/.test(digits)) rest = digits.slice(1);
  return rest ? `+994 ${rest.slice(0, 2)} ${rest.slice(2, 5)} ${rest.slice(5, 7)} ${rest.slice(7)}` : null;
}

export const isEmail = (v: string) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v.trim());

export const isWebsite = (v: string) => !v.trim() || /^https?:\/\/\S+\.\S+$/.test(v.trim());
