import { useState } from "react";
import AcuityBadge from "./AcuityBadge.jsx";

// Sign-off companion. Keeps the case evidence the clinician is attesting to —
// the chest X-ray, abnormal labs, red flags, top differentials — beside the
// letter so they never have to leave the page to check what they're signing.
export default function EvidenceRail({ xrayPreviewUrl, imagingDraft, labDraft, differentialDraft, onJumpToStep }) {
  const [zoom, setZoom] = useState(false);

  const abnormals = labDraft?.abnormals ?? [];
  const redFlags = differentialDraft?.red_flags ?? [];
  const differentials = (differentialDraft?.differentials ?? []).slice(0, 3);
  const impression = imagingDraft?.impression;

  return (
    <aside className="evidence-rail" aria-label="Case evidence">
      <div className="evidence-heading">
        <p className="eyebrow">Signing against</p>
        <h4>Case evidence</h4>
      </div>

      <section className="evidence-block">
        <h5>Chest X-ray</h5>
        {xrayPreviewUrl ? (
          <>
            <button type="button" className="evidence-scan" onClick={() => setZoom(true)} title="Click to enlarge">
              <img src={xrayPreviewUrl} alt="Chest X-ray under review" />
              <span className="scan-zoom-hint">Click to enlarge</span>
            </button>
            {impression && <p className="evidence-impression">{impression}</p>}
          </>
        ) : (
          <div className="evidence-empty">
            <p>No scan attached.</p>
            <button type="button" onClick={() => onJumpToStep?.("imaging")}>
              Add an X-ray in the Imaging step
            </button>
          </div>
        )}
      </section>

      {abnormals.length > 0 && (
        <section className="evidence-block">
          <div className="evidence-block-head">
            <h5>Abnormal labs</h5>
            {labDraft?.urgency && <AcuityBadge urgency={labDraft.urgency} />}
          </div>
          <ul className="evidence-labs">
            {abnormals.map((item, i) => {
              const name = item.analyte ?? item.name ?? "Finding";
              const flag = item.flag ?? "abnormal";
              return (
                <li key={`${name}-${i}`}>
                  <span className={`evidence-dot ${flag}`} aria-hidden="true" />
                  <span className="evidence-lab-name">{name}</span>
                  <span className="evidence-lab-value">{item.value} {item.unit ?? ""}</span>
                  <span className={`evidence-flag ${flag}`}>{flag}</span>
                </li>
              );
            })}
          </ul>
        </section>
      )}

      {redFlags.length > 0 && (
        <section className="evidence-block">
          <h5>Red flags</h5>
          <ul className="evidence-redflags">
            {redFlags.map((flag, i) => (
              <li key={`${flag}-${i}`}>{flag}</li>
            ))}
          </ul>
        </section>
      )}

      {differentials.length > 0 && (
        <section className="evidence-block">
          <h5>Top differentials</h5>
          <ol className="evidence-dx">
            {differentials.map((dx, i) => (
              <li key={`${dx.condition}-${i}`}>
                <span>{dx.condition}</span>
                <small>{dx.likelihood ?? "—"}</small>
              </li>
            ))}
          </ol>
        </section>
      )}

      {zoom && xrayPreviewUrl && (
        <div className="scan-lightbox" role="dialog" aria-label="Enlarged chest X-ray" onClick={() => setZoom(false)}>
          <img src={xrayPreviewUrl} alt="Enlarged chest X-ray" />
          <button type="button" className="scan-lightbox-close" onClick={() => setZoom(false)}>Close</button>
        </div>
      )}
    </aside>
  );
}
