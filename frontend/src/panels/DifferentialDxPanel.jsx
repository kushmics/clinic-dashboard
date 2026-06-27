// Track C. Renders differential_dx draft: ranked differentials + Exa-cited next steps.
export default function DifferentialDxPanel({ draft }) {
  const differentials = draft?.differentials ?? [];
  const redFlags = draft?.red_flags ?? [];

  return (
    <section className="support-panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Track C draft</p>
          <h3>Differential diagnosis</h3>
        </div>
        <span className="sign-state draft">Review</span>
      </div>

      {redFlags.length > 0 && (
        <div style={{ background: "#fdecea", border: "1px solid #f5c2c7", color: "#842029",
          borderRadius: 8, padding: 10, marginBottom: 14, fontSize: 14 }}>
          <strong>Red flags:</strong> {redFlags.join("; ")}
        </div>
      )}

      {differentials.length === 0 && (
        <p style={{ color: "#5a6b7c" }}>No ranked differentials yet.</p>
      )}

      {differentials.map((dx, i) => (
        <article key={i} style={{ borderTop: i ? "1px solid #eef1f4" : "none", paddingTop: i ? 14 : 0, marginTop: i ? 14 : 0 }}>
          <div style={{ display: "flex", gap: 8, alignItems: "baseline", flexWrap: "wrap" }}>
            <strong>{i + 1}. {dx.condition}</strong>
            <span style={{ fontSize: 12, color: "#5a6b7c", textTransform: "uppercase" }}>{dx.likelihood}</span>
          </div>

          {dx.rationale && (
            <p style={{ margin: "6px 0", color: "#33475b", fontSize: 13 }}>{dx.rationale}</p>
          )}

          {dx.supporting?.length > 0 && (
            <p style={{ margin: "6px 0", color: "#33475b", fontSize: 13 }}>
              Evidence in case: {dx.supporting.join("; ")}
            </p>
          )}

          {dx.next_steps?.length > 0 && (
            <ul style={{ margin: "8px 0 0", paddingLeft: 18, fontSize: 13 }}>
              {dx.next_steps.map((step, j) => {
                const action = typeof step === "string" ? step : step.action;
                const citation = typeof step === "string" ? null : step.citation;
                return (
                  <li key={j} style={{ marginBottom: 6 }}>
                    {action}
                    {citation?.url ? (
                      <span style={{ color: "#5a6b7c" }}> — <a href={citation.url} target="_blank" rel="noreferrer">{citation.title || "source"}</a></span>
                    ) : (
                      <span style={{ color: "#9aa7b4" }}> — citation pending</span>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </article>
      ))}
    </section>
  );
}
