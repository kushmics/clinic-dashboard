import { useEffect, useMemo, useState } from "react";
import DifferentialDxPanel from "./panels/DifferentialDxPanel.jsx";
import ImagingReportPanel from "./panels/ImagingReportPanel.jsx";
import LabTriagePanel from "./panels/LabTriagePanel.jsx";
import ReferralLetterPanel from "./panels/ReferralLetterPanel.jsx";
import ReviewStepper from "./components/ReviewStepper.jsx";
import EvidenceRail from "./components/EvidenceRail.jsx";

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

// One guided first-pass flow. Each step reviews one AI draft; the clinician
// advances when satisfied and signs at the end. Steps stay clickable so a
// reviewer can jump back to recheck anything.
const STEPS = [
  { id: "intake", n: 1, label: "Intake", instruction: "Upload the patient's lab report to start the first pass." },
  { id: "lab", n: 2, label: "Lab triage", instruction: "Check the AI's abnormal-value flags and urgency. Confirm nothing critical was missed." },
  { id: "imaging", n: 3, label: "Imaging", instruction: "Upload the chest X-ray and review the preliminary read against the scan." },
  { id: "differential", n: 4, label: "Differential", instruction: "Review the ranked differentials and their cited next steps." },
  { id: "signoff", n: 5, label: "Referral & sign-off", instruction: "Check the evidence on the right, edit the letter, then sign." },
];

const AUTH_TOKEN_STORAGE_KEY = "clinic-dashboard-auth-token";
const DEMO_ACCESS_TOKEN = "clinic-demo-token";

function normalizeAccessToken(token) {
  const trimmed = token.trim();
  return trimmed.toLowerCase() === "clinic demo token" ? DEMO_ACCESS_TOKEN : trimmed;
}

export default function App() {
  const [status, setStatus] = useState("");
  const [caseData] = useState(demoCase);
  const [currentStep, setCurrentStep] = useState("intake");
  const [reviewedSteps, setReviewedSteps] = useState(() => new Set());
  const [auditLog, setAuditLog] = useState(initialAudit);
  const [signedLetters, setSignedLetters] = useState([]);
  const [sentReferrals, setSentReferrals] = useState([]);
  const [generatedReferralDraft, setGeneratedReferralDraft] = useState(null);
  const [isGeneratingReferral, setIsGeneratingReferral] = useState(false);
  const [generatedDifferentialDraft, setGeneratedDifferentialDraft] = useState(null);
  const [isGeneratingDifferential, setIsGeneratingDifferential] = useState(false);
  const [generatedImagingDraft, setGeneratedImagingDraft] = useState(null);
  const [xrayPreviewUrl, setXrayPreviewUrl] = useState("");
  const [xrayFile, setXrayFile] = useState(null);
  const [isAnalyzingXray, setIsAnalyzingXray] = useState(false);
  const [authToken, setAuthToken] = useState(() => localStorage.getItem(AUTH_TOKEN_STORAGE_KEY) ?? "");
  const [authError, setAuthError] = useState("");
  const [authRequired, setAuthRequired] = useState(true);
  const [isCheckingAuth, setIsCheckingAuth] = useState(true);
  const [generatedLabDraft, setGeneratedLabDraft] = useState(null);

  const activeLabDraft = generatedLabDraft ?? caseData.lab_triage;
  const activeImagingDraft = generatedImagingDraft ?? caseData.imaging_report;
  const activeDifferentialDraft = generatedDifferentialDraft ?? caseData.differential_dx;
  const urgency = activeLabDraft.urgency ?? activeImagingDraft.urgency ?? "routine";
  const patientLine = `${caseData.patient.name} / ${caseData.patient.age}${caseData.patient.sex} / ${caseData.patient.id}`;

  const referralDraft = useMemo(
    () => ({
      recipient_specialty: "Internal Medicine",
      reason_for_referral: "Symptomatic anemia and cardiometabolic risk review",
      clinical_summary: caseData.patient.summary,
      relevant_findings: [
        ...(activeLabDraft.abnormals ?? []).map(
          (item) => `${item.name ?? item.analyte}: ${item.value} ${item.unit ?? ""} (${item.flag})`
        ),
        ...(activeImagingDraft.findings ?? []),
        ...(activeDifferentialDraft.red_flags ?? []),
      ],
      letter_markdown: `Dear Internal Medicine Team,

Re: ${caseData.patient.name}

I am referring ${caseData.patient.name} for assessment of symptomatic anemia and cardiometabolic risk.

Clinical summary:
${caseData.patient.summary}

Relevant findings:
${(activeLabDraft.abnormals ?? [])
  .map((item) => `- ${item.name ?? item.analyte}: ${item.value} ${item.unit ?? ""} (${item.flag})`)
  .join("\n")}
- ${activeImagingDraft.impression}

Provisional considerations:
${activeDifferentialDraft.differentials
  .map((item) => {
    const rationale = item.rationale ?? item.reason ?? item.supporting?.join("; ");
    return rationale ? `- ${item.condition}: ${rationale}` : `- ${item.condition}`;
  })
  .join("\n")}

Please assess and advise on further management.

Regards,
Clinician reviewer`,
    }),
    [caseData, activeDifferentialDraft, activeImagingDraft, activeLabDraft]
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

  async function handleUpload(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    setStatus("Uploading...");
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
        await generateDifferentialDraft(nextLabDraft, activeImagingDraft, "Uploaded lab routed into differential diagnosis");
      }
    } catch (err) {
      setStatus("Error: " + err.message);
    }
  }

  async function generateDifferentialDraft(
    labDraft = activeLabDraft,
    imagingDraft = activeImagingDraft,
    auditDetail = "Lab triage and imaging drafts routed into differential diagnosis"
  ) {
    setIsGeneratingDifferential(true);
    try {
      const res = await authFetch("/api/engine/run/differential_dx", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text: caseData.patient.summary,
          context: {
            patient: caseData.patient,
            sex: caseData.patient.sex === "F" ? "female" : caseData.patient.sex === "M" ? "male" : caseData.patient.sex,
            age: caseData.patient.age,
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
            differential_dx: activeDifferentialDraft,
            recipient_specialty: "Internal Medicine",
            reason_for_referral: "Symptomatic anemia and cardiometabolic risk review",
          },
        }),
      });
      if (!res.ok) throw new Error(`Referral generation failed (${res.status})`);
      const result = await res.json();
      setGeneratedReferralDraft(result.draft);
      setCurrentStep("signoff");
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

  function handleXraySelect(file) {
    setXrayFile(file);
    setGeneratedImagingDraft(null);
    setGeneratedReferralDraft(null);
    if (xrayPreviewUrl) URL.revokeObjectURL(xrayPreviewUrl);
    setXrayPreviewUrl(URL.createObjectURL(file));
    setCurrentStep("imaging");
    addAudit("Staff", "Uploaded chest X-ray", file.name);
  }

  async function handleAnalyzeXray(file = xrayFile) {
    if (!file) return;
    setIsAnalyzingXray(true);
    const body = new FormData();
    body.append("file", file);
    try {
      const res = await authFetch("/api/imaging/analyze-upload", { method: "POST", body });
      if (!res.ok) throw new Error(`Imaging analysis failed (${res.status})`);
      const result = await res.json();
      const nextImagingDraft = result.draft;
      setGeneratedImagingDraft(nextImagingDraft);
      setGeneratedReferralDraft(null);
      setCurrentStep("imaging");
      await generateDifferentialDraft(activeLabDraft, nextImagingDraft, "Imaging draft added to differential context");
      if (result.draft?.generation_note) {
        addAudit("System", "Imaging generation used fallback", result.draft.generation_note);
      } else {
        addAudit("AI", "Generated imaging draft", "OpenAI Vision preliminary chest X-ray read ready for clinician review");
      }
    } catch (err) {
      addAudit("System", "Imaging analysis failed", err.message);
    } finally {
      setIsAnalyzingXray(false);
    }
  }

  const stepIndex = STEPS.findIndex((s) => s.id === currentStep);
  const step = STEPS[stepIndex] ?? STEPS[0];
  const isLastStep = stepIndex === STEPS.length - 1;
  const nextStep = STEPS[stepIndex + 1];

  const dxUrgency = (activeDifferentialDraft?.red_flags?.length ?? 0) > 0 ? "urgent" : null;
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
          <CaseIntakePanel patient={caseData.patient} status={status} onUpload={handleUpload} urgency={urgency} />
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
            onAnalyze={handleAnalyzeXray}
          />
        );
      case "differential":
        return (
          <DifferentialDxPanel
            draft={activeDifferentialDraft}
            isGenerating={isGeneratingDifferential}
            onGenerate={() => generateDifferentialDraft()}
          />
        );
      case "signoff":
        return (
          <div className="signoff-layout">
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

  if (authRequired && !authToken) {
    return <AuthScreen error={authError} onSignIn={handleSignIn} />;
  }

  return (
    <main className="app-shell">
      <aside className="sidebar" aria-label="Case and activity">
        <div>
          <p className="eyebrow">Clinic Dashboard</p>
          <h1>First-pass review</h1>
          <p className="subtle">AI drafts the first pass. You review each step and sign. Nothing is signed without you.</p>
        </div>

        {authRequired && (
          <button className="sign-out-button" type="button" onClick={handleSignOut}>
            Sign out
          </button>
        )}

        <section className="sidebar-case-card" aria-label="Patient summary">
          <div>
            <span className="case-avatar">{caseData.patient.name.split(" ").map((part) => part[0]).join("")}</span>
            <div>
              <strong>{caseData.patient.name}</strong>
              <small>{caseData.patient.age}{caseData.patient.sex} / {caseData.patient.id}</small>
            </div>
          </div>
          <span className={`urgency-chip ${urgency}`}>{urgency}</span>
        </section>

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
          <div className={`urgency-badge ${urgency}`}>{urgency}</div>
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
              {reviewedSteps.has(currentStep)
                ? `Next: ${nextStep.label} →`
                : `Mark reviewed · ${nextStep.label} →`}
            </button>
          ) : (
            <span className="step-final-hint">Review the evidence, then sign the letter to complete the first pass.</span>
          )}
        </footer>
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

function CaseIntakePanel({ patient, status, onUpload, urgency }) {
  return (
    <section className="support-panel intake-panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Case intake</p>
          <h3>Upload source</h3>
        </div>
        <span className={`urgency-badge ${urgency}`}>{urgency}</span>
      </div>

      <div className="intake-grid">
        <label className="drop-zone">
          <span>Drop lab, scan, or note</span>
          <small>{status || "Ready for clinical source upload"}</small>
          <input type="file" onChange={onUpload} />
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
    </section>
  );
}
