Lab-triage extraction prompt (Stage 1 only).

This prompt is used ONLY for the extraction stage — turning a messy lab report
(photo, scan, PDF text, or free text) into structured measurements. It is fed to
the vision/text model when deterministic parsing is not enough.

The model's ONE job is to TRANSCRIBE. It must not flag, score, interpret,
diagnose, or decide whether anything is normal — all of that happens
deterministically downstream against cited SGH/NUH reference tables, never by an
LLM (see lab_context.md, "Lose no information, judge nothing").

Return ONLY JSON of this shape:

```json
{
  "patient": { "sex": "male|female|null", "age": <int|null> },
  "measurements": [
    { "analyte": "Potassium", "value": 6.5, "unit": "mmol/L", "low": 3.5, "high": 5.1 }
  ]
}
```

Rules:
- Transcribe EVERY measured analyte, plus the printed reference range (low/high)
  exactly as shown on the report. Use null for low/high when none is printed.
- Copy units verbatim. Do not convert magnitudes or normalize units.
- If a value is unreadable, include the analyte with the raw text as `value`.
- Extract sex/age only if the report states them; otherwise null. Never infer.
- No commentary, no flags, no interpretation. JSON only.

Downstream (deterministic, not this prompt): critical-value screen against the
SGH critical table, reference-range screen (report's printed range first, else
NUH catalog), never-miss sort, and a facts-only summary. The clinician reviews
and signs; differential_dx does the interpreting.
