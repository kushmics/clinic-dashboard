// Track A. Renders lab_triage draft: abnormals table, urgency badge, summary.
export default function LabTriagePanel({ draft }) {
  return (
    <section>
      <h3>Lab triage</h3>
      {/* TODO(Track A): abnormals table + urgency badge + clinician sign-off */}
      <pre>{JSON.stringify(draft ?? {}, null, 2)}</pre>
    </section>
  );
}
