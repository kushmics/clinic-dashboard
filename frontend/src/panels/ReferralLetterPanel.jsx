import { useEffect, useMemo, useRef, useState } from "react";

// Track D. Renders the referral_letter draft. The letter is drafted for the
// clinician automatically; here they edit it as plain text (basic bold/italic
// + a font-size control — no markdown), then drive one morphing action button:
// Sign letter -> Send referral -> Sent.
const FONT_SIZES = [
  { label: "Small", value: 14 },
  { label: "Normal", value: 16 },
  { label: "Large", value: 19 },
  { label: "X-Large", value: 22 },
];

export default function ReferralLetterPanel({
  draft,
  patient,
  reviewerName,
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
  const [reviewer, setReviewer] = useState(reviewerName || "Dr. Reviewer");
  const [isSigned, setIsSigned] = useState(false);
  const [isSent, setIsSent] = useState(false);
  const [fontSize, setFontSize] = useState(16);
  const [copyState, setCopyState] = useState("");
  const editorRef = useRef(null);

  // Load a fresh draft into the editor. innerText keeps it pure text and
  // preserves line breaks; bold/italic are applied visually via execCommand.
  useEffect(() => {
    const text = draft?.letter_markdown ?? "";
    setSpecialty(draft?.recipient_specialty ?? "");
    setReason(draft?.reason_for_referral ?? "");
    setLetter(text);
    setIsSigned(false);
    setIsSent(false);
    setCopyState("");
    if (editorRef.current) editorRef.current.innerText = text;
  }, [draft]);

  useEffect(() => {
    if (reviewerName) setReviewer(reviewerName);
  }, [reviewerName]);

  const wordCount = useMemo(() => letter.trim().split(/\s+/).filter(Boolean).length, [letter]);
  const canSign = reviewer.trim() && specialty.trim() && reason.trim() && letter.trim();

  function resetSignature() {
    setIsSigned(false);
    setIsSent(false);
  }

  function handleFieldEdit(callback) {
    return (event) => {
      callback(event.target.value);
      resetSignature();
    };
  }

  function handleFieldAudit(auditLabel) {
    onAudit?.("Clinician", auditLabel, "Referral draft changed; signature reset");
  }

  function handleEditorInput() {
    setLetter(editorRef.current?.innerText ?? "");
    resetSignature();
  }

  // Apply inline formatting to the current selection inside the editor.
  function format(command) {
    editorRef.current?.focus();
    document.execCommand(command, false, null);
    handleEditorInput();
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
              resetSignature();
            }}
          />
        </label>
      </div>

      <div className="format-toolbar" role="toolbar" aria-label="Letter formatting">
        <div className="format-group">
          <button type="button" className="format-btn" onMouseDown={(e) => e.preventDefault()} onClick={() => format("bold")} title="Bold" aria-label="Bold">
            <b>B</b>
          </button>
          <button type="button" className="format-btn" onMouseDown={(e) => e.preventDefault()} onClick={() => format("italic")} title="Italic" aria-label="Italic">
            <i>I</i>
          </button>
        </div>
        <label className="font-size-control">
          Font size
          <select value={fontSize} onChange={(e) => setFontSize(Number(e.target.value))}>
            {FONT_SIZES.map((size) => (
              <option key={size.value} value={size.value}>{size.label}</option>
            ))}
          </select>
        </label>
        <span className="word-count">{wordCount} words</span>
      </div>

      <div
        ref={editorRef}
        className="letter-editor-rich"
        contentEditable={!isSent}
        suppressContentEditableWarning
        onInput={handleEditorInput}
        onBlur={() => handleFieldAudit("Edited referral letter")}
        style={{ fontSize: `${fontSize}px` }}
        data-placeholder={isGenerating ? "Drafting…" : "The letter will appear here."}
      />

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
