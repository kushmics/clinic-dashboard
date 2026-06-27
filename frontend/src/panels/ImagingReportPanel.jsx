import AcuityBadge from "../components/AcuityBadge.jsx";

// Track B. Renders imaging_report draft: scan viewer + ROI overlay + impression.
export default function ImagingReportPanel({
  draft,
  imagePreviewUrl,
  fileName,
  isAnalyzing = false,
  onImageSelect,
}) {
  const limitations = draft?.limitations ?? [];

  function handleFileChange(event) {
    const file = event.target.files?.[0];
    // Upload + AI read fire together — same one-step flow as the lab report.
    if (file) onImageSelect?.(file);
    event.target.value = "";
  }

  return (
    <section className="support-panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Track B draft</p>
          <h3>Chest X-ray preliminary review</h3>
        </div>
        {draft?.urgency && <AcuityBadge urgency={draft.urgency} />}
      </div>

      {draft?.generation_note && <p className="generation-note">{draft.generation_note}</p>}

      <label className="scan-dropzone">
        {imagePreviewUrl ? (
          <img src={imagePreviewUrl} alt="Uploaded chest X-ray preview" />
        ) : (
          <span className="scan-dropzone-prompt">
            <strong>Click anywhere to upload a chest X-ray</strong>
            <small>The AI preliminary read runs automatically once the scan is added.</small>
          </span>
        )}
        {isAnalyzing && <span className="scan-analyzing">Analyzing scan…</span>}
        <input accept="image/*" type="file" onChange={handleFileChange} disabled={isAnalyzing} />
      </label>
      <p className="scan-disclaimer">
        {fileName ? `${fileName} · ` : ""}AI output is a first-pass draft for clinician review. It is not a final diagnosis.
      </p>

      <h4>Findings</h4>
      <ul className="finding-list">
        {(draft?.findings ?? []).map((finding) => (
          <li key={finding}>{finding}</li>
        ))}
      </ul>
      <h4>Impression</h4>
      <p>{draft?.impression || "No imaging impression yet."}</p>
      {limitations.length > 0 && (
        <>
          <h4>Limitations</h4>
          <ul className="finding-list">
            {limitations.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
