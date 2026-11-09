import React, { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import * as Dialog from "@radix-ui/react-dialog";
import { AnimatePresence, motion } from "framer-motion";
import { ArrowLeft, Check, Info, Lock, Repeat, X } from "lucide-react";
import { Btn } from "@/components/lp/primitives";
import { useAuth } from "@/contexts/AuthContext";
import type { Project } from "@/data/projects";
import { manat, parseManat, toQapik, type Qapik } from "@/lib/money";

/**
 * Giving to a project, in three steps: how much (and how), a review that shows exactly
 * where the money will wait, and a receipt.
 *
 * Card payments open at launch. Until then this is a faithful preview: it splits the gift
 * across the milestones the way the backend does (in order, filling what each still
 * needs, never past the goal) and says plainly that nothing is charged. It never asks
 * for a card number.
 */
type Kind = "once" | "proof";
type Step = "amount" | "review" | "done";

const CHIPS = [10, 25, 50, 100, 250];
const EASE = [0.16, 1, 0.3, 1] as const;

/** How a one-time gift is split: milestone by milestone, each up to what it still needs. */
export function splitGift(project: Project, amount: Qapik) {
  let left = amount;
  const parts: { index: number; title: string; amount: Qapik }[] = [];
  project.milestones.forEach((m, index) => {
    const need = m.budget - m.funded;
    if (left <= 0 || need <= 0) return;
    const take = Math.min(need, left);
    parts.push({ index, title: m.title, amount: take });
    left -= take;
  });
  return { parts, unused: left };
}

/** Milestones a Pay-on-Proof pledge will still be charged for: those not yet approved. */
const pledgeable = (project: Project) =>
  project.milestones.filter((m) => m.status !== "approved" && m.status !== "paid").length;

export default function DonateSheet({
  project,
  open,
  onOpenChange,
}: {
  project: Project;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const { user } = useAuth();
  const [step, setStep] = useState<Step>("amount");
  const [kind, setKind] = useState<Kind>("once");
  const [chip, setChip] = useState<number | null>(50);
  const [custom, setCustom] = useState("");

  const need = project.milestones.reduce((s, m) => s + (m.budget - m.funded), 0);
  const typed = custom.trim() ? parseManat(custom) : null;
  const amount: Qapik | null = custom.trim() ? typed : chip ? toQapik(chip) : null;
  const split = useMemo(() => (amount ? splitGift(project, amount) : null), [project, amount]);
  const charged = kind === "once" ? Math.min(amount ?? 0, need) : (amount ?? 0);
  const count = pledgeable(project);
  const valid = Boolean(amount && amount >= 100 && (kind === "proof" ? count > 0 : need > 0));

  const close = (o: boolean) => {
    onOpenChange(o);
    if (!o) window.setTimeout(() => setStep("amount"), 250);
  };

  return (
    <Dialog.Root open={open} onOpenChange={close}>
      <AnimatePresence>
        {open ? (
          <Dialog.Portal forceMount>
            <Dialog.Overlay asChild forceMount>
              <motion.div className="v-scrim" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} />
            </Dialog.Overlay>
            <Dialog.Content asChild forceMount aria-describedby={undefined}>
              <motion.div
                className="lp v-sheet"
                initial={{ opacity: 0, y: 40, scale: 0.98 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, y: 30, scale: 0.98 }}
                transition={{ duration: 0.4, ease: EASE }}
              >
                <div className="v-sheet__top">
                  {step === "review" ? (
                    <button className="v-sheet__icon" onClick={() => setStep("amount")} aria-label="Back">
                      <ArrowLeft />
                    </button>
                  ) : (
                    <span />
                  )}
                  <Dialog.Title className="v-sheet__title">
                    {step === "done" ? "Thank you" : step === "review" ? "Check your gift" : "Donate"}
                  </Dialog.Title>
                  <Dialog.Close className="v-sheet__icon" aria-label="Close">
                    <X />
                  </Dialog.Close>
                </div>

                <AnimatePresence mode="wait" initial={false}>
                  {step === "amount" ? (
                    <motion.div key="amount" className="v-sheet__body" initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -20 }} transition={{ duration: 0.25 }}>
                      <p className="v-sheet__for">{project.title}</p>

                      <div className="v-seg" role="radiogroup" aria-label="How to give">
                        <button role="radio" aria-checked={kind === "once"} className={kind === "once" ? "on" : ""} onClick={() => setKind("once")}>
                          <Lock aria-hidden="true" />
                          Give once
                        </button>
                        <button role="radio" aria-checked={kind === "proof"} className={kind === "proof" ? "on" : ""} onClick={() => setKind("proof")}>
                          <Repeat aria-hidden="true" />
                          Pay on proof
                        </button>
                      </div>
                      <p className="v-sheet__hint">
                        {kind === "once"
                          ? "Charged now and held in escrow until each milestone is proven."
                          : `Charged only when a milestone is approved: up to ${count} time${count === 1 ? "" : "s"} for this project.`}
                      </p>

                      <div className="v-amounts" role="group" aria-label="Amount">
                        {CHIPS.map((c) => (
                          <button
                            key={c}
                            className={"v-amount" + (chip === c && !custom.trim() ? " on" : "")}
                            onClick={() => {
                              setChip(c);
                              setCustom("");
                            }}
                            aria-pressed={chip === c && !custom.trim()}
                          >
                            ₼{c}
                          </button>
                        ))}
                        <label className={"v-amount v-amount--custom" + (custom.trim() ? " on" : "")}>
                          <span aria-hidden="true">₼</span>
                          <input
                            inputMode="decimal"
                            placeholder="Other"
                            aria-label="Other amount in manat"
                            value={custom}
                            onChange={(e) => setCustom(e.target.value)}
                          />
                        </label>
                      </div>
                      {custom.trim() && !typed ? <p className="v-sheet__err">Enter an amount in manat, like 30 or 12.50.</p> : null}
                      {amount !== null && amount < 100 ? <p className="v-sheet__err">The smallest gift is ₼1.</p> : null}

                      {kind === "once" && split && amount && amount >= 100 ? (
                        <div className="v-split">
                          <span className="v-split__h">Where {manat(Math.min(amount, need))} would wait</span>
                          {split.parts.map((p) => (
                            <div className="v-split__row" key={p.index}>
                              <span className="v-split__n">{p.index + 1}</span>
                              <span className="v-split__t">{p.title}</span>
                              <b>{manat(p.amount)}</b>
                            </div>
                          ))}
                          {split.unused > 0 ? (
                            <p className="v-sheet__note">
                              <Info aria-hidden="true" />
                              This project needs only {manat(need)} more, so that is all you would be charged.
                            </p>
                          ) : null}
                        </div>
                      ) : null}

                      <Btn type="button" size="wide" label={valid ? `Continue with ${manat(charged)}` : "Continue"} disabled={!valid} onClick={() => valid && setStep("review")} />
                    </motion.div>
                  ) : step === "review" ? (
                    <motion.div key="review" className="v-sheet__body" initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -20 }} transition={{ duration: 0.25 }}>
                      <dl className="v-review">
                        <div>
                          <dt>Project</dt>
                          <dd>{project.title}</dd>
                        </div>
                        <div>
                          <dt>{kind === "once" ? "Gift" : "Per approved milestone"}</dt>
                          <dd>{manat(charged)}</dd>
                        </div>
                        <div>
                          <dt>Held</dt>
                          <dd>In escrow, released only on checked proof</dd>
                        </div>
                        <div>
                          <dt>If the project stops</dt>
                          <dd>Your money comes back to your card, or moves to a similar project if you choose</dd>
                        </div>
                      </dl>
                      <p className="v-sheet__note v-sheet__note--warn">
                        <Info aria-hidden="true" />
                        Card payments open at launch. This is a preview: nothing is charged and no card details are asked for.
                      </p>
                      {!user ? (
                        <p className="v-sheet__hint">
                          <Link to="/login" onClick={() => close(false)}>
                            Sign in
                          </Link>{" "}
                          to keep a receipt for every gift in your account.
                        </p>
                      ) : null}
                      <Btn type="button" size="wide" label="Confirm (preview)" onClick={() => setStep("done")} />
                    </motion.div>
                  ) : (
                    <motion.div key="done" className="v-sheet__body v-done" initial={{ opacity: 0, scale: 0.96 }} animate={{ opacity: 1, scale: 1 }} transition={{ duration: 0.4, ease: EASE }}>
                      <div className="v-receipt">
                        <motion.span className="v-receipt__lock" initial={{ scale: 0, rotate: -20 }} animate={{ scale: 1, rotate: 0 }} transition={{ type: "spring", stiffness: 300, damping: 16, delay: 0.15 }}>
                          <Lock />
                        </motion.span>
                        <motion.b initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3 }}>
                          {manat(charged)}
                        </motion.b>
                        <motion.span initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.45 }}>
                          {kind === "once" ? "would now be in escrow" : "pledged per approved milestone"}
                        </motion.span>
                        <ul className="v-receipt__steps">
                          {["Held in escrow", "Photos from the site, checked", "Released to the builder"].map((t, i) => (
                            <motion.li key={t} initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.6 + i * 0.15 }}>
                              <i>
                                <Check />
                              </i>
                              {t}
                            </motion.li>
                          ))}
                        </ul>
                      </div>
                      <p className="v-sheet__hint">This was a preview, so no money moved. At launch you will get a receipt you can check on-chain.</p>
                      <Btn type="button" size="wide" label="Done" onClick={() => close(false)} />
                    </motion.div>
                  )}
                </AnimatePresence>
              </motion.div>
            </Dialog.Content>
          </Dialog.Portal>
        ) : null}
      </AnimatePresence>
    </Dialog.Root>
  );
}
