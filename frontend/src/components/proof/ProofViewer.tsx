import React, { useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { BadgeCheck, Camera, Check, ChevronLeft, ChevronRight, Eye, Landmark, Link2, Lock, MapPin, QrCode, ScanFace, X } from "lucide-react";
import { fmtDate } from "@/components/donate/bits";
import type { Project } from "@/data/projects";
import {
  ballotOf,
  chainOf,
  challengeCode,
  invoiceOf,
  manifestOf,
  paymentOf,
  photosOf,
  proofOf,
  receiptOf,
  sampleHex,
  type EvidencePhoto,
  type ProofDoc,
} from "@/data/sample-proof";
import { fmtCount, manat } from "@/lib/money";
import "./proof.css";

/**
 * The proof behind a milestone, to open: the site photos full size with what the capture app
 * recorded for each, and every document (invoice, e-kassa receipt, capture manifest, the
 * officer's decision, the bank's payment and the on-chain record) as a page to read.
 * Sample data: the photos stand in for a real project's, and the documents are made from it.
 */

const time = (iso: string) => iso.slice(11, 16);
const coord = (n: number) => n.toFixed(5);
const short = (hex: string, head = 10) => `${hex.slice(0, head)}…${hex.slice(-6)}`;

function Shell({
  open,
  onOpenChange,
  title,
  wide = false,
  children,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  wide?: boolean;
  children: React.ReactNode;
}) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="pv-overlay" />
        <Dialog.Content className={"pv-dialog" + (wide ? " pv-dialog--wide" : "")} aria-describedby={undefined}>
          <Dialog.Title className="pv-title">{title}</Dialog.Title>
          <Dialog.Close className="pv-close" aria-label="Close">
            <X />
          </Dialog.Close>
          {children}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

/* ------------------------------------------------------------------ photos */

function Lightbox({ project, index, photos, at, onAt, open, onOpenChange }: {
  project: Project;
  index: number;
  photos: EvidencePhoto[];
  at: number;
  onAt: (n: number) => void;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const photo = photos[at];
  const file = manifestOf(project, index).files[at];
  const code = challengeCode(project, index);
  if (!photo) return null;
  const go = (step: number) => onAt((at + step + photos.length) % photos.length);
  return (
    <Shell open={open} onOpenChange={onOpenChange} title={`Photo ${at + 1} of ${photos.length}: ${photo.caption}`} wide>
      <div
        className="pv-lightbox"
        onKeyDown={(e) => {
          if (e.key === "ArrowRight") go(1);
          if (e.key === "ArrowLeft") go(-1);
        }}
      >
        <figure className="pv-shot">
          <img src={photo.src} alt={photo.caption} />
          <span className="pv-shot__code" aria-label={`Challenge code ${code}`}>
            <small>Today's code</small>
            {code}
          </span>
          {photos.length > 1 ? (
            <>
              <button type="button" className="pv-shot__nav pv-shot__nav--prev" onClick={() => go(-1)} aria-label="Previous photo">
                <ChevronLeft />
              </button>
              <button type="button" className="pv-shot__nav pv-shot__nav--next" onClick={() => go(1)} aria-label="Next photo">
                <ChevronRight />
              </button>
            </>
          ) : null}
        </figure>
        <aside className="pv-meta">
          <p className="pv-meta__k">
            Milestone {index + 1} · photo {at + 1} of {photos.length}
          </p>
          <h3>{photo.caption}</h3>
          <dl>
            <div>
              <dt>Taken</dt>
              <dd>
                {fmtDate(photo.takenAt.slice(0, 10))}, {time(photo.takenAt)}
              </dd>
            </div>
            <div>
              <dt>Where</dt>
              <dd>
                {coord(photo.lat)}, {coord(photo.lng)} ±{photo.accuracy} m
              </dd>
            </div>
            <div>
              <dt>SHA-256</dt>
              <dd className="pv-mono">{file ? short(file.sha256, 16) : "—"}</dd>
            </div>
          </dl>
          <ul className="pv-passes">
            <li>
              <MapPin aria-hidden="true" /> Inside {project.place}'s site boundary
            </li>
            <li>
              <Camera aria-hidden="true" /> Code {code} readable in the photo
            </li>
            <li>
              <Check aria-hidden="true" /> Never seen before, here or on any project
            </li>
            <li>
              <ScanFace aria-hidden="true" /> Faces and number plates blurred
            </li>
          </ul>
          <p className="pv-credit">
            Sample photo: {photo.credit}. It stands in for a real project's photo.
          </p>
          {photos.length > 1 ? (
            <div className="pv-thumbs" role="list">
              {photos.map((p, k) => (
                <button
                  key={p.src}
                  type="button"
                  role="listitem"
                  className={k === at ? "is-on" : ""}
                  onClick={() => onAt(k)}
                  aria-label={`Photo ${k + 1}: ${p.caption}`}
                >
                  <img src={p.src} alt="" />
                </button>
              ))}
            </div>
          ) : null}
        </aside>
      </div>
    </Shell>
  );
}

/** A milestone's site photos as a grid; each opens full size. Nothing when there are none to show. */
export function EvidencePhotos({ project, index, compact = false }: { project: Project; index: number; compact?: boolean }) {
  const photos = photosOf(project, index);
  const [open, setOpen] = useState(false);
  const [at, setAt] = useState(0);
  if (!photos.length) return null;
  return (
    <>
      <div className={"pv-grid" + (compact ? " pv-grid--compact" : "")}>
        {photos.map((p, k) => (
          <button
            type="button"
            key={p.src}
            className="pv-tile"
            onClick={() => {
              setAt(k);
              setOpen(true);
            }}
            aria-label={`Open photo ${k + 1}: ${p.caption}`}
          >
            <img src={p.src} alt="" loading="lazy" />
            <span className="pv-tile__stamp">
              <Camera aria-hidden="true" />
              {fmtDate(p.takenAt.slice(0, 10), { day: "numeric", month: "short" })} · {time(p.takenAt)}
            </span>
            <span className="pv-tile__cap">{p.caption}</span>
          </button>
        ))}
      </div>
      <Lightbox project={project} index={index} photos={photos} at={at} onAt={setAt} open={open} onOpenChange={setOpen} />
    </>
  );
}

/* ------------------------------------------------------------------ documents */

function Paper({ children, kind }: { children: React.ReactNode; kind: string }) {
  return <article className={`pv-paper pv-paper--${kind}`}>{children}</article>;
}

function Fingerprint({ label, value }: { label: string; value: string }) {
  return (
    <p className="pv-print">
      <Link2 aria-hidden="true" />
      <span>
        {label} <code>{value}</code>
      </span>
    </p>
  );
}

function InvoicePaper({ project, index, doc }: { project: Project; index: number; doc: ProofDoc }) {
  const inv = invoiceOf(project, index);
  const m = project.milestones[index];
  return (
    <Paper kind="invoice">
      <header className="pv-paper__head">
        <div>
          <b className="pv-paper__brand">{inv.seller.name}</b>
          <span>
            VÖEN {inv.seller.voen} · {inv.seller.place}
          </span>
        </div>
        <div className="pv-paper__right">
          <b>Invoice</b>
          <span>No. {inv.number}</span>
          <span>{fmtDate(inv.date)}</span>
        </div>
      </header>
      <div className="pv-paper__parties">
        <div>
          <small>Bill to</small>
          <b>{inv.buyer.name}</b>
          <span>
            VÖEN {inv.buyer.voen} · {inv.buyer.place}
          </span>
        </div>
        <div>
          <small>For</small>
          <b>{project.title}</b>
          <span>
            Milestone {index + 1}: {m.title}
          </span>
        </div>
      </div>
      <table className="pv-table">
        <thead>
          <tr>
            <th>Item</th>
            <th>Amount</th>
          </tr>
        </thead>
        <tbody>
          {inv.lines.map((l) => (
            <tr key={l.item}>
              <td>{l.item}</td>
              <td>{manat(l.amount, { exact: true })}</td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr>
            <td>Of which VAT (18%)</td>
            <td>{manat(inv.vat, { exact: true })}</td>
          </tr>
          <tr className="pv-table__total">
            <td>Total</td>
            <td>{manat(inv.total, { exact: true })}</td>
          </tr>
        </tfoot>
      </table>
      <p className="pv-paper__note">
        To be paid from the project's Veritas escrow to account {inv.seller.iban}, never through the organisation. The total
        matches the milestone's budget in the Passport.
      </p>
      <span className="pv-stamp" aria-hidden="true">
        {inv.seller.name}
        <br />
        VÖEN {inv.seller.voen}
      </span>
      <Fingerprint label="This file's SHA-256, as recorded on-chain:" value={short(doc.fingerprint, 16)} />
    </Paper>
  );
}

function QrPattern({ seed }: { seed: string }) {
  const hex = sampleHex(seed, 128);
  const cells: boolean[] = [];
  for (let i = 0; i < 21 * 21; i++) cells.push(parseInt(hex[i % hex.length], 16) % 2 === 0);
  const finder = (r: number, c: number) => {
    const inBox = (r0: number, c0: number) => r >= r0 && r < r0 + 7 && c >= c0 && c < c0 + 7;
    return inBox(0, 0) || inBox(0, 14) || inBox(14, 0);
  };
  return (
    <svg className="pv-qr" viewBox="0 0 21 21" aria-hidden="true" shapeRendering="crispEdges">
      <rect width="21" height="21" fill="#fff" />
      {cells.map((on, i) => {
        const r = Math.floor(i / 21);
        const c = i % 21;
        if (finder(r, c)) return null;
        return on ? <rect key={i} x={c} y={r} width="1" height="1" fill="#242426" /> : null;
      })}
      {[
        [0, 0],
        [0, 14],
        [14, 0],
      ].map(([r, c]) => (
        <g key={`${r}-${c}`}>
          <rect x={c} y={r} width="7" height="7" fill="#242426" />
          <rect x={c + 1} y={r + 1} width="5" height="5" fill="#fff" />
          <rect x={c + 2} y={r + 2} width="3" height="3" fill="#242426" />
        </g>
      ))}
    </svg>
  );
}

function ReceiptPaper({ project, index, doc }: { project: Project; index: number; doc: ProofDoc }) {
  const r = receiptOf(project, index);
  return (
    <Paper kind="receipt">
      <div className="pv-receipt">
        <b className="pv-receipt__k">e-kassa</b>
        <span>Fiscal receipt</span>
        <hr />
        <b>{r.seller.name}</b>
        <span>VÖEN {r.seller.voen}</span>
        <span>{r.seller.place}</span>
        <hr />
        <div className="pv-receipt__row">
          <span>Receipt No.</span>
          <span>{r.number}</span>
        </div>
        <div className="pv-receipt__row">
          <span>Date</span>
          <span>
            {fmtDate(r.date)} {r.time}
          </span>
        </div>
        <div className="pv-receipt__row">
          <span>Milestone {index + 1}</span>
          <span>{manat(r.total, { exact: true })}</span>
        </div>
        <hr />
        <div className="pv-receipt__row pv-receipt__total">
          <span>TOTAL</span>
          <span>{manat(r.total, { exact: true })}</span>
        </div>
        <div className="pv-receipt__row">
          <span>incl. VAT 18%</span>
          <span>{manat(Math.round((r.total * 18) / 118), { exact: true })}</span>
        </div>
        <hr />
        <QrPattern seed={r.fiscalId} />
        <span className="pv-mono">Fiscal ID {r.fiscalId}</span>
      </div>
      <p className="pv-paper__note">
        <QrCode aria-hidden="true" /> Veritas read the QR code and matched the State Tax Service's record of this receipt: same
        seller, date and amount as the invoice.
      </p>
      <Fingerprint label="This file's SHA-256:" value={short(doc.fingerprint, 16)} />
    </Paper>
  );
}

function ManifestPaper({ project, index }: { project: Project; index: number }) {
  const mf = manifestOf(project, index);
  const shown = mf.files.slice(0, 8);
  return (
    <Paper kind="manifest">
      <header className="pv-paper__head">
        <div>
          <b className="pv-paper__brand">Capture manifest</b>
          <span>{mf.device}</span>
        </div>
        <div className="pv-paper__right">
          <span>Session {mf.session}</span>
          <span>Today's code {mf.code}</span>
        </div>
      </header>
      <table className="pv-table pv-table--mono">
        <thead>
          <tr>
            <th>File</th>
            <th>Taken</th>
            <th>GPS</th>
            <th>SHA-256</th>
          </tr>
        </thead>
        <tbody>
          {shown.map((f) => (
            <tr key={f.name + f.sha256}>
              <td>{f.name}</td>
              <td>{time(f.takenAt)}</td>
              <td>
                {coord(f.lat)}, {coord(f.lng)} ±{f.accuracy}m
              </td>
              <td>{short(f.sha256, 8)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {mf.files.length > shown.length ? <p className="pv-paper__note">…and {mf.files.length - shown.length} more photos.</p> : null}
      <ul className="pv-passes pv-passes--paper">
        <li>
          <Check aria-hidden="true" /> Signed on the phone with its hardware key; the signature checks out
        </li>
        <li>
          <Check aria-hidden="true" /> Every file's fingerprint matches the photo that was uploaded
        </li>
        <li>
          <Check aria-hidden="true" /> Every place is inside the site boundary drawn in the Passport
        </li>
      </ul>
      <Fingerprint label="Signature:" value={short(mf.signature, 18)} />
    </Paper>
  );
}

function DecisionPaper({ project, index, doc }: { project: Project; index: number; doc: ProofDoc }) {
  const pr = proofOf(project, index);
  const m = project.milestones[index];
  if (!pr) return null;
  const d = pr.decision;
  const officer = pr.checks.filter((c) => c.how === "officer");
  const automatic = pr.checks.filter((c) => c.how === "automatic");
  return (
    <Paper kind="decision">
      <header className="pv-paper__head">
        <div>
          <b className="pv-paper__brand">Decision on milestone {index + 1}</b>
          <span>{project.title}</span>
        </div>
        <div className="pv-paper__right">
          <span className="pv-approved">
            <BadgeCheck aria-hidden="true" /> Approved
          </span>
          <span>{d.at ? fmtDate(d.at) : ""}</span>
        </div>
      </header>
      <p className="pv-paper__body">
        I have read the evidence for “{m.title}”, the check report and the documents. {d.reason}
      </p>
      <div className="pv-checkcols">
        <div>
          <small>Automatic checks</small>
          {automatic.map((c) => (
            <span key={c.number}>
              <Check aria-hidden="true" /> {c.title}
            </span>
          ))}
        </div>
        <div>
          <small>Checked by the officer</small>
          {officer.map((c) => (
            <span key={c.number}>
              <Check aria-hidden="true" /> {c.title}
            </span>
          ))}
        </div>
      </div>
      <div className="pv-sign">
        <span className="pv-sign__name">{d.officer}</span>
        <span>
          Verification Officer, {d.firm}. Independent of the organisation and the contractor, named in the Passport.
        </span>
      </div>
      <Fingerprint label="Signature (EIP-712), checked on-chain:" value={short(doc.fingerprint, 16)} />
    </Paper>
  );
}

function PaymentPaper({ project, index }: { project: Project; index: number }) {
  const pay = paymentOf(project, index);
  if (!pay) return null;
  return (
    <Paper kind="payment">
      <header className="pv-paper__head">
        <div>
          <b className="pv-paper__brand">Payment order</b>
          <span>From the project's escrow account at the partner bank</span>
        </div>
        <div className="pv-paper__right">
          <span>Ref. {pay.reference}</span>
          <span>{fmtDate(pay.date)}</span>
        </div>
      </header>
      <dl className="pv-deflist">
        <div>
          <dt>Pay</dt>
          <dd className="pv-big">{manat(pay.amount, { exact: true })}</dd>
        </div>
        <div>
          <dt>To</dt>
          <dd>
            {pay.to.name}, VÖEN {pay.to.voen}
          </dd>
        </div>
        <div>
          <dt>Account</dt>
          <dd className="pv-mono">{pay.to.iban}</dd>
        </div>
        <div>
          <dt>Purpose</dt>
          <dd>{pay.purpose}</dd>
        </div>
        <div>
          <dt>Status</dt>
          <dd>
            <span className="pv-approved">
              <Landmark aria-hidden="true" /> Executed by the bank
            </span>
          </dd>
        </div>
      </dl>
      <p className="pv-paper__note">
        <Lock aria-hidden="true" /> The bank pays only what the escrow contract releases: an approved milestone whose vote passed.
        Every day the bank's balance, Veritas's ledger and the contracts are compared, and releases stop if they differ.
      </p>
    </Paper>
  );
}

function ChainPaper({ project, index }: { project: Project; index: number }) {
  const events = chainOf(project, index);
  return (
    <Paper kind="chain">
      <header className="pv-paper__head">
        <div>
          <b className="pv-paper__brand">On the public record</b>
          <span>Polygon, the Amoy test network while Veritas is a prototype</span>
        </div>
      </header>
      <ol className="pv-chain">
        {events.map((e) => (
          <li key={e.name}>
            <span className="pv-chain__dot" aria-hidden="true" />
            <div>
              <b>{e.name}</b>
              <span>{e.detail}</span>
              <span className="pv-mono">
                Block {fmtCount(e.block)} · tx {short(e.tx, 10)} · {fmtDate(e.date)}
              </span>
            </div>
          </li>
        ))}
      </ol>
      <p className="pv-paper__note">
        <Link2 aria-hidden="true" /> These entries are kept by thousands of independent computers, not by Veritas. Anyone can
        look them up, and nobody, Veritas included, can change them.
      </p>
    </Paper>
  );
}

function PhotosNote({ project, index }: { project: Project; index: number }) {
  const n = project.milestones[index]?.evidence?.photos ?? 0;
  return (
    <Paper kind="note">
      <p className="pv-paper__body">
        This sample project's {n} photos are not part of the demo. The finished project “A warm, dry school for 380 pupils in
        Gəncə” has every photo, document and vote open, milestone by milestone.
      </p>
    </Paper>
  );
}

/** A button that opens one of a milestone's documents. */
export function ViewDocument({
  project,
  index,
  doc,
  className = "pv-view",
  children,
}: {
  project: Project;
  index: number;
  doc: ProofDoc;
  className?: string;
  children?: React.ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const photos = doc.kind === "photos" ? photosOf(project, index) : [];
  const [at, setAt] = useState(0);
  return (
    <>
      <button type="button" className={className} onClick={() => setOpen(true)} aria-label={`Open ${doc.title}`}>
        {children ?? (
          <>
            <Eye aria-hidden="true" /> View
          </>
        )}
      </button>
      {doc.kind === "photos" && photos.length ? (
        <Lightbox project={project} index={index} photos={photos} at={at} onAt={setAt} open={open} onOpenChange={setOpen} />
      ) : (
        <Shell open={open} onOpenChange={setOpen} title={`${doc.title}: milestone ${index + 1}`}>
          {doc.kind === "invoice" ? <InvoicePaper project={project} index={index} doc={doc} /> : null}
          {doc.kind === "receipt" ? <ReceiptPaper project={project} index={index} doc={doc} /> : null}
          {doc.kind === "manifest" ? <ManifestPaper project={project} index={index} /> : null}
          {doc.kind === "decision" ? <DecisionPaper project={project} index={index} doc={doc} /> : null}
          {doc.kind === "payment" ? <PaymentPaper project={project} index={index} /> : null}
          {doc.kind === "chain" ? <ChainPaper project={project} index={index} /> : null}
          {doc.kind === "photos" ? <PhotosNote project={project} index={index} /> : null}
        </Shell>
      )}
    </>
  );
}

/** The donors' vote on a milestone, as a result to read at a glance. */
export function VoteResult({ project, index }: { project: Project; index: number }) {
  const b = ballotOf(project, index);
  if (!b) return null;
  const cast = b.yes + b.no;
  const yes = cast ? Math.round((b.yes * 100) / cast) : 0;
  return (
    <div className="pv-vote">
      <div className="pv-vote__head">
        <b>{b.state === "open" ? "Vote open" : `Passed with ${yes}% yes`}</b>
        <span>
          {fmtDate(b.opened, { day: "numeric", month: "short" })} to {fmtDate(b.closes)}
        </span>
      </div>
      <div className="pv-vote__bar" role="img" aria-label={`${b.yes} yes, ${b.no} no`}>
        <i style={{ width: `${yes}%` }} />
      </div>
      <div className="pv-vote__nums">
        <span>
          <b>{fmtCount(b.yes)}</b> yes · <b>{fmtCount(b.no)}</b> no
        </span>
        <span>
          {fmtCount(cast)} of {fmtCount(b.eligible)} receipts voted ({b.eligible ? Math.round((cast * 100) / b.eligible) : 0}%)
        </span>
      </div>
    </div>
  );
}
