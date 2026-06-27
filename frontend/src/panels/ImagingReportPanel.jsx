import { useState } from "react";

// Track B. Renders imaging_report draft: scan viewer + ROI overlay + impression.
export default function ImagingReportPanel({
  draft,
  imagePreviewUrl,
  fileName,
  isAnalyzing = false,
  onImageSelect,
  onAnalyze,
}) {
  const [isDragging, setIsDragging] = useState(false);
  const possibleDiagnoses = draft?.possible_diagnoses ?? [];
  const limitations = draft?.limitations ?? [];

  function handleFileChange(event) {
    const file = event.target.files?.[0];
    if (file) onImageSelect?.(file);
  }

  function handleDrag(event) {
    event.preventDefault();
    event.stopPropagation();
    setIsDragging(true);
  }

  function handleDragLeave(event) {
    event.preventDefault();
    event.stopPropagation();
    if (!event.currentTarget.contains(event.relatedTarget)) {
      setIsDragging(false);
    }
  }

  function handleDrop(event) {
    event.preventDefault();
    event.stopPropagation();
    setIsDragging(false);
    const file = event.dataTransfer.files?.[0];
    if (file) onImageSelect?.(file);
  }

  return (
    <section className="support-panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Track B draft</p>
          <h3>Imaging preliminary review</h3>
        </div>
        <span
          className={`urgency-badge triage-${draft?.triage?.color ?? "blue"}`}
          title={draft?.triage ? `Level ${draft.triage.level} — wait ≤${draft.triage.target_minutes}min — composite ${draft.triage.composite}` : ""}
        >
          {draft?.triage?.label ?? "Non-Urgent"}
        </span>
      </div>

      {draft?.generation_note && <p className="generation-note">{draft.generation_note}</p>}

      <div className="imaging-workbench">
        <div
          className={isDragging ? "scan-viewer dragging" : "scan-viewer"}
          onDragEnter={handleDrag}
          onDragOver={handleDrag}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
        >
          {imagePreviewUrl ? (
            <img src={imagePreviewUrl} alt="Uploaded imaging study preview" />
          ) : fileName ? (
            <span>{fileName} ready for analysis</span>
          ) : (
            <span>Upload X-ray, CT, MRI, or scan</span>
          )}
        </div>
        <div className="scan-actions">
          <label className="image-upload-button">
            <span>{fileName || "Choose imaging study"}</span>
            <input accept="image/*,.dcm,.dicom,.nii,.nii.gz,.h5" type="file" onChange={handleFileChange} />
          </label>
          <button type="button" onClick={() => onAnalyze?.()} disabled={!fileName || isAnalyzing}>
            {isAnalyzing ? "Analyzing..." : "Run AI preliminary read"}
          </button>
          <p>
            AI output is a first-pass draft for clinician review. It is not a final diagnosis.
          </p>
        </div>
      </div>

      <h4>Findings</h4>
      <ul className="finding-list">
        {(draft?.findings ?? []).map((finding) => (
          <li key={finding}>{finding}</li>
        ))}
      </ul>
      {possibleDiagnoses.length > 0 && (
        <>
          <h4>Possible diagnoses</h4>
          <ul className="diagnosis-list">
            {possibleDiagnoses.map((item) => (
              <li key={`${item.condition}-${item.rationale}`}>
                <strong>{item.condition}</strong>
                <span>{item.confidence ?? "low"} confidence</span>
                <p>{item.rationale}</p>
              </li>
            ))}
          </ul>
        </>
      )}
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
