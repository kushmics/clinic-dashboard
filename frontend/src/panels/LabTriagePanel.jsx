// Track A. Renders a lab_triage draft: urgency, abnormals (never-miss sorted),
// unassessed, normals, with cited thresholds. Draft only — clinician reviews
// and signs; nothing here is a diagnosis (that's differential_dx).
import { useState } from "react";

const URGENCY = {
  urgent: { bg: "#fdecea", fg: "#b71c1c", label: "URGENT" },
  soon: { bg: "#fff4e5", fg: "#b15c00", label: "REVIEW SOON" },
  routine: { bg: "#e8f5e9", fg: "#1b5e20", label: "ROUTINE" },
};
const FLAG = {
  critical: { bg: "#b71c1c", fg: "#fff" },
  high: { bg: "#f3d9a4", fg: "#7a4f00" },
  low: { bg: "#cfe3f3", fg: "#0b4a73" },
};

function Badge({ style, children }) {
  return (
    <span style={{ display: "inline-block", padding: "2px 8px", borderRadius: 6,
      fontSize: 12, fontWeight: 700, letterSpacing: 0.3, ...style }}>
      {children}
    </span>
  );
}

// Format the draft as a plain-text chart note the clinician can paste straight
// into the EMR — the admin-time payoff. Facts only; no severity judgement added.
function buildNote(draft) {
  const {
    abnormals = [], unassessed = [], context_used = {},
    urgency = "routine", summary = "", meta = {},
  } = draft;
  const lines = ["LAB TRIAGE — DRAFT (unsigned)", `Urgency: ${urgency.toUpperCase()}`, ""];
  if (summary) lines.push(summary, "");
  if (abnormals.length) {
    lines.push("Abnormal:");
    for (const a of abnormals) {
      const val = [a.value, a.unit].filter(Boolean).join(" ");
      lines.push(`- ${a.analyte} ${val} — ${a.note ?? a.flag}`);
    }
    lines.push("");
  }
  if (unassessed.length) {
    lines.push(`Not assessed (${unassessed.length}): `
      + unassessed.map(x => x.analyte).join(", "), "");
  }
  const ctx = [
    context_used.sex != null && `Sex ${context_used.sex}`
      + (context_used.sex_source ? ` (${context_used.sex_source})` : ""),
    context_used.age != null && `Age ${context_used.age}`
      + (context_used.age_source ? ` (${context_used.age_source})` : ""),
  ].filter(Boolean).join(" · ");
  if (ctx) lines.push(`Context: ${ctx}`);
  const src = [meta.sources?.critical?.name, meta.sources?.ranges?.name].filter(Boolean).join(", ");
  if (src) lines.push(`Thresholds: ${src}. Reference-table lookups only.`);
  return lines.join("\n").trim();
}

export default function LabTriagePanel({ draft, onSign }) {
  const [signed, setSigned] = useState(false);
  const [showNormals, setShowNormals] = useState(false);
  const [copied, setCopied] = useState(false);
  if (!draft) return null;

  async function copyNote() {
    try {
      await navigator.clipboard.writeText(buildNote(draft));
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  }

  const {
    abnormals = [], unassessed = [], normals = [], assumptions = [],
    context_used = {}, urgency = "routine", summary = "", meta = {},
  } = draft;
  const u = URGENCY[urgency] ?? URGENCY.routine;

  return (
    <section style={{ background: "#fff", border: "1px solid #e1e6eb", borderRadius: 12, padding: 20 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
        <h3 style={{ margin: 0, flex: 1 }}>Lab triage</h3>
        <Badge style={{ background: u.bg, color: u.fg, fontSize: 13 }}>{u.label}</Badge>
        <span style={{ fontSize: 12, color: "#5a6b7c" }}>draft · unsigned</span>
      </div>

      <p style={{ color: "#33475b", marginTop: 10, marginBottom: 0 }}>{summary}</p>

      {/* Context the triage ran against (decision 5: provenance is explicit). */}
      <div style={{ marginTop: 10, fontSize: 12, color: "#5a6b7c" }}>
        Sex: {context_used.sex ?? "—"}{context_used.sex_source ? ` (${context_used.sex_source})` : ""}
        {"  ·  "}Age: {context_used.age ?? "—"}{context_used.age_source ? ` (${context_used.age_source})` : ""}
        {"  ·  "}Priors: {context_used.priors_available ? "yes" : "none"}
        {meta.extraction_method ? `  ·  extracted via ${meta.extraction_method}` : ""}
      </div>

      {assumptions.length > 0 && (
        <ul style={{ background: "#fff8e1", border: "1px solid #ffe0a3", borderRadius: 8,
          padding: "8px 8px 8px 26px", marginTop: 12, fontSize: 13, color: "#7a4f00" }}>
          {assumptions.map((a, i) => <li key={i}>{a}</li>)}
        </ul>
      )}

      {/* Abnormals — never-miss sorted, each with its cited threshold. */}
      {abnormals.length > 0 && (
        <table style={{ width: "100%", borderCollapse: "collapse", marginTop: 14, fontSize: 14 }}>
          <thead>
            <tr style={{ textAlign: "left", color: "#5a6b7c", fontSize: 12 }}>
              <th style={th}>Analyte</th><th style={th}>Value</th><th style={th}>Flag</th>
              <th style={th}>Range</th><th style={th}>Source</th><th style={th}>Trend</th>
            </tr>
          </thead>
          <tbody>
            {abnormals.map((a, i) => {
              const f = FLAG[a.flag] ?? FLAG.high;
              const ts = a.threshold_source ?? {};
              return (
                <tr key={i} style={{ borderTop: "1px solid #eef1f4" }}>
                  <td style={td}>
                    <strong>{a.analyte}</strong>
                    {a.loinc && <span style={{ color: "#9aa7b4", fontSize: 11 }}> · LOINC {a.loinc}</span>}
                    <div style={{ color: "#5a6b7c", fontSize: 12 }}>{a.note}</div>
                  </td>
                  <td style={td}>{a.value} {a.unit}</td>
                  <td style={td}>
                    <Badge style={{ background: f.bg, color: f.fg }}>{a.flag}</Badge>
                    {a.provisional && <div style={{ fontSize: 11, color: "#b15c00" }}>provisional</div>}
                  </td>
                  <td style={td}>{a.reference_range ?? "—"}</td>
                  <td style={td}>
                    {ts.url
                      ? <a href={ts.url} target="_blank" rel="noreferrer">{ts.table}</a>
                      : (ts.table ?? "—")}
                    {ts.threshold != null && <div style={{ fontSize: 11, color: "#9aa7b4" }}>
                      {ts.rule} {ts.threshold}</div>}
                  </td>
                  <td style={td}>{a.delta ? a.delta.note : "—"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}

      {/* Unassessed — surfaced, never dropped (decision 9). */}
      {unassessed.length > 0 && (
        <div style={{ marginTop: 14 }}>
          <h4 style={{ margin: "0 0 6px" }}>Not assessed ({unassessed.length})</h4>
          <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13, color: "#5a6b7c" }}>
            {unassessed.map((x, i) => (
              <li key={i}><strong>{x.analyte}</strong> {x.value} {x.unit} — {x.reason}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Normals — collapsed, kept for completeness (lose no information). */}
      {normals.length > 0 && (
        <div style={{ marginTop: 14 }}>
          <button onClick={() => setShowNormals(s => !s)} style={linkBtn}>
            {showNormals ? "▾" : "▸"} {normals.length} within range
          </button>
          {showNormals && (
            <table style={{ width: "100%", borderCollapse: "collapse", marginTop: 8, fontSize: 13 }}>
              <tbody>
                {normals.map((n, i) => (
                  <tr key={i} style={{ borderTop: "1px solid #eef1f4", color: "#5a6b7c" }}>
                    <td style={td}>{n.analyte}</td>
                    <td style={td}>{n.value} {n.unit}</td>
                    <td style={td}>{n.reference_range ?? "—"}</td>
                    <td style={td}>{n.range_source}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {/* Citations footer. */}
      {meta.sources && (
        <p style={{ marginTop: 14, fontSize: 11, color: "#9aa7b4" }}>
          Thresholds: {meta.sources.critical?.name} ·{" "}
          {meta.sources.ranges?.name}. Reference-table lookups only — no model decides severity.
        </p>
      )}

      {/* Review → sign (audit flow proper is Track D; this is the panel affordance). */}
      <div style={{ marginTop: 16, paddingTop: 14, borderTop: "1px solid #eef1f4",
        display: "flex", alignItems: "center", gap: 12 }}>
        <button
          disabled={signed}
          onClick={() => { setSigned(true); onSign?.(draft); }}
          style={{ padding: "8px 16px", borderRadius: 8, border: "none", cursor: signed ? "default" : "pointer",
            background: signed ? "#cfd8dc" : "#1b5e20", color: "#fff", fontWeight: 600 }}>
          {signed ? "✓ Reviewed & signed" : "Review & sign"}
        </button>
        <button
          onClick={copyNote}
          style={{ padding: "8px 16px", borderRadius: 8, cursor: "pointer",
            background: "#fff", color: "#0b4a73", border: "1px solid #0b4a73", fontWeight: 600 }}>
          {copied ? "✓ Copied" : "Copy as note"}
        </button>
        <span style={{ fontSize: 12, color: "#5a6b7c" }}>
          Clinician confirms the draft. Nothing is auto-signed.
        </span>
      </div>
    </section>
  );
}

const th = { padding: "4px 8px" };
const td = { padding: "8px 8px", verticalAlign: "top" };
const linkBtn = { background: "none", border: "none", color: "#0b4a73", cursor: "pointer",
  padding: 0, fontSize: 13, fontWeight: 600 };
