// Shared 5-level clinical acuity scale (mirrors backend app/acuity.py).
// Slug is the wire value; the UI maps it to a level number, label, and colour.
export const ACUITY = {
  immediate: { level: 1, label: "Immediate", note: "Life-threatening — immediate intervention" },
  emergency: { level: 2, label: "Emergency", note: "High-risk — target ≤ 10 min" },
  urgent: { level: 3, label: "Urgent", note: "Serious — target ~ 60 min" },
  "semi-urgent": { level: 4, label: "Semi-urgent", note: "Treat when time permits" },
  "non-urgent": { level: 5, label: "Non-urgent", note: "Minor or stable" },
};

export function acuityInfo(slug) {
  return ACUITY[slug] ?? null;
}

export function acuityRank(slug) {
  return ACUITY[slug]?.level ?? 99;
}

// Most-acute (lowest level number) slug from a list, or null.
export function mostAcute(slugs) {
  let best = null;
  for (const s of slugs) {
    if (s && ACUITY[s] && (best === null || ACUITY[s].level < ACUITY[best].level)) best = s;
  }
  return best;
}
