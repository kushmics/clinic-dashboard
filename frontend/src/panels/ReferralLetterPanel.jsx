import { useEffect, useMemo, useState } from "react";

// Track D. Renders the referral_letter draft. The letter is drafted for the
// clinician automatically; here they edit it and drive one morphing action
// button: Sign letter -> Send referral -> Sent.
export default function ReferralLetterPanel({
  draft,
  patient,
  signedLetters = [],
  sentReferrals = [],
  onAudit,
  onSigned,
  onSent,
  isGenerating = false,
}) {
  const [specialty, setSpecialty] = useState("");
  const [reason, setReason] = useState("");
  const [letter, setLetter] = useState("");
  const [reviewer, setReviewer] = useState("Dr. Reviewer");
  const [isSigned, setIsSigned] = useState(false);
  const [isSent, setIsSent] = useState(false);
  const [mode, setMode] = useState("edit");
  const [copyState, setCopyState] = useState("");

  useEffect(() => {
    setSpecialty(draft?.recipient_specialty ?? "");
    setReason(draft?.reason_for_referral ?? "");
    setLetter(draft?.letter_markdown ?? "");
    setIsSigned(false);
    setIsSent(false);
    setCopyState("");
  }, [draft]);

  const wordCount = useMemo(() => letter.trim().split(/\s+/).filter(Boolean).length, [letter]);
  const canSign = reviewer.trim() && specialty.trim() && reason.trim() && letter.trim();

  function handleFieldEdit(callback) {
    return (event) => {
      callback(event.target.value);
      setIsSigned(false);
      setIsSent(false);
    };
  }

  function handleFieldAudit(auditLabel) {
    onAudit?.("Clinician", auditLabel, "Referral draft changed; signature reset");
  }

  function handleSign() {
    if (!canSign || isSigned) return;
    setIsSigned(true);
    onSigned?.({
      patientId: patient?.id,
      patientName: patient?.name,
      specialty,
      reason,
      letter,
      reviewer,
      signedAt: new Date().toISOString(),
    });
  }

  function handleSend() {
    if (!isSigned || isSent) return;
    setIsSent(true);
    onSent?.({
      patientId: patient?.id,
      patientName: patient?.name,
      specialty,
      reason,
      sentAt: new Date().toISOString(),
    });
  }

  // The single morphing action button at the bottom-right.
  const action = isSent
    ? { label: "Sent ✓", cls: "sent", onClick: () => {}, disabled: true }
    : isSigned
      ? { label: "Send referral →", cls: "send", onClick: handleSend, disabled: false }
      : { label: "Sign letter", cls: "sign", onClick: handleSign, disabled: !canSign };

  async function handleCopy() {
    await navigator.clipboard.writeText(letter);
    setCopyState("Copied");
    onAudit?.("Clinician", "Copied referral letter", `${specialty} referral copied to clipboard`);
  }

  return (
    <section className="referral-panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Referral letter</p>
          <h3>Review &amp; sign</h3>
        </div>
        <span className={isSent ? "sign-state sent" : isSigned ? "sign-state signed" : "sign-state draft"}>
          {isSent ? "Sent" : isSigned ? "Signed" : "Draft ready"}
        </span>
      </div>

      {isGenerating && <p className="generation-note">Drafting the letter from the reviewed case…</p>}
      {draft?.generation_note && <p className="generation-note">{draft.generation_note}</p>}

      <div className="letter-controls">
        <label>
          Specialty
          <input value={specialty} onChange={handleFieldEdit(setSpecialty)} onBlur={() => handleFieldAudit("Edited referral specialty")} placeholder="Internal Medicine" />
        </label>
        <label>
          Reason
          <input value={reason} onChange={handleFieldEdit(setReason)} onBlur={() => handleFieldAudit("Edited referral reason")} placeholder="Reason for referral" />
        </label>
        <label>
          Reviewer
          <input
            value={reviewer}
            onChange={(event) => {
              setReviewer(event.target.value);
              setIsSigned(false);
              setIsSent(false);
            }}
          />
        </label>
      </div>

      <div className="mode-row">
        <div className="segmented-control" aria-label="Letter mode">
          <button className={mode === "edit" ? "active" : ""} onClick={() => setMode("edit")} type="button">Edit</button>
          <button className={mode === "preview" ? "active" : ""} onClick={() => setMode("preview")} type="button">Preview</button>
        </div>
        <span className="word-count">{wordCount} words</span>
      </div>

      <div className="letter-stage">
        {mode === "edit" ? (
          <label className="letter-editor">
            Letter draft
            <textarea
              value={letter}
              onChange={handleFieldEdit(setLetter)}
              onBlur={() => handleFieldAudit("Edited referral letter")}
              placeholder={isGenerating ? "Drafting…" : "The letter will appear here."}
            />
          </label>
        ) : (
          <article className="letter-preview">
            {letter.split("\n").map((line, index) => (
              <p key={`${line}-${index}`} className={line.trim() ? "" : "empty-line"}>
                {line || " "}
              </p>
            ))}
          </article>
        )}
      </div>

      <div className="letter-footer">
        <button type="button" className="letter-copy" onClick={handleCopy} disabled={!letter.trim()}>
          {copyState || "Copy"}
        </button>
        <button type="button" className={`letter-action ${action.cls}`} onClick={action.onClick} disabled={action.disabled}>
          {action.label}
        </button>
      </div>

      {(signedLetters.length > 0 || sentReferrals.length > 0) && (
        <div className="signed-log">
          <h4>Referral handoff</h4>
          <ul>
            {signedLetters.map((item) => (
              <li key={item.signedAt}>
                <strong>{item.specialty}</strong>
                <span>{new Date(item.signedAt).toLocaleString()} by {item.reviewer}</span>
              </li>
            ))}
            {sentReferrals.map((item) => (
              <li key={item.sentAt}>
                <strong>Sent to {item.specialty}</strong>
                <span>{new Date(item.sentAt).toLocaleString()} via Workato workflow</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
