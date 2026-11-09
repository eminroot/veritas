import React from "react";
import { BadgeCheck, Camera, Check, Eye, FileText, Landmark, Link2, Receipt, ScrollText } from "lucide-react";
import { StatusTag, fmtDate } from "@/components/donate/bits";
import type { Project } from "@/data/projects";
import { proofOf, type ProofDoc } from "@/data/sample-proof";
import { manat } from "@/lib/money";
import { EvidencePhotos, ViewDocument, VoteResult } from "./ProofViewer";
import "./proof.css";

const ICON: Record<ProofDoc["kind"], React.ElementType> = {
  photos: Camera,
  manifest: ScrollText,
  invoice: FileText,
  receipt: Receipt,
  chain: Link2,
  decision: BadgeCheck,
  payment: Landmark,
};

/**
 * A project's proof on its public page, milestone by milestone: the site photos, every
 * document to open, and the donors' vote, so that anyone can look before they give.
 */
export default function ProjectProof({ project }: { project: Project }) {
  const proven = project.milestones.map((m, i) => ({ m, i, proof: proofOf(project, i) })).filter((x) => x.proof);
  if (!proven.length) return null;
  return (
    <div className="pv-proj">
      {proven.map(({ m, i, proof }) => (
        <section className="pv-proj__ms" key={i} aria-label={`Milestone ${i + 1}: ${m.title}`}>
          <header className="pv-proj__head">
            <span className={"pv-proj__num" + (m.status === "paid" ? " is-paid" : "")} aria-hidden="true">
              {m.status === "paid" ? <Check /> : i + 1}
            </span>
            <div>
              <h3>{m.title}</h3>
              <p>
                {manat(m.budget)} · {m.paidAt ? `paid to ${project.contractor.name} on ${fmtDate(m.paidAt)}` : `due ${fmtDate(m.due)}`}
              </p>
            </div>
            <StatusTag status={m.status} />
          </header>
          <EvidencePhotos project={project} index={i} />
          <div className="pv-docs">
            {proof?.docs.map((doc) => {
              const Icon = ICON[doc.kind];
              return (
                <ViewDocument key={doc.kind} project={project} index={i} doc={doc} className="pv-doc">
                  <span className="pv-doc__ico" aria-hidden="true">
                    <Icon />
                  </span>
                  <span className="pv-doc__text">
                    <b>{doc.title}</b>
                    <em>{doc.public ? "Public" : "Private; its fingerprint is public"}</em>
                  </span>
                  <Eye className="pv-doc__eye" aria-hidden="true" />
                </ViewDocument>
              );
            })}
          </div>
          <VoteResult project={project} index={i} />
        </section>
      ))}
    </div>
  );
}
