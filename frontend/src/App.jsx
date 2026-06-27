import { useEffect, useMemo, useState } from "react";
import DifferentialDxPanel from "./panels/DifferentialDxPanel.jsx";
import ImagingReportPanel from "./panels/ImagingReportPanel.jsx";
import LabTriagePanel from "./panels/LabTriagePanel.jsx";
import ReferralLetterPanel from "./panels/ReferralLetterPanel.jsx";
import ReviewStepper from "./components/ReviewStepper.jsx";
import EvidenceRail from "./components/EvidenceRail.jsx";
import PatientPicker from "./components/PatientPicker.jsx";
import AcuityBadge from "./components/AcuityBadge.jsx";
import { mostAcute } from "./acuity.js";

const initialAudit = [
  { actor: "System", action: "Session started", time: "09:12", detail: "Clinician signed in to the first-pass dashboard" },
];

// One guided first-pass flow. Each step reviews one AI draft; the clinician
// advances when satisfied and signs at the end. Steps stay clickable so a
// reviewer can jump back to recheck anything.
const STEPS = [
  { id: "intake", n: 1, label: "Intake", instruction: "Confirm the patient and their source labs. Upload a new report to re-triage." },
  { id: "lab", n: 2, label: "Lab triage", instruction: "Check the abnormal-value flags and acuity. Confirm nothing critical was missed." },
  { id: "imaging", n: 3, label: "Imaging", instruction: "Review the preliminary chest X-ray read against the scan, or upload a new one." },
  { id: "differential", n: 4, label: "Differential", instruction: "Review the ranked differentials and their cited next steps." },
  { id: "signoff", n: 5, label: "Referral & sign-off", instruction: "The letter is drafted from the case. Check the evidence, edit, then sign." },
];

const AUTH_TOKEN_STORAGE_KEY = "clinic-dashboard-auth-token";
const DOCTOR_NAME_STORAGE_KEY = "clinic-dashboard-doctor-name";
const DEMO_ACCESS_TOKEN = "clinic-demo-token";

function normalizeAccessToken(token) {
  const trimmed = token.trim();
  return trimmed.toLowerCase() === "clinic demo token" ? DEMO_ACCESS_TOKEN : trimmed;
}

function sexWord(sex) {
  if (sex === "F") return "female";
  if (sex === "M") return "male";
  return sex;
}

export default function App() {
  const [status, setStatus] = useState("");
  const [currentStep, setCurrentStep] = useState("intake");
  const [reviewedSteps, setReviewedSteps] = useState(() => new Set());
  const [auditLog, setAuditLog] = useState(initialAudit);
  const [signedLetters, setSignedLetters] = useState([]);
  const [sentReferrals, setSentReferrals] = useState([]);

  const [patients, setPatients] = useState([]);
  const [selectedPatientId, setSelectedPatientId] = useState(null);
  const [patient, setPatient] = useState(null);
  const [isLoadingPatient, setIsLoadingPatient] = useState(false);

  const [generatedLabDraft, setGeneratedLabDraft] = useState(null);
  const [generatedImagingDraft, setGeneratedImagingDraft] = useState(null);
  const [generatedDifferentialDraft, setGeneratedDifferentialDraft] = useState(null);
  const [generatedReferralDraft, setGeneratedReferralDraft] = useState(null);
  const [isGeneratingDifferential, setIsGeneratingDifferential] = useState(false);
  const [isGeneratingReferral, setIsGeneratingReferral] = useState(false);

  const [xrayPreviewUrl, setXrayPreviewUrl] = useState("");
  const [xrayFile, setXrayFile] = useState(null);
  const [isAnalyzingXray, setIsAnalyzingXray] = useState(false);

  // CV/OCR patient-ID intake — extract identity fields for staff to verify.
  const [patientDocumentDraft, setPatientDocumentDraft] = useState(null);
  const [patientDocumentPreviewUrl, setPatientDocumentPreviewUrl] = useState("");
  const [patientDocumentFileName, setPatientDocumentFileName] = useState("");
  const [isExtractingPatientDocument, setIsExtractingPatientDocument] = useState(false);

  const [authToken, setAuthToken] = useState(() => localStorage.getItem(AUTH_TOKEN_STORAGE_KEY) ?? "");
  const [doctorName, setDoctorName] = useState(() => localStorage.getItem(DOCTOR_NAME_STORAGE_KEY) ?? "");
  const [authError, setAuthError] = useState("");
  const [authRequired, setAuthRequired] = useState(true);
  const [isCheckingAuth, setIsCheckingAuth] = useState(true);

  const activeLabDraft = generatedLabDraft ?? patient?.lab_draft ?? null;
  const activeImagingDraft = generatedImagingDraft ?? patient?.imaging_draft ?? null;
  const activeDifferentialDraft = generatedDifferentialDraft ?? null;

  const dxUrgency = (activeDifferentialDraft?.red_flags?.length ?? 0) > 0 ? "emergency" : null;
  const urgency = mostAcute([activeLabDraft?.urgency, activeImagingDraft?.urgency, dxUrgency]);
  const patientLine = patient ? `${patient.name} · ${patient.age}${patient.sex} · ${patient.id}` : "";

  const referralDraft = useMemo(() => {
    if (!patient) return null;
    const findings = [
      ...(activeLabDraft?.abnormals ?? []).map(
        (item) => `${item.analyte ?? item.name}: ${item.value} ${item.unit ?? ""} (${item.flag})`.trim()
      ),
      ...(activeImagingDraft?.findings ?? []),
      ...(activeDifferentialDraft?.red_flags ?? []),
    ];
    return {
      recipient_specialty: "Internal Medicine",
      reason_for_referral: "Specialist assessment and management",
      clinical_summary: patient.summary,
      relevant_findings: findings,
      letter_markdown: `Dear Internal Medicine Team,

Re: ${patient.name} (${patient.age}${patient.sex}, ${patient.id})

I am referring ${patient.name} for specialist assessment and management.

Clinical summary:
${patient.summary}

Relevant findings:
${findings.length ? findings.map((f) => `- ${f}`).join("\n") : "- See attached results."}
${activeImagingDraft?.impression ? `- Imaging: ${activeImagingDraft.impression}` : ""}

Provisional considerations:
${(activeDifferentialDraft?.differentials ?? [])
  .map((item) => {
    const rationale = item.rationale ?? item.reason ?? item.supporting?.join("; ");
    return rationale ? `- ${item.condition}: ${rationale}` : `- ${item.condition}`;
  })
  .join("\n") || "- Pending differential review."}

Please assess and advise on further management.

Regards,
Clinician reviewer`,
    };
  }, [patient, activeLabDraft, activeImagingDraft, activeDifferentialDraft]);

  const activeReferralDraft = generatedReferralDraft ?? referralDraft;

  // ── Auth ──────────────────────────────────────────────────────────────
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
        if (isMounted) setAuthRequired(true);
      } finally {
        if (isMounted) setIsCheckingAuth(false);
      }
    }
    checkAuthStatus();
    return () => {
      isMounted = false;
    };
  }, []);

  // ── Load the patient roster once authed ───────────────────────────────
  useEffect(() => {
    if (isCheckingAuth) return;
    if (authRequired && !authToken) return;
    if (patients.length) return;
    loadPatients();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isCheckingAuth, authRequired, authToken]);

  // ── Auto-draft the referral letter the moment the clinician reaches sign-off ──
  useEffect(() => {
    if (currentStep !== "signoff" || !patient) return;
    if (generatedReferralDraft || isGeneratingReferral) return;
    handleGenerateReferral();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentStep, patient, generatedReferralDraft, isGeneratingReferral]);

  function saveAuthToken(token) {
    if (token) localStorage.setItem(AUTH_TOKEN_STORAGE_KEY, token);
    else localStorage.removeItem(AUTH_TOKEN_STORAGE_KEY);
    setAuthToken(token);
  }

  function saveDoctorName(name) {
    if (name) localStorage.setItem(DOCTOR_NAME_STORAGE_KEY, name);
    else localStorage.removeItem(DOCTOR_NAME_STORAGE_KEY);
    setDoctorName(name);
  }

  async function authFetch(url, options = {}) {
    const headers = new Headers(options.headers);
    if (authRequired) headers.set("Authorization", `Bearer ${authToken}`);
    const res = await fetch(url, { ...options, headers });
    if (res.status === 401 || res.status === 403) {
      setAuthError("Session token was rejected. Sign in again.");
      saveAuthToken("");
    }
    return res;
  }

  async function handleSignIn({ token, name }) {
    setAuthError("");
    const cleanName = (name ?? "").trim();
    if (!cleanName) {
      setAuthError("Enter your name.");
      return;
    }
    if (authRequired) {
      const trimmedToken = normalizeAccessToken(token ?? "");
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
    }
    saveDoctorName(cleanName);
    addAudit(cleanName, "Signed in", authRequired ? "Access token verified" : "Session started");
  }

  function handleSignOut() {
    saveAuthToken("");
    saveDoctorName("");
    setAuthError("");
    setPatients([]);
    setPatient(null);
    setSelectedPatientId(null);
    addAudit("Staff", "Signed out", "Session cleared");
  }

  // ── Patients ──────────────────────────────────────────────────────────
  async function loadPatients() {
    setIsLoadingPatient(true);
    try {
      const res = await authFetch("/api/patients");
      if (!res.ok) throw new Error(`Patients failed (${res.status})`);
      const data = await res.json();
      const list = data.patients ?? [];
      setPatients(list);
      if (list.length) await loadPatient(list[0].id);
    } catch (err) {
      addAudit("System", "Patient list failed", err.message);
    } finally {
      setIsLoadingPatient(false);
    }
  }

  function resetDraftsFor(stepId = "intake") {
    setGeneratedLabDraft(null);
    setGeneratedImagingDraft(null);
    setGeneratedDifferentialDraft(null);
    setGeneratedReferralDraft(null);
    setXrayFile(null);
    setReviewedSteps(new Set());
    setCurrentStep(stepId);
    setStatus("");
    if (xrayPreviewUrl.startsWith("blob:")) URL.revokeObjectURL(xrayPreviewUrl);
    setXrayPreviewUrl("");
    setPatientDocumentDraft(null);
    setPatientDocumentFileName("");
    if (patientDocumentPreviewUrl.startsWith("blob:")) URL.revokeObjectURL(patientDocumentPreviewUrl);
    setPatientDocumentPreviewUrl("");
  }

  async function loadPatient(id) {
    setSelectedPatientId(id);
    setIsLoadingPatient(true);
    resetDraftsFor("intake");
    try {
      const res = await authFetch(`/api/patients/${id}`);
      if (!res.ok) throw new Error(`Patient load failed (${res.status})`);
      const data = await res.json();
      setPatient(data);
      addAudit("System", "Opened patient", `${data.name} (${data.id})`);

      // Their X-ray, if on file, is already there — fetch it (auth) as a blob.
      if (data.has_xray && data.xray_url) {
        try {
          const imgRes = await authFetch(`/api${data.xray_url}`);
          if (imgRes.ok) setXrayPreviewUrl(URL.createObjectURL(await imgRes.blob()));
        } catch {
          /* image stays empty; rail shows the prompt */
        }
      }

      // Roll labs straight into a differential so the case is review-ready.
      if (data.lab_draft) {
        await generateDifferentialDraft(data, data.lab_draft, data.imaging_draft, "Differential generated from patient labs");
      }
    } catch (err) {
      addAudit("System", "Patient load failed", err.message);
    } finally {
      setIsLoadingPatient(false);
    }
  }

  // ── Drafts ────────────────────────────────────────────────────────────
  async function handleUpload(e) {
    const file = e.target.files?.[0];
    if (!file || !patient) return;
    setStatus("Uploading…");
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
        setCurrentStep("lab");
      }
      setStatus(`${result.filename} uploaded`);
      addAudit("Staff", "Uploaded source file", result.filename);
      if (nextLabDraft) {
        await generateDifferentialDraft(patient, nextLabDraft, activeImagingDraft, "Uploaded lab routed into differential diagnosis");
      }
    } catch (err) {
      setStatus("Error: " + err.message);
    }
  }

  async function generateDifferentialDraft(patientObj, labDraft, imagingDraft, auditDetail) {
    if (!patientObj) return null;
    setIsGeneratingDifferential(true);
    try {
      const res = await authFetch("/api/engine/run/differential_dx", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text: patientObj.summary,
          context: {
            patient: { id: patientObj.id, name: patientObj.name, age: patientObj.age, sex: patientObj.sex },
            sex: sexWord(patientObj.sex),
            age: patientObj.age,
            lab_triage: labDraft,
            imaging_report: imagingDraft,
          },
        }),
      });
      if (!res.ok) throw new Error(`Differential generation failed (${res.status})`);
      const result = await res.json();
      setGeneratedDifferentialDraft(result.draft);
      setGeneratedReferralDraft(null);
      addAudit("AI", "Generated differential draft", auditDetail);
      return result.draft;
    } catch (err) {
      addAudit("System", "Differential generation failed", err.message);
      return null;
    } finally {
      setIsGeneratingDifferential(false);
    }
  }

  async function handleGenerateReferral() {
    if (!patient) return;
    setIsGeneratingReferral(true);
    try {
      const res = await authFetch("/api/engine/run/referral_letter", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text: patient.summary,
          context: {
            patient: { id: patient.id, name: patient.name, age: patient.age, sex: patient.sex, summary: patient.summary },
            lab_triage: activeLabDraft,
            imaging_report: activeImagingDraft,
            differential_dx: activeDifferentialDraft,
            recipient_specialty: "Internal Medicine",
            reason_for_referral: "Specialist assessment and management",
          },
        }),
      });
      if (!res.ok) throw new Error(`Referral generation failed (${res.status})`);
      const result = await res.json();
      setGeneratedReferralDraft(result.draft);
      if (result.draft?.generation_note) {
        addAudit("System", "Referral drafted (fallback)", result.draft.generation_note);
      } else {
        addAudit("AI", "Drafted referral letter", "Letter built from the reviewed case, ready to edit");
      }
    } catch (err) {
      addAudit("System", "Referral generation failed", err.message);
    } finally {
      setIsGeneratingReferral(false);
    }
  }

  // ── Patient-ID document intake (CV/OCR) ───────────────────────────────
  async function handlePatientDocumentUpload(e) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file || !patient) return;
    setPatientDocumentFileName(file.name);
    setPatientDocumentDraft(null);
    if (patientDocumentPreviewUrl.startsWith("blob:")) URL.revokeObjectURL(patientDocumentPreviewUrl);
    setPatientDocumentPreviewUrl(file.type.startsWith("image/") ? URL.createObjectURL(file) : "");
    setIsExtractingPatientDocument(true);

    const body = new FormData();
    body.append("file", file);
    try {
      const res = await authFetch("/api/ingestion/patient-document", { method: "POST", body });
      if (!res.ok) throw new Error(`Patient document extraction failed (${res.status})`);
      const result = await res.json();
      setPatientDocumentDraft(result.draft);
      addAudit("AI", "Extracted patient details", "ID document fields ready for staff review");
    } catch (err) {
      setPatientDocumentDraft(createEmptyPatientDocumentDraft(err.message));
      addAudit("System", "Patient detail extraction failed", err.message);
    } finally {
      setIsExtractingPatientDocument(false);
    }
  }

  // Staff-confirmed fields update the active case header in-session. This is
  // CV-assisted intake review, not automatic identity verification.
  function handleApplyPatientDetails(draft) {
    if (!patient) return;
    setPatient((prev) => ({
      ...prev,
      name: draft.patient_name || prev.name,
      id: draft.patient_id || prev.id,
      age: draft.age ?? prev.age,
      sex: normalizeSex(draft.sex) || prev.sex,
    }));
    addAudit("Staff", "Applied patient details", "Reviewed CV extraction and updated the active case header");
  }

  function handleXraySelect(file) {
    setXrayFile(file);
    setGeneratedImagingDraft(null);
    setGeneratedReferralDraft(null);
    if (xrayPreviewUrl.startsWith("blob:")) URL.revokeObjectURL(xrayPreviewUrl);
    setXrayPreviewUrl(URL.createObjectURL(file));
    setCurrentStep("imaging");
    addAudit("Staff", "Uploaded chest X-ray", file.name);
    // Run the AI read immediately — no separate "Review" press, same as labs.
    handleAnalyzeXray(file);
  }

  async function handleAnalyzeXray(file = xrayFile) {
    if (!file || !patient) return;
    setIsAnalyzingXray(true);
    const body = new FormData();
    body.append("file", file);
    try {
      // Persists the scan against the patient and returns the imaging read.
      const res = await authFetch(`/api/patients/${patient.id}/xray`, { method: "POST", body });
      if (!res.ok) throw new Error(`Imaging analysis failed (${res.status})`);
      const result = await res.json();
      const nextImagingDraft = result.draft;
      setGeneratedImagingDraft(nextImagingDraft);
      setGeneratedReferralDraft(null);
      await generateDifferentialDraft(patient, activeLabDraft, nextImagingDraft, "Imaging draft added to differential context");
      if (result.draft?._api_error) {
        addAudit("System", "Imaging read unavailable", "Vision model returned no read; manual review needed");
      } else {
        addAudit("AI", "Generated imaging draft", "Preliminary chest X-ray read ready for clinician review");
      }
    } catch (err) {
      addAudit("System", "Imaging analysis failed", err.message);
    } finally {
      setIsAnalyzingXray(false);
    }
  }

  function addAudit(actor, action, detail) {
    const now = new Date();
    setAuditLog((items) => [
      { actor, action, detail, time: now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) },
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

  // ── Step navigation ───────────────────────────────────────────────────
  const stepIndex = STEPS.findIndex((s) => s.id === currentStep);
  const step = STEPS[stepIndex] ?? STEPS[0];
  const isLastStep = stepIndex === STEPS.length - 1;
  const nextStep = STEPS[stepIndex + 1];

  const urgencyByStep = {
    lab: activeLabDraft?.urgency,
    imaging: activeImagingDraft?.urgency,
    differential: dxUrgency,
  };

  function goToStep(id) {
    setCurrentStep(id);
  }

  function markReviewed(id) {
    setReviewedSteps((prev) => {
      const next = new Set(prev);
      next.add(id);
      return next;
    });
  }

  function goNext() {
    markReviewed(currentStep);
    if (nextStep) setCurrentStep(nextStep.id);
  }

  function goBack() {
    const prev = STEPS[stepIndex - 1];
    if (prev) setCurrentStep(prev.id);
  }

  function renderStep() {
    switch (currentStep) {
      case "intake":
        return (
          <CaseIntakePanel
            patient={patient}
            status={status}
            onUpload={handleUpload}
            urgency={urgency}
            patientDocumentDraft={patientDocumentDraft}
            patientDocumentFileName={patientDocumentFileName}
            patientDocumentPreviewUrl={patientDocumentPreviewUrl}
            isExtractingPatientDocument={isExtractingPatientDocument}
            onPatientDocumentUpload={handlePatientDocumentUpload}
            onApplyPatientDetails={handleApplyPatientDetails}
          />
        );
      case "lab":
        return <LabTriagePanel draft={activeLabDraft} />;
      case "imaging":
        return (
          <ImagingReportPanel
            draft={activeImagingDraft}
            imagePreviewUrl={xrayPreviewUrl}
            fileName={xrayFile?.name}
            isAnalyzing={isAnalyzingXray}
            onImageSelect={handleXraySelect}
          />
        );
      case "differential":
        return (
          <DifferentialDxPanel
            draft={activeDifferentialDraft}
            isGenerating={isGeneratingDifferential}
            onGenerate={() => generateDifferentialDraft(patient, activeLabDraft, activeImagingDraft, "Differential regenerated")}
          />
        );
      case "signoff":
        return (
          <div className="signoff-layout">
            <ReferralLetterPanel
              draft={activeReferralDraft}
              patient={patient}
              reviewerName={doctorName}
              signedLetters={signedLetters}
              sentReferrals={sentReferrals}
              onAudit={addAudit}
              onSigned={handleSignedLetter}
              onSent={handleSentReferral}
              isGenerating={isGeneratingReferral}
            />
            <EvidenceRail
              xrayPreviewUrl={xrayPreviewUrl}
              imagingDraft={activeImagingDraft}
              labDraft={activeLabDraft}
              differentialDraft={activeDifferentialDraft}
              onJumpToStep={goToStep}
            />
          </div>
        );
      default:
        return null;
    }
  }

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

  if ((authRequired && !authToken) || !doctorName) {
    return <AuthScreen error={authError} onSignIn={handleSignIn} requireToken={authRequired} />;
  }

  return (
    <main className="app-shell">
      <aside className="sidebar" aria-label="Patients and activity">
        <div>
          <p className="eyebrow">Clinic Dashboard</p>
          <h1>First-pass review</h1>
          <p className="subtle">AI drafts the first pass. You review each step and sign. Nothing is signed without you.</p>
        </div>

        <div className="signed-in-row">
          <span className="signed-in-label">
            Signed in as <strong>{doctorName}</strong>
          </span>
          <button className="sign-out-button" type="button" onClick={handleSignOut}>
            Sign out
          </button>
        </div>

        <PatientPicker
          patients={patients}
          selectedId={selectedPatientId}
          onSelect={loadPatient}
          isLoading={isLoadingPatient}
        />

        <section className="sidebar-activity" aria-label="Audit trail">
          <div className="audit-heading">
            <h3>Activity</h3>
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
        </section>
      </aside>

      <section className="workspace">
        {!patient ? (
          <div className="workspace-empty">
            {isLoadingPatient ? "Loading patient…" : "Select a patient to begin a first pass."}
          </div>
        ) : (
          <>
            <ReviewStepper
              steps={STEPS}
              currentStep={currentStep}
              reviewedSteps={reviewedSteps}
              urgencyByStep={urgencyByStep}
              onJump={goToStep}
            />

            <header className="step-header">
              <div>
                <p className="eyebrow">Step {step.n} of {STEPS.length} · {patientLine}</p>
                <h2>{step.label}</h2>
                <p className="step-instruction">{step.instruction}</p>
              </div>
              {urgency && <AcuityBadge urgency={urgency} size="lg" />}
            </header>

            <div className="step-body" key={currentStep}>
              {renderStep()}
            </div>

            <footer className="step-nav">
              <button className="step-back" type="button" onClick={goBack} disabled={stepIndex === 0}>
                ← Back
              </button>
              {!isLastStep ? (
                <button className="step-next" type="button" onClick={goNext}>
                  {reviewedSteps.has(currentStep) ? `Next: ${nextStep.label} →` : `Mark reviewed · ${nextStep.label} →`}
                </button>
              ) : (
                <span className="step-final-hint">Review the evidence, then sign the letter to complete the first pass.</span>
              )}
            </footer>
          </>
        )}
      </section>
    </main>
  );
}

function AuthScreen({ error, onSignIn, requireToken = true }) {
  const [name, setName] = useState("");
  const [token, setToken] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setIsSubmitting(true);
    try {
      await onSignIn({ token, name });
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
          <p>
            {requireToken
              ? "Enter your name and the clinic access token to open patient reports."
              : "Enter your name to open patient reports."}
          </p>
        </div>

        <form className="auth-form" onSubmit={handleSubmit}>
          <label>
            Your name
            <input
              autoComplete="name"
              autoFocus
              type="text"
              placeholder="Dr. Jane Smith"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </label>
          {requireToken && (
            <label>
              Access token
              <input
                autoComplete="current-password"
                type="password"
                placeholder={DEMO_ACCESS_TOKEN}
                value={token}
                onChange={(e) => setToken(e.target.value)}
              />
            </label>
          )}
          {error && <p className="auth-error">{error}</p>}
          <button type="submit" disabled={isSubmitting}>
            {isSubmitting ? "Checking..." : "Sign in"}
          </button>
        </form>
      </section>
    </main>
  );
}

function CaseIntakePanel({
  patient,
  status,
  onUpload,
  urgency,
  patientDocumentDraft,
  patientDocumentFileName,
  patientDocumentPreviewUrl,
  isExtractingPatientDocument,
  onPatientDocumentUpload,
  onApplyPatientDetails,
}) {
  if (!patient) return null;
  const hasApplicableDetails = Boolean(
    patientDocumentDraft?.patient_name ||
      patientDocumentDraft?.patient_id ||
      patientDocumentDraft?.age ||
      patientDocumentDraft?.sex
  );

  return (
    <section className="support-panel intake-panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Case intake</p>
          <h3>{patient.name}</h3>
        </div>
        {urgency && <AcuityBadge urgency={urgency} />}
      </div>

      <p className="intake-summary">{patient.summary}</p>

      <div className="intake-grid">
        <label className="drop-zone">
          <span>Upload a new lab report</span>
          <small>{status || "Re-triage from a fresh lab PDF or photo"}</small>
          <input type="file" onChange={onUpload} />
        </label>
        <dl className="case-facts">
          <div>
            <dt>Record</dt>
            <dd>{patient.id}</dd>
          </div>
          <div>
            <dt>Profile</dt>
            <dd>{patient.age}{patient.sex}</dd>
          </div>
          <div>
            <dt>Scan on file</dt>
            <dd>{patient.has_xray ? "Chest X-ray" : "None"}</dd>
          </div>
        </dl>
      </div>

      <div className="identity-extraction">
        <div className="panel-heading compact">
          <div>
            <p className="eyebrow">Computer-vision intake</p>
            <h4>Patient ID scanner</h4>
          </div>
          {patientDocumentDraft && (
            <span className={`confidence-badge ${patientDocumentDraft.confidence}`}>
              {patientDocumentDraft.confidence} confidence
            </span>
          )}
        </div>

        <div className="identity-grid">
          <label className="identity-upload">
            {patientDocumentPreviewUrl ? (
              <img src={patientDocumentPreviewUrl} alt="Patient document preview" />
            ) : (
              <span className="scan-dropzone-prompt">
                <strong>Click anywhere to scan an ID or document</strong>
                <small>Identity card, report, or booklet — fields extract automatically.</small>
              </span>
            )}
            {isExtractingPatientDocument && <span className="scan-analyzing">Extracting…</span>}
            <input accept="image/*,.pdf" type="file" onChange={onPatientDocumentUpload} disabled={isExtractingPatientDocument} />
          </label>

          <div className="identity-review">
            <div className="identity-review-header">
              <strong>{patientDocumentFileName || "No document scanned yet"}</strong>
              {isExtractingPatientDocument && <span>Extracting…</span>}
            </div>

            {patientDocumentDraft ? (
              <>
                {patientDocumentDraft.needs_review && (
                  <div className="review-required">Review required before applying to the case</div>
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
                  disabled={isExtractingPatientDocument || !hasApplicableDetails}
                  type="button"
                  onClick={() => onApplyPatientDetails(patientDocumentDraft)}
                >
                  Apply reviewed details
                </button>
              </>
            ) : (
              <p className="muted-note">
                Scans an ID or clinical document and uses CV/OCR to pre-fill patient details.
                Staff confirm the fields before applying them to the active case.
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

function normalizeSex(value) {
  const text = String(value || "").trim().toLowerCase();
  if (["f", "female", "woman"].includes(text)) return "F";
  if (["m", "male", "man"].includes(text)) return "M";
  return "";
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
    field_confidence: { patient_name: "low", patient_id: "low", date_of_birth: "low", age: "low", sex: "low" },
    extraction_evidence: { patient_name: "", patient_id: "", date_of_birth: "", age: "", sex: "" },
    needs_review: true,
    warnings: [message],
  };
}
