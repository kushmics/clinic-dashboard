import AcuityBadge from "./AcuityBadge.jsx";

// Sidebar patient switcher. Lists everyone in the shared store with their
// current acuity and whether a scan is on file, sorted most-acute first.
export default function PatientPicker({ patients, selectedId, onSelect, isLoading }) {
  return (
    <section className="patient-picker" aria-label="Patients">
      <div className="patient-picker-head">
        <h3>Patients</h3>
        <span>{patients.length}</span>
      </div>
      {isLoading && patients.length === 0 ? (
        <p className="patient-picker-empty">Loading patients…</p>
      ) : (
        <ul>
          {patients.map((p) => (
            <li key={p.id}>
              <button
                type="button"
                className={p.id === selectedId ? "active" : ""}
                onClick={() => onSelect(p.id)}
                aria-current={p.id === selectedId ? "true" : undefined}
              >
                <span className="patient-row-top">
                  <strong>{p.name}</strong>
                  {p.urgency && <AcuityBadge urgency={p.urgency} />}
                </span>
                <span className="patient-row-sub">
                  {p.age}{p.sex} · {p.id}
                  {p.has_xray && <span className="patient-scan-dot" title="Chest X-ray on file">▣ scan</span>}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
