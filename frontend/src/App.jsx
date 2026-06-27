import { useMemo, useState } from "react";
import DifferentialDxPanel from "./panels/DifferentialDxPanel.jsx";
import ImagingReportPanel from "./panels/ImagingReportPanel.jsx";
import LabTriagePanel from "./panels/LabTriagePanel.jsx";
import ReferralLetterPanel from "./panels/ReferralLetterPanel.jsx";

const demoCase = {
  patient: {
    id: "PX-1048",
    name: "Aisha Tan",
    age: 58,
    sex: "F",
    summary:
      "58-year-old woman with 2 weeks of fatigue, exertional dyspnea, intermittent chest tightness, and poorly controlled diabetes.",
  },
  lab_triage: {
    urgency: "urgent",
    summary: "Microcytic anemia with elevated inflammatory markers and poor glycemic control.",
    abnormals: [
      { name: "Hemoglobin", value: "8.9", unit: "g/dL", flag: "low", urgency: "urgent" },
      { name: "MCV", value: "72", unit: "fL", flag: "low", urgency: "soon" },
      { name: "CRP", value: "42", unit: "mg/L", flag: "high", urgency: "soon" },
      { name: "HbA1c", value: "9.4", unit: "%", flag: "high", urgency: "soon" },
    ],
  },
  imaging_report: {
    urgency: "soon",
    findings: [
      "Chest X-ray draft notes mild cardiomegaly without focal consolidation.",
      "No pleural effusion or pneumothorax identified on preliminary review.",
    ],
    impression: "Mild cardiomegaly. Correlate clinically for anemia-related symptoms and cardiac risk.",
  },
  differential_dx: {
    red_flags: ["Symptomatic anemia with chest tightness", "Diabetes with elevated inflammatory markers"],
    differentials: [
      { condition: "Iron deficiency anemia", rationale: "Low hemoglobin with microcytosis." },
      { condition: "Anemia of chronic inflammation", rationale: "Raised CRP and persistent fatigue." },
      { condition: "Cardiac ischemia risk", rationale: "Chest tightness in a diabetic patient requires exclusion." },
    ],
  },
};

const initialAudit = [
  { actor: "System", action: "Case opened", time: "09:12", detail: "Synthetic demo case loaded" },
  { actor: "AI", action: "Drafts generated", time: "09:13", detail: "Lab, imaging, differential, and referral drafts ready for review" },
];

export default function App() {
  const [status, setStatus] = useState("");
  const [caseData, setCaseData] = useState(demoCase);
  const [activePanel, setActivePanel] = useState("referral");
  const [auditLog, setAuditLog] = useState(initialAudit);
  const [signedLetters, setSignedLetters] = useState([]);

  const urgency = caseData.lab_triage.urgency ?? caseData.imaging_report.urgency ?? "routine";
  const patientLine = `${caseData.patient.name} / ${caseData.patient.age}${caseData.patient.sex} / ${caseData.patient.id}`;

  const referralDraft = useMemo(
    () => ({
      recipient_specialty: "Internal Medicine",
      reason_for_referral: "Symptomatic anemia and cardiometabolic risk review",
      clinical_summary: caseData.patient.summary,
      relevant_findings: [
        ...caseData.lab_triage.abnormals.map(
          (item) => `${item.name}: ${item.value} ${item.unit} (${item.flag})`
        ),
        ...caseData.imaging_report.findings,
        ...caseData.differential_dx.red_flags,
      ],
      letter_markdown: `Dear Internal Medicine Team,

Re: ${caseData.patient.name}

I am referring ${caseData.patient.name} for assessment of symptomatic anemia and cardiometabolic risk.

Clinical summary:
${caseData.patient.summary}

Relevant findings:
${caseData.lab_triage.abnormals
  .map((item) => `- ${item.name}: ${item.value} ${item.unit} (${item.flag})`)
  .join("\n")}
- ${caseData.imaging_report.impression}

Provisional considerations:
${caseData.differential_dx.differentials
  .map((item) => `- ${item.condition}: ${item.rationale}`)
  .join("\n")}

Please assess and advise on further management.

Regards,
Clinician reviewer`,
    }),
    [caseData]
  );

  async function handleUpload(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    setStatus("Uploading...");
    const body = new FormData();
    body.append("file", file);
    try {
      const res = await fetch("/api/ingestion/upload", { method: "POST", body });
      const result = await res.json();
      setStatus(`${result.filename} uploaded`);
      addAudit("Staff", "Uploaded source file", result.filename);
    } catch (err) {
      setStatus("Error: " + err.message);
    }
  }

  function addAudit(actor, action, detail) {
    const now = new Date();
    setAuditLog((items) => [
      {
        actor,
        action,
        detail,
        time: now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
      },
      ...items,
    ]);
  }

  function handleSignedLetter(letter) {
    setSignedLetters((items) => [letter, ...items]);
    addAudit(letter.reviewer, "Signed referral letter", `${letter.specialty} referral locked for export`);
  }

  const panels = {
    lab: <LabTriagePanel draft={caseData.lab_triage} />,
    imaging: <ImagingReportPanel draft={caseData.imaging_report} />,
    dx: <DifferentialDxPanel draft={caseData.differential_dx} />,
    referral: (
      <ReferralLetterPanel
        draft={referralDraft}
        patient={caseData.patient}
        signedLetters={signedLetters}
        onAudit={addAudit}
        onSigned={handleSignedLetter}
      />
    ),
  };

  return (
    <main className="app-shell">
      <aside className="sidebar" aria-label="Case workflow">
        <div>
          <p className="eyebrow">Clinic Dashboard</p>
          <h1>First-pass review</h1>
          <p className="subtle">AI drafts stay unsigned until a clinician reviews and locks them.</p>
        </div>

        <label className="upload-button">
          <span>Upload source</span>
          <input type="file" onChange={handleUpload} />
        </label>
        {status && <p className="upload-status">{status}</p>}

        <nav className="workflow-tabs" aria-label="Draft panels">
          {[
            ["lab", "Labs"],
            ["imaging", "Imaging"],
            ["dx", "Differentials"],
            ["referral", "Referral"],
          ].map(([id, label]) => (
            <button
              key={id}
              className={activePanel === id ? "active" : ""}
              onClick={() => setActivePanel(id)}
              type="button"
            >
              {label}
            </button>
          ))}
        </nav>
      </aside>

      <section className="workspace">
        <header className="case-header">
          <div>
            <p className="eyebrow">Active case</p>
            <h2>{patientLine}</h2>
            <p>{caseData.patient.summary}</p>
          </div>
          <div className={`urgency-badge ${urgency}`}>{urgency}</div>
        </header>

        <div className="dashboard-grid">
          <section className="review-surface">{panels[activePanel]}</section>
          <aside className="audit-panel" aria-label="Audit trail">
            <div className="audit-heading">
              <h3>Audit trail</h3>
              <span>{auditLog.length} events</span>
            </div>
            <ol className="audit-list">
              {auditLog.map((event, index) => (
                <li key={`${event.time}-${event.action}-${index}`}>
                  <time>{event.time}</time>
                  <strong>{event.action}</strong>
                  <span>{event.actor}</span>
                  <p>{event.detail}</p>
                </li>
              ))}
            </ol>
          </aside>
        </div>
      </section>
    </main>
  );
}
