// Track A. Renders lab_triage draft: abnormals table, urgency badge, summary.
export default function LabTriagePanel({ draft }) {
  const abnormals = draft?.abnormals ?? [];

  return (
    <section className="support-panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Track A draft</p>
          <h3>Lab triage</h3>
        </div>
        <span className={`urgency-badge ${draft?.urgency ?? "routine"}`}>{draft?.urgency ?? "routine"}</span>
      </div>
      <p>{draft?.summary || "No lab triage summary yet."}</p>
      <table>
        <thead>
          <tr>
            <th>Analyte</th>
            <th>Value</th>
            <th>Flag</th>
            <th>Urgency</th>
          </tr>
        </thead>
        <tbody>
          {abnormals.map((item) => (
            <tr key={item.name}>
              <td>{item.name}</td>
              <td>{item.value} {item.unit}</td>
              <td>{item.flag}</td>
              <td>{item.urgency}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
