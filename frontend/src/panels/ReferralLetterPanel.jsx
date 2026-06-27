import { useEffect, useMemo, useState } from "react";

// Track D. Renders referral_letter draft: editable letter + sign & export.
export default function ReferralLetterPanel({ draft, patient, signedLetters = [], onAudit, onSigned }) {
  const [specialty, setSpecialty] = useState("");
  const [reason, setReason] = useState("");
  const [letter, setLetter] = useState("");
  const [reviewer, setReviewer] = useState("Dr. Reviewer");
  const [isSigned, setIsSigned] = useState(false);
  const [copyState, setCopyState] = useState("");

  useEffect(() => {
    setSpecialty(draft?.recipient_specialty ?? "");
    setReason(draft?.reason_for_referral ?? "");
    setLetter(draft?.letter_markdown ?? "");
    setIsSigned(false);
    setCopyState("");
  }, [draft]);

  const wordCount = useMemo(() => letter.trim().split(/\s+/).filter(Boolean).length, [letter]);
  const canSign = reviewer.trim() && specialty.trim() && reason.trim() && letter.trim();

  function handleFieldEdit(callback, auditLabel) {
    return (event) => {
      callback(event.target.value);
      setIsSigned(false);
      onAudit?.("Clinician", auditLabel, "Referral draft changed; signature reset");
    };
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
        <span className={isSigned ? "sign-state signed" : "sign-state draft"}>
          {isSigned ? "Signed" : "Draft"}
        </span>
      </div>

      <div className="letter-controls">
        <label>
          Specialty
          <input
            value={specialty}
            onChange={handleFieldEdit(setSpecialty, "Edited referral specialty")}
            placeholder="Internal Medicine"
          />
        </label>
        <label>
          Reason
          <input
            value={reason}
            onChange={handleFieldEdit(setReason, "Edited referral reason")}
            placeholder="Reason for referral"
          />
        </label>
        <label>
          Reviewer
          <input value={reviewer} onChange={(event) => setReviewer(event.target.value)} />
        </label>
      </div>

      <label className="letter-editor">
        Letter draft
        <textarea value={letter} onChange={handleFieldEdit(setLetter, "Edited referral letter")} />
      </label>

      <div className="letter-footer">
        <span>{wordCount} words</span>
        <div className="letter-actions">
          <button type="button" onClick={handleCopy} disabled={!letter.trim()}>
            {copyState || "Copy"}
          </button>
          <button type="button" className="primary-action" onClick={handleSign} disabled={!canSign}>
            Sign
          </button>
        </div>
      </div>

      <div className="signed-log">
        <h4>Signed outputs</h4>
        {signedLetters.length === 0 ? (
          <p>No signed referral yet.</p>
        ) : (
          <ul>
            {signedLetters.map((item) => (
              <li key={item.signedAt}>
                <strong>{item.specialty}</strong>
                <span>{new Date(item.signedAt).toLocaleString()} by {item.reviewer}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
