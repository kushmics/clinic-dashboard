// Track C. Renders differential_dx draft: ranked differentials + next steps.
export default function DifferentialDxPanel({ draft }) {
  return (
    <section>
      <h3>Differential diagnosis</h3>
      {/* TODO(Track C): ranked list, evidence, next steps, red-flag banner */}
      <pre>{JSON.stringify(draft ?? {}, null, 2)}</pre>
    </section>
  );
}
