import { useState } from "react";
import LabTriagePanel from "./panels/LabTriagePanel.jsx";

// Lab-triage vertical: upload a report, the backend extracts + triages against
// cited tables, and the panel renders the draft for clinician review & sign.
// The full 4-panel shell is Track D.
export default function App() {
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [sex, setSex] = useState("");
  const [age, setAge] = useState("");

  async function handleUpload(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    setBusy(true); setError(""); setResult(null);
    const body = new FormData();
    body.append("file", file);
    body.append("skill", "lab_triage");
    if (sex) body.append("sex", sex);
    if (age) body.append("age", age);
    try {
      const res = await fetch("/api/ingestion/upload", { method: "POST", body });
      const json = await res.json();
      setResult(json);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main style={{ maxWidth: 880, margin: "0 auto", padding: 24 }}>
      <h1>Clinic Dashboard</h1>
      <p style={{ color: "#5a6b7c" }}>
        First-pass clinical decision support — AI drafts, a clinician reviews & signs.
      </p>

      <section style={{ background: "#fff", border: "1px solid #e1e6eb", borderRadius: 12, padding: 20, marginBottom: 16 }}>
        <h2 style={{ marginTop: 0 }}>Upload a lab result</h2>
        <p style={{ color: "#5a6b7c", marginTop: 0, fontSize: 13 }}>
          PDF, photo, or text. Sex/age auto-fill from the report when present —
          override here if it doesn't.
        </p>
        <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap", marginBottom: 12 }}>
          <label style={lbl}>Sex
            <select value={sex} onChange={e => setSex(e.target.value)} style={inp}>
              <option value="">auto</option>
              <option value="female">female</option>
              <option value="male">male</option>
            </select>
          </label>
          <label style={lbl}>Age
            <input type="number" min="0" max="120" value={age}
              onChange={e => setAge(e.target.value)} placeholder="auto" style={{ ...inp, width: 80 }} />
          </label>
        </div>
        <input type="file" onChange={handleUpload} disabled={busy} />
        {busy && <span style={{ marginLeft: 10, color: "#5a6b7c" }}>Processing…</span>}
        {error && <p style={{ color: "#b71c1c" }}>Error: {error}</p>}
      </section>

      {result?.result?.draft && (
        <LabTriagePanel draft={result.result.draft} />
      )}
      {result && !result?.result?.draft && (
        <pre style={{ background: "#f6f8fa", padding: 12, borderRadius: 8, overflow: "auto" }}>
          {JSON.stringify(result, null, 2)}
        </pre>
      )}
    </main>
  );
}

const lbl = { display: "flex", flexDirection: "column", gap: 4, fontSize: 12, color: "#5a6b7c" };
const inp = { padding: "6px 8px", borderRadius: 6, border: "1px solid #cfd8dc" };
