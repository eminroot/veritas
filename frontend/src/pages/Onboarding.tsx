import React, { useEffect, useMemo, useState } from "react";
import { Navigate, useNavigate, useSearchParams } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import { Building2, FileUp, Globe, HandHeart, Hash, Mail, MapPin, Phone, User, X } from "lucide-react";
import AuthShell from "@/components/auth/AuthShell";
import { Btn } from "@/components/lp/primitives";
import { useAuth, type AccountType } from "@/contexts/AuthContext";
import { ApiError, DOCUMENT_KINDS, createCharity, submitCharity, uploadCharityDocument, type CharityIn } from "@/lib/api";
import { isEmail, isVoen, isWebsite, normalizePhone, readOrgDraft, saveOrgDraft } from "@/lib/orgDraft";
import { SpinIcon } from "./Login";

/**
 * The step between signing up and the console.
 *
 * Everyone says whether they came to donate or to raise money for an organisation (Google
 * sign-ups have not been asked yet). Organisations then apply: legal details, the
 * director and a contact, and the documents Veritas verifies. With the API reachable the
 * application is created, its documents uploaded and it is submitted for review
 * (POST /v1/charities, /documents, /submit). Without it, the details are saved in this
 * browser and the console says the application still has to be sent.
 */
const LEGAL_FORMS = ["Public union", "Foundation", "Charity", "Other non-profit"];
const REQUIRED_DOCS = ["registration", "charter", "tax_registration", "director_id"];
const MAX_FILE = 20 * 1024 * 1024;
const STEPS = ["Organisation", "People", "Documents", "Send"];

type Form = {
  legal_name: string;
  voen: string;
  legal_form: string;
  legal_address: string;
  website: string;
  director_name: string;
  contact_email: string;
  contact_phone: string;
};

export default function Onboarding() {
  const { user, loading, accountType, setAccountType, api, connectApi } = useAuth();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const draft = readOrgDraft(user?.id);
  // An application saved while the API was out of reach can be reopened and sent.
  const resume = params.get("resume") === "1" && draft?.status === "saved";
  const [choice, setChoice] = useState<AccountType | null>(accountType);
  const [step, setStep] = useState(0);
  const [form, setForm] = useState<Form>(() => ({
    legal_name: draft?.details.legal_name ?? "",
    voen: draft?.details.voen ?? "",
    legal_form: draft?.details.legal_form ?? LEGAL_FORMS[0],
    legal_address: draft?.details.legal_address ?? "",
    website: draft?.details.website ?? "",
    director_name: draft?.details.director_name ?? "",
    contact_email: draft?.details.contact_email ?? user?.email ?? "",
    contact_phone: draft?.details.contact_phone ?? "",
  }));
  const [files, setFiles] = useState<Record<string, File>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => setChoice((c) => c ?? accountType), [accountType]);
  useEffect(() => {
    if (user && !form.contact_email) setForm((f) => ({ ...f, contact_email: user.email }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user]);

  const missingDocs = useMemo(() => REQUIRED_DOCS.filter((k) => !files[k]), [files]);

  if (loading) return null;
  if (!user) return <Navigate to="/login" replace />;

  const hasOrg = (api.status === "connected" && api.me.memberships.length > 0) || Boolean(draft);
  if (accountType === "donor" || (accountType === "organisation" && hasOrg && !resume)) {
    return <Navigate to={accountType === "organisation" ? "/organisation" : "/dashboard"} replace />;
  }

  const set = (k: keyof Form) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    setForm((f) => ({ ...f, [k]: e.target.value }));
    setErrors((x) => ({ ...x, [k]: "" }));
  };

  /* ---------------- step 0: donor or organisation ---------------- */
  if (!accountType) {
    return (
      <AuthShell solo title="How will you use Veritas?" subtitle="You can donate either way; organisations can also raise money once verified.">
        <div className="v-types v-types--big" role="radiogroup" aria-label="Account type">
          {[
            { key: "donor" as const, icon: HandHeart, title: "I want to donate", sub: "Give to verified projects and follow every manat." },
            { key: "organisation" as const, icon: Building2, title: "I represent an organisation", sub: "A registered charity, foundation or public union raising money for its projects." },
          ].map((t) => (
            <button key={t.key} type="button" role="radio" aria-checked={choice === t.key} className={"v-type" + (choice === t.key ? " on" : "")} onClick={() => setChoice(t.key)}>
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
        <Btn type="button" size="wide" label="Continue" disabled={!choice} onClick={() => choice && setAccountType(choice)} />
      </AuthShell>
    );
  }

  /* ---------------- the organisation's application ---------------- */
  const validateStep = (s: number) => {
    const e: Record<string, string> = {};
    if (s === 0) {
      if (!form.legal_name.trim()) e.legal_name = "Enter the organisation's registered name";
      if (!isVoen(form.voen)) e.voen = "A VÖEN is 10 digits";
      if (!form.legal_address.trim()) e.legal_address = "Enter the registered address";
      if (!isWebsite(form.website)) e.website = "Start with https://";
    }
    if (s === 1) {
      if (!form.director_name.trim()) e.director_name = "Enter the director's full name";
      if (!isEmail(form.contact_email)) e.contact_email = "Enter a valid email address";
      if (!normalizePhone(form.contact_phone)) e.contact_phone = "An Azerbaijani number, like +994 50 123 45 67";
    }
    if (s === 2 && missingDocs.length) e.docs = "Attach each required document";
    setErrors(e);
    return Object.keys(e).length === 0;
  };

  const next = () => validateStep(step) && setStep((x) => Math.min(STEPS.length - 1, x + 1));

  const details = (): CharityIn => ({
    legal_name: form.legal_name.trim(),
    voen: form.voen.replace(/\s+/g, ""),
    legal_form: form.legal_form,
    legal_address: form.legal_address.trim(),
    director_name: form.director_name.trim(),
    contact_email: form.contact_email.trim(),
    contact_phone: normalizePhone(form.contact_phone) ?? form.contact_phone,
    website: form.website.trim() || null,
  });

  const send = async () => {
    setError(null);
    setBusy(true);
    try {
      if (api.status !== "connected") await connectApi();
      const charity = await createCharity(details());
      for (const [kind, file] of Object.entries(files)) await uploadCharityDocument(charity.id, kind, file);
      await submitCharity(charity.id);
      saveOrgDraft(user.id, { details: details(), charityId: charity.id, status: "submitted", documents: Object.keys(files), savedAt: new Date().toISOString() });
      await connectApi();
      navigate("/organisation", { replace: true });
    } catch (err) {
      if (err instanceof ApiError && !err.offline && err.code !== "not_the_api") {
        setError(err.message);
      } else {
        // The API is out of reach: keep everything typed, and say what is left to do.
        saveOrgDraft(user.id, { details: details(), status: "saved", documents: [], savedAt: new Date().toISOString() });
        navigate("/organisation", { replace: true });
      }
    } finally {
      setBusy(false);
    }
  };

  const wrap = (k: string) => "field__wrap" + (errors[k] ? " is-bad" : "");
  const err = (k: string) => (errors[k] ? <span className="field__err">{errors[k]}</span> : null);

  return (
    <AuthShell
      title="Register your organisation"
      subtitle="Veritas checks every organisation before it can raise money. This takes about five minutes."
      pitch="Verified once, trusted by every donor who opens your projects."
    >
      <div className="lp-steps" aria-label={`Step ${step + 1} of ${STEPS.length}`}>
        {STEPS.map((s, i) => (
          <React.Fragment key={s}>
            <span className={"lp-steps__item" + (i === step ? " is-active" : i < step ? " is-done" : "")}>
              <b>{i + 1}</b>
              {s}
            </span>
            {i < STEPS.length - 1 ? <span className="lp-steps__bar" /> : null}
          </React.Fragment>
        ))}
      </div>

      <AnimatePresence mode="wait" initial={false}>
        <motion.div key={step} className="auth-form" initial={{ opacity: 0, x: 18 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -18 }} transition={{ duration: 0.22 }}>
          {step === 0 ? (
            <>
              <label className="field">
                <span className="field__label">Registered name</span>
                <span className={wrap("legal_name")}>
                  <Building2 strokeWidth={1.6} />
                  <input value={form.legal_name} onChange={set("legal_name")} placeholder="Ümid Körpüsü İctimai Birliyi" />
                </span>
                {err("legal_name")}
              </label>
              <div className="field-row">
                <label className="field">
                  <span className="field__label">VÖEN</span>
                  <span className={wrap("voen")}>
                    <Hash strokeWidth={1.6} />
                    <input inputMode="numeric" value={form.voen} onChange={set("voen")} placeholder="10 digits" />
                  </span>
                  {err("voen")}
                </label>
                <label className="field">
                  <span className="field__label">Legal form</span>
                  <span className="field__wrap">
                    <select value={form.legal_form} onChange={set("legal_form")}>
                      {LEGAL_FORMS.map((f) => (
                        <option key={f}>{f}</option>
                      ))}
                    </select>
                  </span>
                </label>
              </div>
              <label className="field">
                <span className="field__label">Registered address</span>
                <span className={wrap("legal_address")}>
                  <MapPin strokeWidth={1.6} />
                  <input value={form.legal_address} onChange={set("legal_address")} placeholder="Street, building, city" />
                </span>
                {err("legal_address")}
              </label>
              <label className="field">
                <span className="field__label">Website (optional)</span>
                <span className={wrap("website")}>
                  <Globe strokeWidth={1.6} />
                  <input value={form.website} onChange={set("website")} placeholder="https://" />
                </span>
                {err("website")}
              </label>
            </>
          ) : step === 1 ? (
            <>
              <label className="field">
                <span className="field__label">Director's full name</span>
                <span className={wrap("director_name")}>
                  <User strokeWidth={1.6} />
                  <input value={form.director_name} onChange={set("director_name")} placeholder="As on their ID card" />
                </span>
                {err("director_name")}
              </label>
              <div className="field-row">
                <label className="field">
                  <span className="field__label">Contact email</span>
                  <span className={wrap("contact_email")}>
                    <Mail strokeWidth={1.6} />
                    <input type="email" value={form.contact_email} onChange={set("contact_email")} />
                  </span>
                  {err("contact_email")}
                </label>
                <label className="field">
                  <span className="field__label">Contact phone</span>
                  <span className={wrap("contact_phone")}>
                    <Phone strokeWidth={1.6} />
                    <input type="tel" value={form.contact_phone} onChange={set("contact_phone")} placeholder="+994 50 123 45 67" />
                  </span>
                  {err("contact_phone")}
                </label>
              </div>
              <p className="field__hint">Veritas contacts this person about the review. The director's name must match the documents.</p>
            </>
          ) : step === 2 ? (
            <>
              <p className="field__hint">PDF, JPEG or PNG, up to 20 MB each. Only Veritas's reviewers see them.</p>
              <div className="v-docs">
                {DOCUMENT_KINDS.filter((d) => d.kind !== "other").map((d) => {
                  const f = files[d.kind];
                  const required = REQUIRED_DOCS.includes(d.kind);
                  return (
                    <div className={"v-doc" + (f ? " is-in" : "")} key={d.kind}>
                      <FileUp aria-hidden="true" />
                      <span className="v-doc__say">
                        <b>
                          {d.label}
                          {required ? "" : " (optional)"}
                        </b>
                        <span>{f ? `${f.name} · ${(f.size / 1024 / 1024).toFixed(1)} MB` : "Not attached"}</span>
                      </span>
                      {f ? (
                        <button
                          type="button"
                          className="v-doc__x"
                          aria-label={`Remove ${d.label}`}
                          onClick={() =>
                            setFiles((x) => {
                              const n = { ...x };
                              delete n[d.kind];
                              return n;
                            })
                          }
                        >
                          <X />
                        </button>
                      ) : (
                        <label className="v-doc__pick">
                          Attach
                          <input
                            type="file"
                            accept="application/pdf,image/jpeg,image/png"
                            onChange={(e) => {
                              const file = e.target.files?.[0];
                              e.target.value = "";
                              if (!file) return;
                              if (file.size > MAX_FILE) return setErrors((x) => ({ ...x, docs: `${file.name} is larger than 20 MB` }));
                              setFiles((x) => ({ ...x, [d.kind]: file }));
                              setErrors((x) => ({ ...x, docs: "" }));
                            }}
                          />
                        </label>
                      )}
                    </div>
                  );
                })}
              </div>
              {err("docs")}
            </>
          ) : (
            <>
              <dl className="v-review">
                <div>
                  <dt>Organisation</dt>
                  <dd>
                    {form.legal_name} · {form.legal_form}
                  </dd>
                </div>
                <div>
                  <dt>VÖEN</dt>
                  <dd>{form.voen}</dd>
                </div>
                <div>
                  <dt>Address</dt>
                  <dd>{form.legal_address}</dd>
                </div>
                <div>
                  <dt>Director</dt>
                  <dd>{form.director_name}</dd>
                </div>
                <div>
                  <dt>Contact</dt>
                  <dd>
                    {form.contact_email} · {normalizePhone(form.contact_phone)}
                  </dd>
                </div>
                <div>
                  <dt>Documents</dt>
                  <dd>{Object.keys(files).length} attached</dd>
                </div>
              </dl>
              <p className="field__hint">
                By sending, you confirm these details are true and that you may act for the organisation. Veritas reviews the
                application and tells you by email.
              </p>
              {error ? (
                <div className="lp-alert lp-alert--error" role="alert">
                  {error}
                </div>
              ) : null}
            </>
          )}
        </motion.div>
      </AnimatePresence>

      <div className="lp-auth__actions" style={{ paddingTop: 18 }}>
        {step > 0 ? <Btn type="button" variant="quiet" label="Back" onClick={() => setStep((x) => x - 1)} /> : null}
        {step < STEPS.length - 1 ? (
          <Btn type="button" label="Continue" onClick={next} />
        ) : (
          <Btn type="button" label={busy ? "Sending…" : "Send for review"} icon={busy ? SpinIcon : undefined} disabled={busy} onClick={send} />
        )}
      </div>
    </AuthShell>
  );
}
