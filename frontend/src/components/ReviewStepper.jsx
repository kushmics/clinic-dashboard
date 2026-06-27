// Guided review rail. Shows the five-step first-pass flow, current position,
// which steps the clinician has reviewed, and the urgency each step surfaced.
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
                {urgency && <span className={`step-urgency ${urgency}`}>{urgency}</span>}
              </button>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
