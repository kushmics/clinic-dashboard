// Track B. Renders imaging_report draft: scan viewer + ROI overlay + impression.
export default function ImagingReportPanel({ draft }) {
  return (
    <section>
      <h3>Imaging preliminary report</h3>
      {/* TODO(Track B): scan viewer, ROI boxes, structured report, sign-off */}
      <pre>{JSON.stringify(draft ?? {}, null, 2)}</pre>
    </section>
  );
}
