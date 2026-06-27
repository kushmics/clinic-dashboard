import { useEffect, useMemo, useState } from "react";

// Track D. Renders referral_letter draft: editable letter + sign & export.
export default function ReferralLetterPanel({
  draft,
  patient,
  signedLetters = [],
  sentReferrals = [],
  onAudit,
  onGenerate,
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
  const canSend = isSigned && !isSent;

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
    if (!canSign) return;
    const signedAt = new Date().toISOString();
    setIsSigned(true);
    onSigned?.({
      patientId: patient?.id,
      patientName: patient?.name,
      specialty,
      reason,
      letter,
      reviewer,
      signedAt,
    });
  }

  function handleSend() {
    if (!canSend) return;
    const sentAt = new Date().toISOString();
    setIsSent(true);
    onSent?.({
      patientId: patient?.id,
      patientName: patient?.name,
      specialty,
      reason,
      sentAt,
    });
  }

  async function handleCopy() {
    await navigator.clipboard.writeText(letter);
    setCopyState("Copied");
    onAudit?.("Clinician", "Copied referral letter", `${specialty} referral copied to clipboard`);
  }

  return (
    <section className="referral-panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Track D</p>
          <h3>Referral letter</h3>
        </div>
        <span className={isSent ? "sign-state sent" : isSigned ? "sign-state signed" : "sign-state draft"}>
          {isSent ? "Sent" : isSigned ? "Signed" : "Draft"}
        </span>
      </div>

      {draft?.generation_note && <p className="generation-note">{draft.generation_note}</p>}

      <div className="handoff-strip">
        <div className="handoff-step done">
          <span>Draft</span>
        </div>
        <div className={isSigned ? "handoff-step done" : "handoff-step"}>
          <span>Sign</span>
        </div>
        <div className={isSent ? "handoff-step done" : "handoff-step"}>
          <span>Send</span>
        </div>
      </div>

      <div className="letter-controls">
        <label>
          Specialty
          <input
            value={specialty}
            onChange={handleFieldEdit(setSpecialty)}
            onBlur={() => handleFieldAudit("Edited referral specialty")}
            placeholder="Internal Medicine"
          />
        </label>
        <label>
          Reason
          <input
            value={reason}
            onChange={handleFieldEdit(setReason)}
            onBlur={() => handleFieldAudit("Edited referral reason")}
            placeholder="Reason for referral"
          />
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
          <button className={mode === "edit" ? "active" : ""} onClick={() => setMode("edit")} type="button">
            Edit
          </button>
          <button className={mode === "preview" ? "active" : ""} onClick={() => setMode("preview")} type="button">
            Preview
          </button>
        </div>
        <button className="generate-action" type="button" onClick={onGenerate} disabled={isGenerating}>
          {isGenerating ? "Generating..." : "Generate with OpenAI"}
        </button>
      </div>

      <div className="letter-stage">
        {mode === "edit" ? (
          <label className="letter-editor">
            Letter draft
            <textarea
              value={letter}
              onChange={handleFieldEdit(setLetter)}
              onBlur={() => handleFieldAudit("Edited referral letter")}
            />
          </label>
        ) : (
          <article className="letter-preview">
            {letter.split("\n").map((line, index) => (
              <p key={`${line}-${index}`} className={line.trim() ? "" : "empty-line"}>
                {line || "\u00a0"}
              </p>
            ))}
          </article>
        )}
      </div>

      <div className="letter-footer">
        <span>{wordCount} words</span>
        <div className="letter-actions">
          <button type="button" onClick={handleCopy} disabled={!letter.trim()}>
            {copyState || "Copy"}
          </button>
          <button type="button" className="primary-action" onClick={handleSign} disabled={!canSign}>
            Sign
          </button>
          <button type="button" className="send-action" onClick={handleSend} disabled={!canSend}>
            {isSent ? "Sent" : "Send referral"}
          </button>
        </div>
      </div>

      <div className="signed-log">
        <h4>Referral handoff</h4>
        {signedLetters.length === 0 && sentReferrals.length === 0 ? (
          <p>No signed referral yet.</p>
        ) : (
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
        )}
      </div>
    </section>
  );
}
