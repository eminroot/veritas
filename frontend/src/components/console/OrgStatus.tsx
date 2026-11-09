import React from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import { Building2, Check, Clock, Send, XCircle } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { readOrgDraft, type OrgDraft } from "@/lib/orgDraft";
import { Panel, Tag } from "./kit";

/**
 * Where an organisation's application stands, from the API when connected (its charity
 * membership and status) and otherwise from what this browser saved during onboarding.
 */
export type OrgState = {
  name: string;
  status: "saved" | "draft" | "submitted" | "verified" | "rejected" | "suspended";
  source: "api" | "local";
  charityId?: string;
  draft: OrgDraft | null;
};

export function useOrgState(): OrgState | null {
  const { user, api } = useAuth();
  const draft = readOrgDraft(user?.id);
  if (api.status === "connected" && api.me.memberships.length) {
    const m = api.me.memberships[0];
    const s = m.charity_status as OrgState["status"];
    return { name: m.charity_name, status: s, source: "api", charityId: m.charity_id, draft };
  }
  if (draft) {
    return { name: draft.details.legal_name, status: draft.status === "submitted" ? "submitted" : "saved", source: "local", charityId: draft.charityId, draft };
  }
  return null;
}

const LABEL: Record<OrgState["status"], [string, "ok" | "warn" | "stop" | "dark" | "lime" | undefined]> = {
  saved: ["Not sent yet", "warn"],
  draft: ["Draft", "warn"],
  submitted: ["Under review", "lime"],
  verified: ["Verified", "ok"],
  rejected: ["Needs changes", "stop"],
  suspended: ["Suspended", "stop"],
};

export function OrgTag({ status }: { status: OrgState["status"] }) {
  const [label, tone] = LABEL[status];
  return <Tag tone={tone}>{label}</Tag>;
}

export default function OrgStatus({ compact = false }: { compact?: boolean }) {
  const org = useOrgState();
  if (!org) return null;
  const sent = org.status !== "saved" && org.status !== "draft";
  const verified = org.status === "verified";
  const steps = [
    { label: "Details", done: true },
    { label: "Documents", done: sent },
    { label: "Veritas review", done: verified, now: org.status === "submitted" },
    { label: "Verified", done: verified },
  ];

  return (
    <Panel
      title={compact ? org.name : "Verification"}
      icon={Building2}
      sub={
        org.status === "saved"
          ? "Saved on this device but not sent to Veritas yet: the API could not be reached."
          : org.status === "submitted"
            ? "Veritas is checking the documents. You will hear by email."
            : verified
              ? "Verified. You can publish projects and invite your field team."
              : org.status === "rejected"
                ? "Veritas asked for changes before it can verify the organisation."
                : org.status === "suspended"
                  ? "Suspended: projects cannot raise money until Veritas lifts it."
                  : "Finish the application and send it for review."
      }
      action={<OrgTag status={org.status} />}
    >
      <ol className="v-vsteps">
        {steps.map((s, i) => (
          <motion.li
            key={s.label}
            className={s.done ? "is-done" : s.now ? "is-now" : ""}
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.05 * i }}
          >
            <span>{s.done ? <Check /> : s.now ? <Clock /> : i + 1}</span>
            {s.label}
          </motion.li>
        ))}
      </ol>
      {org.status === "saved" || org.status === "draft" ? (
        <div className="v-orgcta">
          <Link to="/onboarding?resume=1" className="btn btn--primary">
            <Send />
            Send the application
          </Link>
        </div>
      ) : org.status === "rejected" ? (
        <div className="v-orgcta">
          <XCircle aria-hidden="true" />
          <span>Read the reviewer's notes on the organisation page, change what they asked, and send it again.</span>
        </div>
      ) : null}
      {compact ? (
        <div className="v-orgcta v-orgcta--quiet">
          <Link to="/organisation" className="link-btn">
            Open the organisation page
          </Link>
        </div>
      ) : null}
    </Panel>
  );
}
