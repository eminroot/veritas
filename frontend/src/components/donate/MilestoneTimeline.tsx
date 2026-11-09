import React from "react";
import { motion } from "framer-motion";
import { Camera, Check, Link2, ShieldCheck } from "lucide-react";
import type { Project } from "@/data/projects";
import { manat, percentOf } from "@/lib/money";
import { STATUS, StatusTag, fmtDate } from "./bits";

/**
 * A project's milestones, top to bottom: what each one costs, how much of it is in
 * escrow, where it stands and the evidence behind it. The rail between markers fills as
 * far as the money has been paid out.
 */
export default function MilestoneTimeline({ project }: { project: Project }) {
  return (
    <ol className="v-steps">
      {project.milestones.map((m, i) => {
        const s = STATUS[m.status];
        const pct = percentOf(m.funded, m.budget);
        return (
          <motion.li
            key={m.title}
            className={`v-step v-step--${m.status}`}
            initial={{ opacity: 0, y: 14 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: "-30px" }}
            transition={{ duration: 0.45, ease: [0.16, 1, 0.3, 1], delay: i * 0.06 }}
          >
            <span className="v-step__mark" aria-hidden="true">
              {m.status === "paid" ? <Check /> : i + 1}
            </span>
            <div className="v-step__body">
              <div className="v-step__top">
                <h3>{m.title}</h3>
                <StatusTag status={m.status} />
              </div>
              <p className="v-step__say">{s.say}</p>
              <div className="v-step__money">
                <div className="v-step__bar" role="img" aria-label={`${manat(m.funded)} of ${manat(m.budget)} in escrow or paid`}>
                  <motion.i
                    initial={{ width: 0 }}
                    whileInView={{ width: `${pct}%` }}
                    viewport={{ once: true }}
                    transition={{ duration: 0.9, ease: [0.16, 1, 0.3, 1], delay: 0.15 + i * 0.06 }}
                  />
                </div>
                <span>
                  <b>{manat(m.funded)}</b> of {manat(m.budget)}
                </span>
              </div>
              <div className="v-step__meta">
                {m.evidence ? (
                  <>
                    <span>
                      <Camera aria-hidden="true" />
                      {m.evidence.photos} photos from the site
                    </span>
                    <span>
                      <ShieldCheck aria-hidden="true" />
                      {m.evidence.checksPassed} of {m.evidence.checksTotal} checks passed
                    </span>
                    {m.evidence.anchoredAt ? (
                      <span>
                        <Link2 aria-hidden="true" />
                        Recorded on-chain {fmtDate(m.evidence.anchoredAt, { day: "numeric", month: "short" })}
                      </span>
                    ) : null}
                  </>
                ) : (
                  <span>Due {fmtDate(m.due)}</span>
                )}
                {m.paidAt ? <span>Paid {fmtDate(m.paidAt, { day: "numeric", month: "short" })}</span> : null}
              </div>
            </div>
          </motion.li>
        );
      })}
    </ol>
  );
}
