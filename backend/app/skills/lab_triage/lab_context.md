# Lab Triage — Design Context

Everything decided while designing the `lab_triage` skill. Read this before
implementing. This is the "why," not just the "what."

## Guiding principle

> **Lose no information, judge nothing.** Extract everything, sort and surface it
> against *cited* thresholds so a human processes it faster.

The only place an LLM is allowed to touch a clinical value is rephrasing
**already-flagged facts** into plain language. Every flag, range, and sort is a
deterministic lookup against a published Singapore reference table — never an LLM
opinion. We automate what a doctor does trivially/tediously (reading a messy
report, eyeballing values against ranges); we never make a call the doctor
should make. Interpretation is `differential_dx`'s job, not ours.

## How real hospital lab triage works (the SOP we follow)

Researched from primary sources. The lab **flags first and proceeds — it never
blocks waiting for clinical context.** Three automated layers:

1. **Autoverification** (CAP/CLIA) — the lab system auto-checks every result
   against rules + reference ranges; normals auto-release, abnormals are held for
   review. Reference ranges are **age/sex-partitioned in the system**; age/sex
   come from registration, not re-typed per result.
2. **Delta checks** (ARUP) — each result is auto-compared to the patient's
   **previous** result; a change beyond a biological limit is flagged. Catches
   real deterioration *and* lab errors (wrong tube, mislabeled sample). → trend
   is standard practice, not optional.
3. **Critical-value notification** (Joint Commission / CAP) — a defined list of
   life-threatening values triggers an **immediate mandatory phone call with
   read-back**, within hard timeframes (one study: 15 min ED / 45 min inpatient /
   480 min outpatient). A tier *above* "abnormal."

**Our stance:** mirror layers 1–2 deterministically; consciously scope *out* the
layer-3 active-paging backstop (see Open Items). We are a convenience layer for
small clinics/polyclinics, not a replacement for hospital LIS.

## Data sources (cited, Singapore-specific, no hand-tuning)

Reference numbers come from these — we transcribe/scrape, we do not invent bands.

### SGH — Critical Test Results and Laboratory Values
https://www.sgh.com.sg/our-specialties/pathology/pathology-lab-services/critical-test-results-and-laboratory-values

Drives the top of the sort. Sample (Clinical Biochemistry + Haematology):

| Test | Critical | Units |
|---|---|---|
| Potassium | < 2.5 or > 5.7 | mmol/L |
| Sodium | < 120 or > 160 | mmol/L |
| Calcium | < 1.75 or > 3.25 | mmol/L |
| Glucose | < 2.5 or > 25.0 | mmol/L |
| Calcium, ionised | < 0.80 or > 1.60 | mmol/L |
| Haemoglobin (adult) | < 6.0 or > 20.0 | g/dL |
| WBC | < 1.0 or > 50.0 | ×10⁹/L |
| Platelets | < 20 or > 800 | ×10⁹/L |
| APTT | > 100 | seconds |
| INR | > 5.0 | — |
| Fibrinogen | < 0.9 or > 7.8 | g/L |

Also lists drug levels (digoxin, lithium, phenytoin, vancomycin…), blood-gas pH,
neonatal bilirubin, and qualitative criticals (malaria positive, new leukaemia).
Note: mostly **single thresholds, not age/sex-partitioned** (a few neonatal
exceptions).

### NUH — Test Catalog (reference ranges)
https://nuhsingapore.testcatalog.org/  (e.g. /show/FBC)

Per-test pages giving **sex-partitioned adult ranges, age-banded paediatric
ranges, units, LOINC codes, and alias lists**. Example (FBC, adults):

| Param | Male | Female | Unit | LOINC |
|---|---|---|---|---|
| HB | 13.1–16.8 | 11.5–14.9 | g/dL | 718-7 |
| WBC | 4.30–10.40 | 4.30–10.40 | ×10⁹/L | 6690-2 |
| PLT | 150–410 | 150–410 | ×10⁹/L | 777-3 |

Aliases on the FBC page: `CBC`, `Complete Blood Count`, `HB`, `Haemoglobin`, …
→ this is our analyte-identity dictionary, **for free**.

Literature confirms local/ethnic FBC ranges genuinely differ (Malaysian
multiethnic study; Han Chinese CBC intervals) — so using Singapore ranges is more
correct, not just convenient.

## Design decisions (locked)

| # | Topic | Decision |
|---|---|---|
| 1 | Input | Accept any form (structured/PDF/photo/free-text). **Extraction is a separate upstream stage** → normalized values + source kept for verification. Triage assumes normalized input. |
| 2 | Analyte identity | extracted label → alias → **LOINC**, from NUH catalog. |
| 3 | Reference ranges | NUH (sex/age-partitioned). Prefer the report's printed range when present; fall back to NUH. |
| 4 | Critical thresholds | SGH table. Drives top-of-sort. |
| 5 | Patient context | Auto-extract age/sex from report, else prompt. Until known, triage anyway but mark flags **"provisional — assumed adult."** Never silently default. |
| 6 | Trend | Snapshot for demo, **built to accept priors** via `context`; output states "no prior result for delta comparison." |
| 7 | Urgency | **Flat** (routine/soon/urgent). |
| 8 | Ranking | Deterministic **never-miss surfacing**: SGH-critical → outside-NUH-range → normal. **No LLM severity.** |
| 9 | Unknowns / unit mismatch | **Surface as "extracted but not assessed — no range on file."** Never drop, never let the LLM guess. Normalize units to SI when recognized; if not, route to the unassessed bucket. |
| 10 | Summary & scope | `summary` = **facts-only roll-up** (counts by tier + most-out-of-range values w/ cited thresholds). LLM may only restate flagged facts. **All interpretation → `differential_dx`.** |

## Scope boundary

- **lab_triage (this skill):** descriptive only. *"Here's what's abnormal, how far
  out, sorted, against these cited thresholds."*
- **differential_dx (Track C):** consumes our structured output via
  `SkillInput.context` and interprets / offers options. No duplication.

Example of the line:
- ✅ *"K 6.5 (critical, SGH >5.7); Creatinine 210 (above NUH range)."*
- ❌ *"Suggests acute kidney injury with hyperkalemia."* ← that's Track C.

## Schema changes needed

Current `schema.json` has only `abnormals / urgency / summary`. Add:
- `assumptions` / `context_used` — records provisional age/sex (decision 5).
- `unassessed` — extracted-but-no-range items (decision 9), kept separate from
  `abnormals`, never flagged normal/abnormal.
- per-abnormal `threshold_source` — which cited table fired (SGH vs NUH) + the
  value, for the audit trail.

## Open items / deferred

- **Critical-value active backstop** (paging/SMS) — out of scope for the build;
  flat urgency accepts this. Revisit; matters most in polyclinics with no LIS.
- **Units** — SI assumed (Singapore). Non-SI inputs need a normalization step;
  unrecognized units → unassessed bucket.
- **Trend/delta** — design the seam now, populate when a prior-results source
  exists.
- **AI approach** — default is OpenAI (sponsor) for extraction + summary prose;
  the model never decides severity. Keep extraction and triage as two stages with
  a checkable artifact between them.

## Build tasks (bounded, delegatable)

1. Scrape ~15 NUH panel pages (FBC, U/E/Cr, LFT, glucose, lipids, TFT, …) +ranges,
   LOINC, aliases → `reference_data/ranges.json`.
2. Transcribe the SGH critical table → `reference_data/critical_values.json`.
3. Update `schema.json` per above.
4. Implement deterministic flag+sort against the two tables; wire OpenAI only for
   extraction and facts-only summary prose.

## Implementation status (built)

All four build tasks are implemented. Map of the skill:

- `reference_data/critical_values.json` (SGH) + `ranges.json` (NUH) — cited tables.
  A seeded set ships now; expanded by scraping the source pages. Add panels by
  appending in the same shape — no code change.
- `reference.py` — table load (cached), alias→canonical→LOINC resolution, unit
  normalization (no magnitude conversion), sex/age range selection (narrowest
  envelope when sex unknown → conservative).
- `extraction.py` — Stage 1. Deterministic JSON/regex parse first; OpenAI
  vision/text (`OPENAI_API_KEY`) only as fallback / for photos. Pulls age/sex
  from the report header. Output = inspectable `Measurement` list.
- `triage.py` — Stage 2. Deterministic: critical (SGH) → printed range, else NUH
  → unassessed. Never-miss sort, flat urgency, facts-only summary. No LLM.
- `skill.py` — wires the two stages; `signed` never set.
- `schema.json` — adds `unassessed`, `normals`, `assumptions`, `context_used`,
  per-flag `threshold_source` + `provisional` + `delta`.

Front door: `POST /ingestion/upload` (file + optional `sex`/`age`) stores, extracts,
runs triage, returns the draft. Generic path: `POST /engine/run/lab_triage` with
`{text, image_path, context}`. Frontend: `panels/LabTriagePanel.jsx`.

Verify (no network / no key):  `.venv/bin/python tests/test_lab_triage.py`  (10 cases).

Still open: OpenAI extraction path needs a key + live test on a real photo/scan;
delta/trend seam exists but no prior-results source is wired yet.
