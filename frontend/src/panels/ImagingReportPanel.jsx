// Track B. Renders imaging_report draft: scan viewer + ROI overlay + impression.
export default function ImagingReportPanel({ draft }) {
  return (
    <section className="support-panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Track B draft</p>
          <h3>Imaging preliminary report</h3>
        </div>
        <span className={`urgency-badge ${draft?.urgency ?? "routine"}`}>{draft?.urgency ?? "routine"}</span>
      </div>
      <div className="scan-placeholder">
        <span>Prelim image view</span>
      </div>
      <h4>Findings</h4>
      <ul className="finding-list">
        {(draft?.findings ?? []).map((finding) => (
          <li key={finding}>{finding}</li>
        ))}
      </ul>
      <h4>Impression</h4>
      <p>{draft?.impression || "No imaging impression yet."}</p>
    </section>
  );
}
