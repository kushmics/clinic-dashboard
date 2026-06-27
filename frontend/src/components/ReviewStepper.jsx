import { ACUITY } from "../acuity.js";

// Guided review rail. Shows the five-step first-pass flow, current position,
// which steps the clinician has reviewed, and the acuity each step surfaced.
// Steps are clickable (guided + free jump).
export default function ReviewStepper({ steps, currentStep, reviewedSteps, urgencyByStep, onJump }) {
  const activeIndex = steps.findIndex((s) => s.id === currentStep);

  return (
    <nav className="review-stepper" aria-label="Review progress">
      <ol>
        {steps.map((step, index) => {
          const isActive = step.id === currentStep;
          const isReviewed = reviewedSteps.has(step.id);
          const urgency = urgencyByStep[step.id];
          const acuity = urgency ? ACUITY[urgency] : null;
          const state = isActive ? "active" : isReviewed ? "done" : index < activeIndex ? "done" : "upcoming";

          return (
            <li
              key={step.id}
              className={`step ${state}${urgency ? ` u-${urgency}` : ""}`}
            >
              <button type="button" onClick={() => onJump(step.id)} aria-current={isActive ? "step" : undefined}>
                <span className="step-marker">{isReviewed && !isActive ? "✓" : step.n}</span>
                <span className="step-text">
                  <small>Step {step.n}</small>
                  <strong>{step.label}</strong>
                </span>
                {acuity && <span className={`step-urgency ${urgency}`} title={acuity.label}>L{acuity.level}</span>}
              </button>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
