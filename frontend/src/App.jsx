import { useState } from "react";

// Minimal scaffold: upload a file, hit the backend, show the draft.
// Real dashboard (abnormal flags, urgency, differentials, referral letter)
// gets built on top of these stubs once the AI approach is chosen.
export default function App() {
  const [status, setStatus] = useState("");

  async function handleUpload(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    setStatus("Uploading…");
    const body = new FormData();
    body.append("file", file);
    try {
      const res = await fetch("/api/ingestion/upload", { method: "POST", body });
      setStatus(JSON.stringify(await res.json(), null, 2));
    } catch (err) {
      setStatus("Error: " + err.message);
    }
  }

  return (
    <main style={{ maxWidth: 820, margin: "0 auto", padding: 24 }}>
      <h1>Clinic Dashboard</h1>
      <p style={{ color: "#5a6b7c" }}>
        First-pass clinical decision support — AI drafts, a clinician reviews & signs.
      </p>
      <section style={{ background: "#fff", border: "1px solid #e1e6eb", borderRadius: 12, padding: 20 }}>
        <h2 style={{ marginTop: 0 }}>Upload a lab result, scan, or case description</h2>
        <input type="file" onChange={handleUpload} />
        {status && (
          <pre style={{ marginTop: 16, background: "#f6f8fa", padding: 12, borderRadius: 8, overflow: "auto" }}>
            {status}
          </pre>
        )}
      </section>
    </main>
  );
}
