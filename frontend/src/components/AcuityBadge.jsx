import { ACUITY } from "../acuity.js";

// One consistent acuity pill used across the app: "L1 · Immediate" etc.
// `size="lg"` for headers, default for inline chips.
export default function AcuityBadge({ urgency, size, className = "" }) {
  const info = ACUITY[urgency];
  if (!info) return null;
  return (
    <span
      className={`acuity ${urgency}${size === "lg" ? " lg" : ""} ${className}`.trim()}
      title={info.note}
    >
      <b>L{info.level}</b>
      {info.label}
    </span>
  );
}
