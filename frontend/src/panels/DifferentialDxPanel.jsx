// Track C. Renders differential_dx draft: ranked differentials + next steps.
export default function DifferentialDxPanel({ draft }) {
  return (
    <section className="support-panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Track C draft</p>
          <h3>Differential diagnosis</h3>
        </div>
        <span className="sign-state draft">Review</span>
      </div>
      <div className="red-flags">
        {(draft?.red_flags ?? []).map((flag) => (
          <span key={flag}>{flag}</span>
        ))}
      </div>
      <ol className="dx-list">
        {(draft?.differentials ?? []).map((item) => (
          <li key={item.condition}>
            <strong>{item.condition}</strong>
            <p>{item.rationale}</p>
          </li>
        ))}
      </ol>
    </section>
  );
}
