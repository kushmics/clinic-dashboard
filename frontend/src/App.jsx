import { useEffect, useMemo, useState } from "react";
import ImagingReportPanel from "./panels/ImagingReportPanel.jsx";
import LabTriagePanel from "./panels/LabTriagePanel.jsx";
import ReferralLetterPanel from "./panels/ReferralLetterPanel.jsx";

const INCOMING_SUMMARY = "New patient record pending CV identification and clinical source scan.";

function createEmptyCase(index = 1) {
  const id = `INCOMING-${String(index).padStart(3, "0")}`;
  return {
    patient: {
      id,
      name: "Incoming patient",
      age: null,
      sex: "",
      summary: INCOMING_SUMMARY,
    },
    lab_triage: {
      urgency: "routine",
      summary: "No clinical source scanned yet.",
      abnormals: [],
      normals: [],
      unassessed: [],
    },
    imaging_report: {
      urgency: "routine",
      findings: [],
      impression: "No imaging study uploaded yet.",
      possible_diagnoses: [],
      limitations: [],
    },
    differential_dx: {
      red_flags: [],
      differentials: [],
    },
  };
}

function createIncomingPatient(index = 1) {
  const caseData = createEmptyCase(index);
  return {
    id: caseData.patient.id,
    status: "incoming",
    lastSeen: "Awaiting ID",
    caseData,
    records: [],
  };
}

const initialPatients = [createIncomingPatient(1)];

const initialAudit = [
  { actor: "System", action: "Workspace opened", time: "--:--", detail: "Ready for incoming patient intake" },
];

const workflowStages = [
  { id: "select", label: "Select patient", panel: "patients", status: "done" },
  { id: "upload", label: "Scan record", panel: "upload", status: "done" },
  { id: "review", label: "Review", panel: "lab", status: "active" },
  { id: "sign", label: "Sign", panel: "referral", status: "waiting" },
];

const reportSections = [
  { id: "patients", label: "Patients", detail: "Library and incoming" },
  { id: "upload", label: "Record intake", detail: "Scan source files" },
  { id: "lab", label: "Lab triage", detail: "4 abnormal flags" },
  { id: "imaging", label: "Imaging review", detail: "X-ray, CT, MRI" },
  { id: "referral", label: "Referral letter", detail: "Review and sign" },
];

const AUTH_TOKEN_STORAGE_KEY = "clinic-dashboard-auth-token";
const DEMO_ACCESS_TOKEN = "clinic-demo-token";

function normalizeAccessToken(token) {
  const trimmed = token.trim();
  return trimmed.toLowerCase() === "clinic demo token" ? DEMO_ACCESS_TOKEN : trimmed;
}

export default function App() {
  const [patients, setPatients] = useState(initialPatients);
  const [activePatientId, setActivePatientId] = useState(initialPatients[0].id);
  const [status, setStatus] = useState("");
  const [caseData, setCaseData] = useState(initialPatients[0].caseData);
  const [activePanel, setActivePanel] = useState("patients");
  const [activeStage, setActiveStage] = useState("select");
  const [auditLog, setAuditLog] = useState(initialAudit);
  const [signedLetters, setSignedLetters] = useState([]);
  const [sentReferrals, setSentReferrals] = useState([]);
  const [generatedReferralDraft, setGeneratedReferralDraft] = useState(null);
  const [isGeneratingReferral, setIsGeneratingReferral] = useState(false);
  const [generatedImagingDraft, setGeneratedImagingDraft] = useState(null);
  const [xrayPreviewUrl, setXrayPreviewUrl] = useState("");
  const [xrayFile, setXrayFile] = useState(null);
  const [isAnalyzingXray, setIsAnalyzingXray] = useState(false);
  const [authToken, setAuthToken] = useState(() => localStorage.getItem(AUTH_TOKEN_STORAGE_KEY) ?? "");
  const [authError, setAuthError] = useState("");
  const [authRequired, setAuthRequired] = useState(true);
  const [isCheckingAuth, setIsCheckingAuth] = useState(true);
  const [generatedLabDraft, setGeneratedLabDraft] = useState(null);
  const [patientDocumentDraft, setPatientDocumentDraft] = useState(null);
  const [patientDocumentPreviewUrl, setPatientDocumentPreviewUrl] = useState("");
  const [patientDocumentFileName, setPatientDocumentFileName] = useState("");
  const [isExtractingPatientDocument, setIsExtractingPatientDocument] = useState(false);
  const [sourceUploadMode, setSourceUploadMode] = useState("clinical");

  const activeLabDraft = generatedLabDraft ?? caseData.lab_triage;
  const activeImagingDraft = generatedImagingDraft ?? caseData.imaging_report;
  const urgency = activeLabDraft.urgency ?? activeImagingDraft.urgency ?? "routine";
  const patientLine = `${caseData.patient.name} / ${formatPatientProfile(caseData.patient)} / ${caseData.patient.id}`;
  const activePatientRecord = patients.find((patient) => patient.id === activePatientId) ?? patients[0];
  const activeRecords = activePatientRecord?.records ?? [];
  const abnormalCount = activeLabDraft.abnormals?.length ?? 0;
  const dynamicReportSections = reportSections.map((section) => {
    if (section.id === "lab") return { ...section, detail: `${abnormalCount} abnormal flags` };
    return section;
  });

  const referralDraft = useMemo(
    () => ({
      recipient_specialty: "Internal Medicine",
      reason_for_referral: activeLabDraft.summary || activeImagingDraft.impression || "Specialist review requested",
      clinical_summary: caseData.patient.summary,
      relevant_findings: [
        ...(activeLabDraft.abnormals ?? []).map(
          (item) => `${item.name ?? item.analyte}: ${item.value} ${item.unit ?? ""} (${item.flag})`
        ),
        ...(activeImagingDraft.findings ?? []),
      ],
      letter_markdown: `Dear Internal Medicine Team,

Re: ${caseData.patient.name}

I am referring ${caseData.patient.name} for specialist review.

Clinical summary:
${caseData.patient.summary}

Relevant findings:
${formatReferralFindings(activeLabDraft, activeImagingDraft)}

Please assess and advise on further management.

Regards,
Clinician reviewer`,
    }),
    [caseData, activeImagingDraft, activeLabDraft]
  );

  const activeReferralDraft = generatedReferralDraft ?? referralDraft;

  useEffect(() => {
    let isMounted = true;

    async function checkAuthStatus() {
      try {
        const res = await fetch("/api/auth/status");
        if (!res.ok) throw new Error(`Auth status failed (${res.status})`);
        const result = await res.json();
        if (!isMounted) return;
        setAuthRequired(Boolean(result.enabled));
        if (!result.enabled) {
          setAuthError("");
          saveAuthToken("");
        }
      } catch (err) {
        if (isMounted) {
          setAuthRequired(true);
        }
      } finally {
        if (isMounted) {
          setIsCheckingAuth(false);
        }
      }
    }

    checkAuthStatus();

    return () => {
      isMounted = false;
    };
  }, []);

  useEffect(() => {
    return () => {
      if (patientDocumentPreviewUrl) URL.revokeObjectURL(patientDocumentPreviewUrl);
    };
  }, [patientDocumentPreviewUrl]);

  function saveAuthToken(token) {
    if (token) {
      localStorage.setItem(AUTH_TOKEN_STORAGE_KEY, token);
    } else {
      localStorage.removeItem(AUTH_TOKEN_STORAGE_KEY);
    }
    setAuthToken(token);
  }

  async function authFetch(url, options = {}) {
    const headers = new Headers(options.headers);
    if (authRequired) {
      headers.set("Authorization", `Bearer ${authToken}`);
    }

    const res = await fetch(url, { ...options, headers });
    if (res.status === 401 || res.status === 403) {
      setAuthError("Session token was rejected. Sign in again.");
      saveAuthToken("");
    }
    return res;
  }

  async function handleSignIn(token) {
    setAuthError("");
    const trimmedToken = normalizeAccessToken(token);
    if (!trimmedToken) {
      setAuthError("Enter an access token.");
      return;
    }

    const res = await fetch("/api/engine/skills", {
      headers: { Authorization: `Bearer ${trimmedToken}` },
    });

    if (!res.ok) {
      setAuthError(res.status === 401 || res.status === 403 ? "Invalid access token." : `Auth check failed (${res.status}).`);
      return;
    }

    saveAuthToken(trimmedToken);
    addAudit("Staff", "Authenticated session", "Local access token verified");
  }

  function handleSignOut() {
    saveAuthToken("");
    setAuthError("");
    addAudit("Staff", "Signed out", "Local access token cleared");
  }

  function syncActiveCase(nextCase) {
    setCaseData(nextCase);
    setPatients((items) =>
      items.map((patient) =>
        patient.id === activePatientId ? { ...patient, id: nextCase.patient.id, caseData: nextCase } : patient
      )
    );
    setActivePatientId(nextCase.patient.id);
  }

  function updateActivePatientRecord(recordId, updates) {
    setPatients((items) =>
      items.map((patient) =>
        patient.id === activePatientId
          ? {
              ...patient,
              records: patient.records.map((record) =>
                record.id === recordId ? { ...record, ...updates } : record
              ),
            }
          : patient
      )
    );
  }

  function addActivePatientRecord(record) {
    setPatients((items) =>
      items.map((patient) =>
        patient.id === activePatientId
          ? { ...patient, records: [record, ...patient.records], status: "incoming", lastSeen: "Today" }
          : patient
      )
    );
  }

  function handleCreateIncomingPatient() {
    const nextPatient = createIncomingPatient(patients.length + 1);
    setPatients((items) => [nextPatient, ...items]);
    setActivePatientId(nextPatient.id);
    setCaseData(nextPatient.caseData);
    setGeneratedLabDraft(null);
    setGeneratedImagingDraft(null);
    setGeneratedReferralDraft(null);
    setPatientDocumentDraft(null);
    setPatientDocumentFileName("");
    if (patientDocumentPreviewUrl) URL.revokeObjectURL(patientDocumentPreviewUrl);
    setPatientDocumentPreviewUrl("");
    setStatus("");
    setActivePanel("upload");
    setActiveStage("upload");
    addAudit("Staff", "Opened incoming patient", `${nextPatient.id} ready for intake`);
  }

  function handleSelectPatient(patientId) {
    const selected = patients.find((patient) => patient.id === patientId);
    if (!selected) return;
    setActivePatientId(patientId);
    setCaseData(selected.caseData);
    setGeneratedLabDraft(null);
    setGeneratedImagingDraft(null);
    setGeneratedReferralDraft(null);
    setPatientDocumentDraft(null);
    setPatientDocumentFileName("");
    setStatus("");
    if (patientDocumentPreviewUrl) URL.revokeObjectURL(patientDocumentPreviewUrl);
    setPatientDocumentPreviewUrl("");
    setActivePanel("upload");
    setActiveStage("upload");
    addAudit("Staff", "Selected patient", `${selected.caseData.patient.id} opened from worklist`);
  }

  async function handleUpload(e) {
    const file = e.target.files?.[0];
    e.target.value = "";
    await processSourceUpload(file);
  }

  async function processSourceUpload(file) {
    if (!file) return;
    const recordId = `rec-${Date.now()}`;
    const category = sourceUploadMode === "imaging" ? "Imaging study" : "Clinical record";
    const uploadedRecord = {
      id: recordId,
      category,
      name: file.name,
      status: "Processing",
      time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    };
    addActivePatientRecord(uploadedRecord);
    setStatus(`Processing ${file.name}...`);

    if (sourceUploadMode === "imaging") {
      await analyzeImagingUpload(file, recordId);
      return;
    }

    const body = new FormData();
    body.append("file", file);
    body.append("skill", "lab_triage");
    try {
      const res = await authFetch("/api/ingestion/upload", { method: "POST", body });
      if (!res.ok) throw new Error(`Upload failed (${res.status})`);
      const result = await res.json();
      let nextLabDraft = null;
      if (result.result?.draft) {
        nextLabDraft = result.result.draft;
        setGeneratedLabDraft(nextLabDraft);
        setGeneratedReferralDraft(null);
        syncActiveCase({ ...caseData, lab_triage: nextLabDraft });
        setActivePanel("lab");
        setActiveStage("review");
        updateActivePatientRecord(recordId, { status: "AI draft ready", result: "Lab triage" });
      } else {
        updateActivePatientRecord(recordId, { status: "Stored", result: "No AI draft" });
      }
      setStatus(`${result.filename} uploaded`);
      addAudit("Staff", "Scanned clinical record", `${result.filename} attached to ${caseData.patient.name}`);
    } catch (err) {
      setStatus("Error: " + err.message);
      updateActivePatientRecord(recordId, { status: "Needs review", result: err.message });
      addAudit("System", "Clinical record scan failed", err.message);
    }
  }

  async function handlePatientDocumentUpload(e) {
    const file = e.target.files?.[0];
    e.target.value = "";
    await processPatientDocumentUpload(file);
  }

  async function processPatientDocumentUpload(file) {
    if (!file) return;
    setPatientDocumentFileName(file.name);
    setPatientDocumentDraft(null);
    if (patientDocumentPreviewUrl) URL.revokeObjectURL(patientDocumentPreviewUrl);
    setPatientDocumentPreviewUrl(file.type.startsWith("image/") ? URL.createObjectURL(file) : "");
    setIsExtractingPatientDocument(true);

    const body = new FormData();
    body.append("file", file);
    try {
      const res = await authFetch("/api/ingestion/patient-document", { method: "POST", body });
      if (!res.ok) throw new Error(`Patient document extraction failed (${res.status})`);
      const result = await res.json();
      setPatientDocumentDraft(result.draft);
      addAudit("AI", "Extracted patient details", "Patient document fields ready for staff review");
    } catch (err) {
      setPatientDocumentDraft(createEmptyPatientDocumentDraft(err.message));
      addAudit("System", "Patient detail extraction failed", err.message);
    } finally {
      setIsExtractingPatientDocument(false);
    }
  }

  function handleApplyPatientDetails(draft) {
    const nextPatient = {
      ...caseData.patient,
      name: draft.patient_name || caseData.patient.name,
      id: draft.patient_id || caseData.patient.id,
      age: draft.age ?? caseData.patient.age,
      sex: normalizeSex(draft.sex) || caseData.patient.sex,
    };
    const nextCase = {
      ...caseData,
      patient: {
        ...nextPatient,
        summary:
          caseData.patient.summary === INCOMING_SUMMARY
            ? "Patient record opened from incoming intake. Clinical summary pending source review."
            : caseData.patient.summary,
      },
    };
    syncActiveCase(nextCase);
    setGeneratedReferralDraft(null);
    addAudit("Staff", "Applied patient details", "Reviewed CV extraction and updated active case header");
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

  function handleSentReferral(referral) {
    setSentReferrals((items) => [referral, ...items]);
    addAudit("Workato", "Referral workflow sent", `${referral.specialty} package routed to specialist clinic`);
  }

  async function handleGenerateReferral() {
    setIsGeneratingReferral(true);
    try {
      const res = await authFetch("/api/engine/run/referral_letter", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text: caseData.patient.summary,
          context: {
            patient: caseData.patient,
            lab_triage: activeLabDraft,
            imaging_report: activeImagingDraft,
            differential_dx: caseData.differential_dx,
            recipient_specialty: "Internal Medicine",
            reason_for_referral: activeLabDraft.summary || activeImagingDraft.impression || "Specialist review requested",
          },
        }),
      });
      if (!res.ok) throw new Error(`Referral generation failed (${res.status})`);
      const result = await res.json();
      setGeneratedReferralDraft(result.draft);
      setActivePanel("referral");
      setActiveStage("sign");
      if (result.draft?.generation_note) {
        addAudit("System", "Referral generation used fallback", result.draft.generation_note);
      } else {
        addAudit("AI", "Generated referral draft", "OpenAI-backed referral draft ready for clinician review");
      }
    } catch (err) {
      addAudit("System", "Referral generation failed", err.message);
    } finally {
      setIsGeneratingReferral(false);
    }
  }

  function handleImagingSelect(file) {
    setXrayFile(file);
    setGeneratedImagingDraft(null);
    setGeneratedReferralDraft(null);
    if (xrayPreviewUrl) URL.revokeObjectURL(xrayPreviewUrl);
    setXrayPreviewUrl(file.type.startsWith("image/") ? URL.createObjectURL(file) : "");
    setActivePanel("imaging");
    setActiveStage("review");
    addAudit("Staff", "Selected imaging study", file.name);
  }

  async function analyzeImagingUpload(file = xrayFile, recordId = null) {
    if (!file) return;
    setIsAnalyzingXray(true);
    setXrayFile(file);
    if (file.type.startsWith("image/")) {
      if (xrayPreviewUrl) URL.revokeObjectURL(xrayPreviewUrl);
      setXrayPreviewUrl(URL.createObjectURL(file));
    } else {
      setXrayPreviewUrl("");
    }
    const body = new FormData();
    body.append("file", file);
    try {
      const res = await authFetch("/api/imaging/analyze-upload", { method: "POST", body });
      if (!res.ok) throw new Error(`Imaging analysis failed (${res.status})`);
      const result = await res.json();
      const nextImagingDraft = result.draft;
      setGeneratedImagingDraft(nextImagingDraft);
      setGeneratedReferralDraft(null);
      syncActiveCase({ ...caseData, imaging_report: nextImagingDraft });
      setActivePanel("imaging");
      setActiveStage("review");
      if (recordId) updateActivePatientRecord(recordId, { status: "AI draft ready", result: nextImagingDraft.modality ?? "Imaging" });
      if (result.draft?.generation_note) {
        addAudit("System", "Imaging generation used fallback", result.draft.generation_note);
      } else {
        addAudit("AI", "Generated imaging draft", "Preliminary imaging read ready for clinician review");
      }
    } catch (err) {
      addAudit("System", "Imaging analysis failed", err.message);
      if (recordId) updateActivePatientRecord(recordId, { status: "Needs review", result: err.message });
    } finally {
      setIsAnalyzingXray(false);
    }
  }

  function goToStage(stage) {
    setActiveStage(stage.id);
    setActivePanel(stage.panel);
  }

  function goToPanel(panel) {
    setActivePanel(panel);
    if (panel === "patients") setActiveStage("select");
    if (panel === "upload") setActiveStage("upload");
    if (panel === "referral") setActiveStage("sign");
    if (panel === "lab" || panel === "imaging") setActiveStage("review");
  }

  const panels = {
    patients: (
      <PatientLibraryPanel
        activePatientId={activePatientId}
        onCreateIncomingPatient={handleCreateIncomingPatient}
        onSelectPatient={handleSelectPatient}
        patients={patients}
      />
    ),
    upload: (
      <CaseIntakePanel
        records={activeRecords}
        patient={caseData.patient}
        status={status}
        onUpload={handleUpload}
        onSourceFile={processSourceUpload}
        urgency={urgency}
        sourceUploadMode={sourceUploadMode}
        onSourceUploadModeChange={setSourceUploadMode}
        patientDocumentDraft={patientDocumentDraft}
        patientDocumentFileName={patientDocumentFileName}
        patientDocumentPreviewUrl={patientDocumentPreviewUrl}
        isExtractingPatientDocument={isExtractingPatientDocument}
        onPatientDocumentUpload={handlePatientDocumentUpload}
        onPatientDocumentFile={processPatientDocumentUpload}
        onApplyPatientDetails={handleApplyPatientDetails}
      />
    ),
    lab: <LabTriagePanel draft={activeLabDraft} />,
    imaging: (
      <ImagingReportPanel
        draft={activeImagingDraft}
        imagePreviewUrl={xrayPreviewUrl}
        fileName={xrayFile?.name}
        isAnalyzing={isAnalyzingXray}
        onImageSelect={handleImagingSelect}
        onAnalyze={analyzeImagingUpload}
      />
    ),
    referral: (
      <ReferralLetterPanel
        draft={activeReferralDraft}
        patient={caseData.patient}
        signedLetters={signedLetters}
        sentReferrals={sentReferrals}
        onAudit={addAudit}
        onGenerate={handleGenerateReferral}
        onSigned={handleSignedLetter}
        onSent={handleSentReferral}
        isGenerating={isGeneratingReferral}
      />
    ),
  };

  if (isCheckingAuth) {
    return (
      <main className="auth-shell">
        <section className="auth-panel" aria-live="polite">
          <p className="eyebrow">Clinic Dashboard</p>
          <h1>Checking access</h1>
        </section>
      </main>
    );
  }

  if (authRequired && !authToken) {
    return <AuthScreen error={authError} onSignIn={handleSignIn} />;
  }

  return (
    <main className="app-shell">
      <aside className="sidebar" aria-label="Patient worklist and report sections">
        <div>
          <p className="eyebrow">Clinic Dashboard</p>
          <h1>Patient library</h1>
          <p className="subtle">Select a patient, scan incoming records, and review AI-assisted drafts.</p>
        </div>

        {authRequired && (
          <button className="sign-out-button" type="button" onClick={handleSignOut}>
            Sign out
          </button>
        )}

        <section className="sidebar-patient-list" aria-label="Patient worklist">
          {patients.map((patient) => {
            const profile = patient.caseData.patient;
            return (
              <button
                key={patient.id}
                className={patient.id === activePatientId ? "active" : ""}
                type="button"
                onClick={() => handleSelectPatient(patient.id)}
              >
                <span className="case-avatar">{getPatientInitials(profile.name)}</span>
                <span>
                  <strong>{profile.name}</strong>
                  <small>{formatPatientProfile(profile)} / {profile.id}</small>
                </span>
                <em>{patient.status}</em>
              </button>
            );
          })}
        </section>

        <nav className="report-tabs" aria-label="Report sections">
          {dynamicReportSections.map((section) => (
            <button
              key={section.id}
              className={activePanel === section.id ? "active" : ""}
              onClick={() => goToPanel(section.id)}
              type="button"
            >
              <span>{section.label}</span>
              <small>{section.detail}</small>
            </button>
          ))}
        </nav>

        <label className="upload-button">
          <span>Scan into selected chart</span>
          <input type="file" onChange={handleUpload} />
        </label>
        {status && <p className="upload-status">{status}</p>}
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

        <nav className="workflow-rail" aria-label="Case progress">
          {workflowStages.map((stage, index) => (
            <button
              key={stage.id}
              type="button"
              className={activeStage === stage.id ? "stage-card active" : `stage-card ${stage.status}`}
              onClick={() => goToStage(stage)}
            >
              <span>{String(index + 1).padStart(2, "0")}</span>
              <strong>{stage.label}</strong>
            </button>
          ))}
        </nav>

        <div className="dashboard-grid">
          <section className="review-surface" key={activePanel}>{panels[activePanel]}</section>
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

function AuthScreen({ error, onSignIn }) {
  const [token, setToken] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setIsSubmitting(true);
    try {
      await onSignIn(token);
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <main className="auth-shell">
      <section className="auth-panel" aria-labelledby="auth-title">
        <div>
          <p className="eyebrow">Clinic Dashboard</p>
          <h1 id="auth-title">Staff access</h1>
          <p>Enter the clinic dashboard access token to open patient reports.</p>
        </div>

        <form className="auth-form" onSubmit={handleSubmit}>
          <label>
            Access token
            <input
              autoComplete="current-password"
              autoFocus
              type="password"
              placeholder={DEMO_ACCESS_TOKEN}
              value={token}
              onChange={(e) => setToken(e.target.value)}
            />
          </label>
          {error && <p className="auth-error">{error}</p>}
          <button type="submit" disabled={isSubmitting}>
            {isSubmitting ? "Checking..." : "Sign in"}
          </button>
        </form>
      </section>
    </main>
  );
}

function PatientLibraryPanel({ activePatientId, onCreateIncomingPatient, onSelectPatient, patients }) {
  const incoming = patients.filter((patient) => patient.status === "incoming");
  const library = patients.filter((patient) => patient.status !== "incoming");

  return (
    <section className="support-panel patient-library-panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Patient worklist</p>
          <h3>Library and incoming records</h3>
        </div>
        <button className="create-patient-button" type="button" onClick={onCreateIncomingPatient}>
          New incoming
        </button>
      </div>

      <PatientGroup
        activePatientId={activePatientId}
        label="Incoming"
        onSelectPatient={onSelectPatient}
        patients={incoming}
      />
      <PatientGroup
        activePatientId={activePatientId}
        label="Library"
        onSelectPatient={onSelectPatient}
        patients={library}
      />
    </section>
  );
}

function PatientGroup({ activePatientId, label, onSelectPatient, patients }) {
  return (
    <section className="patient-group">
      <h4>{label}</h4>
      <div className="patient-card-grid">
        {patients.length === 0 ? (
          <div className="empty-worklist">No patients in this queue yet.</div>
        ) : patients.map((patient) => {
          const profile = patient.caseData.patient;
          const latestRecord = patient.records[0];
          return (
            <button
              key={patient.id}
              className={patient.id === activePatientId ? "patient-card active" : "patient-card"}
              type="button"
              onClick={() => onSelectPatient(patient.id)}
            >
              <span className="case-avatar">{getPatientInitials(profile.name)}</span>
              <strong>{profile.name}</strong>
              <small>{formatPatientProfile(profile)} / {profile.id}</small>
              <span>{latestRecord ? `${latestRecord.category}: ${latestRecord.status}` : "No records scanned"}</span>
            </button>
          );
        })}
      </div>
    </section>
  );
}

function CaseIntakePanel({
  records,
  patient,
  status,
  onUpload,
  onSourceFile,
  urgency,
  sourceUploadMode,
  onSourceUploadModeChange,
  patientDocumentDraft,
  patientDocumentFileName,
  patientDocumentPreviewUrl,
  isExtractingPatientDocument,
  onPatientDocumentUpload,
  onPatientDocumentFile,
  onApplyPatientDetails,
}) {
  const [isSourceDragging, setIsSourceDragging] = useState(false);
  const [isIdentityDragging, setIsIdentityDragging] = useState(false);
  const hasApplicablePatientDetails = Boolean(
    patientDocumentDraft?.patient_name ||
      patientDocumentDraft?.patient_id ||
      patientDocumentDraft?.age ||
      patientDocumentDraft?.sex
  );

  return (
    <section className="support-panel intake-panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Record intake</p>
          <h3>Scan into selected patient chart</h3>
        </div>
        <span className={`urgency-badge ${urgency}`}>{urgency}</span>
      </div>

      <div className="intake-mode-row">
        <span>Incoming source type</span>
        <div className="segmented-control">
          <button
            className={sourceUploadMode === "clinical" ? "active" : ""}
            type="button"
            onClick={() => onSourceUploadModeChange("clinical")}
          >
            Clinical
          </button>
          <button
            className={sourceUploadMode === "imaging" ? "active" : ""}
            type="button"
            onClick={() => onSourceUploadModeChange("imaging")}
          >
            Imaging
          </button>
        </div>
      </div>

      <div className="intake-grid">
        <label
          className={isSourceDragging ? "drop-zone dragging" : "drop-zone"}
          onDragEnter={(event) => handleDragEnter(event, setIsSourceDragging)}
          onDragOver={(event) => handleDragEnter(event, setIsSourceDragging)}
          onDragLeave={(event) => handleDragLeave(event, setIsSourceDragging)}
          onDrop={(event) => handleDrop(event, setIsSourceDragging, onSourceFile)}
        >
          <span>{sourceUploadMode === "imaging" ? "Drop imaging study" : "Drop clinical record"}</span>
          <small>{status || "Drag a file here or click to browse"}</small>
          <input
            accept={
              sourceUploadMode === "imaging"
                ? "image/*,.dcm,.dicom,.nii,.nii.gz,.h5"
                : "image/*,.pdf,.docx,.txt,.csv,.json,.md"
            }
            type="file"
            onChange={onUpload}
          />
        </label>
        <dl className="case-facts">
          <div>
            <dt>Patient</dt>
            <dd>{patient.name}</dd>
          </div>
          <div>
            <dt>Record</dt>
            <dd>{patient.id}</dd>
          </div>
          <div>
            <dt>Profile</dt>
            <dd>{patient.age}{patient.sex}</dd>
          </div>
        </dl>
      </div>

      <section className="record-ledger" aria-label="Patient records">
        <div className="panel-heading compact">
          <div>
            <p className="eyebrow">Patient database</p>
            <h4>Records in chart</h4>
          </div>
          <span>{records.length} files</span>
        </div>
        {records.length > 0 ? (
          <ol>
            {records.map((record) => (
              <li key={record.id}>
                <strong>{record.name}</strong>
                <span>{record.category}</span>
                <em>{record.status}</em>
              </li>
            ))}
          </ol>
        ) : (
          <p>No records scanned for this patient yet.</p>
        )}
      </section>


      <div className="identity-extraction">
        <div className="panel-heading compact">
          <div>
            <p className="eyebrow">Computer vision intake</p>
            <h4>Patient document extraction</h4>
          </div>
          {patientDocumentDraft && (
            <span className={`confidence-badge ${patientDocumentDraft.confidence}`}>
              {patientDocumentDraft.confidence} confidence
            </span>
          )}
        </div>

        <div className="identity-grid">
          <label
            className={isIdentityDragging ? "identity-upload dragging" : "identity-upload"}
            onDragEnter={(event) => handleDragEnter(event, setIsIdentityDragging)}
            onDragOver={(event) => handleDragEnter(event, setIsIdentityDragging)}
            onDragLeave={(event) => handleDragLeave(event, setIsIdentityDragging)}
            onDrop={(event) => handleDrop(event, setIsIdentityDragging, onPatientDocumentFile)}
          >
            {patientDocumentPreviewUrl ? (
              <img src={patientDocumentPreviewUrl} alt="Patient document preview" />
            ) : (
              <>
                <span>Upload ID, report, or booklet</span>
                <small>Drag a file here or click to browse</small>
              </>
            )}
            <input accept="image/*,.pdf" type="file" onChange={onPatientDocumentUpload} />
          </label>

          <div className="identity-review">
            <div className="identity-review-header">
              <strong>{patientDocumentFileName || "No patient document uploaded"}</strong>
              {isExtractingPatientDocument && <span>Extracting...</span>}
            </div>

            {patientDocumentDraft ? (
              <>
                {patientDocumentDraft.needs_review && (
                  <div className="review-required">Review required before applying to case</div>
                )}

                <dl className="identity-fields">
                  <IdentityField label="Document" value={patientDocumentDraft.document_type || "Unknown"} />
                  <IdentityField
                    confidence={getFieldConfidence(patientDocumentDraft, "patient_name")}
                    evidence={getExtractionEvidence(patientDocumentDraft, "patient_name")}
                    label="Name"
                    value={patientDocumentDraft.patient_name}
                  />
                  <IdentityField
                    confidence={getFieldConfidence(patientDocumentDraft, "patient_id")}
                    evidence={getExtractionEvidence(patientDocumentDraft, "patient_id")}
                    label={patientDocumentDraft.patient_id_type || "Patient ID"}
                    value={patientDocumentDraft.patient_id}
                  />
                  <IdentityField
                    confidence={getFieldConfidence(patientDocumentDraft, "date_of_birth")}
                    evidence={getExtractionEvidence(patientDocumentDraft, "date_of_birth")}
                    label="Date of birth"
                    value={patientDocumentDraft.date_of_birth}
                  />
                  <IdentityField
                    confidence={getFieldConfidence(patientDocumentDraft, "age")}
                    evidence={getExtractionEvidence(patientDocumentDraft, "age")}
                    label="Age"
                    value={patientDocumentDraft.age ? `${patientDocumentDraft.age}y` : ""}
                  />
                  <IdentityField
                    confidence={getFieldConfidence(patientDocumentDraft, "sex")}
                    evidence={getExtractionEvidence(patientDocumentDraft, "sex")}
                    label="Sex"
                    value={patientDocumentDraft.sex}
                  />
                  <IdentityField label="Image quality" value={patientDocumentDraft.source_quality} />
                </dl>

                {patientDocumentDraft.warnings?.length > 0 && (
                  <ul className="identity-warnings">
                    {patientDocumentDraft.warnings.map((warning) => (
                      <li key={warning}>{warning}</li>
                    ))}
                  </ul>
                )}

                <button
                  className="apply-details-button"
                  disabled={isExtractingPatientDocument || !hasApplicablePatientDetails}
                  type="button"
                  onClick={() => onApplyPatientDetails(patientDocumentDraft)}
                >
                  Apply reviewed details
                </button>
              </>
            ) : (
              <p>
                This step uses CV/OCR to pre-fill patient details. Staff must confirm the fields
                before applying them to the active case.
              </p>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}

function IdentityField({ confidence, evidence, label, value }) {
  return (
    <div>
      <dt>
        <span>{label}</span>
        {confidence && <em className={`field-confidence ${confidence}`}>{confidence}</em>}
      </dt>
      <dd>{formatIdentityValue(value)}</dd>
      {evidence && <small>{evidence}</small>}
    </div>
  );
}

function handleDragEnter(event, setDragging) {
  event.preventDefault();
  event.stopPropagation();
  setDragging(true);
}

function handleDragLeave(event, setDragging) {
  event.preventDefault();
  event.stopPropagation();
  if (!event.currentTarget.contains(event.relatedTarget)) {
    setDragging(false);
  }
}

function handleDrop(event, setDragging, onFile) {
  event.preventDefault();
  event.stopPropagation();
  setDragging(false);
  const file = event.dataTransfer.files?.[0];
  if (file) onFile?.(file);
}

function normalizeSex(value) {
  const text = String(value || "").trim().toLowerCase();
  if (["f", "female", "woman"].includes(text)) return "F";
  if (["m", "male", "man"].includes(text)) return "M";
  return "";
}

function formatIdentityValue(value) {
  if (value === null || value === undefined || value === "") return "Not detected";
  return String(value);
}

function getFieldConfidence(draft, field) {
  return draft?.field_confidence?.[field] || "";
}

function getExtractionEvidence(draft, field) {
  return draft?.extraction_evidence?.[field] || "";
}

function getPatientInitials(name) {
  return String(name || "?")
    .split(" ")
    .filter(Boolean)
    .map((part) => part[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();
}

function formatPatientProfile(patient) {
  if (!patient?.age && !patient?.sex) return "Profile pending";
  return `${patient.age || "?"}${patient.sex || ""}`;
}

function formatReferralFindings(labDraft, imagingDraft) {
  const labFindings = (labDraft.abnormals ?? []).map(
    (item) => `- ${item.name ?? item.analyte}: ${item.value} ${item.unit ?? ""} (${item.flag})`
  );
  const imagingImpression = imagingDraft.impression ? [`- ${imagingDraft.impression}`] : [];
  const findings = [...labFindings, ...imagingImpression];
  return findings.length > 0 ? findings.join("\n") : "- No structured findings attached yet.";
}

function createEmptyPatientDocumentDraft(message) {
  return {
    document_type: "unknown",
    patient_name: "",
    patient_id: "",
    patient_id_type: "",
    date_of_birth: "",
    age: null,
    sex: "",
    source_quality: "poor",
    confidence: "low",
    field_confidence: {
      patient_name: "low",
      patient_id: "low",
      date_of_birth: "low",
      age: "low",
      sex: "low",
    },
    extraction_evidence: {
      patient_name: "",
      patient_id: "",
      date_of_birth: "",
      age: "",
      sex: "",
    },
    needs_review: true,
    warnings: [message],
  };
}
