// Track D. Renders referral_letter draft: editable letter + sign & export.
export default function ReferralLetterPanel({ draft }) {
  return (
    <section>
      <h3>Referral letter</h3>
      {/* TODO(Track D): editable Markdown letter, sign-off, one-click export */}
      <pre>{JSON.stringify(draft ?? {}, null, 2)}</pre>
    </section>
  );
}
