"""Stage 1 — extraction: messy input -> normalized measurements + patient context.

This is the ONLY place an LLM is allowed to touch the data, and only to read it
into a structured, checkable artifact (decision: extraction and triage are two
stages with an inspectable list of measurements between them). The LLM never
flags, scores, or decides severity — that is the deterministic triage stage.

Order of preference:
  1. Input already structured as JSON  -> parse directly (no model).
  2. Plain-ish text with value lines     -> deterministic regex parse (no model).
  3. Nothing parsed, or a photo/scan     -> OpenAI (sponsor) vision/text extract,
                                            only if a key is configured.
"""
from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass, field

from app.config import settings


@dataclass
class Measurement:
    label: str
    value: float | None          # numeric value, None if non-numeric
    raw_value: str               # as printed, e.g. ">25.0"
    unit: str | None = None
    printed_low: float | None = None
    printed_high: float | None = None
    printed_range: str | None = None
    source_text: str = ""        # the original line, for verification


@dataclass
class Extraction:
    measurements: list[Measurement] = field(default_factory=list)
    context: dict = field(default_factory=dict)   # {sex, sex_source, age, age_source}
    method: str = "none"                           # json | regex | openai | none
    notes: list[str] = field(default_factory=list)


# ----------------------------------------------------------------- patient ctx
_SEX_RE = re.compile(r"\b(?:sex|gender)\s*[:=]?\s*(male|female|m|f)\b", re.I)
_AGE_RE = re.compile(r"\bage\s*[:=]?\s*(\d{1,3})\b", re.I)


def _extract_context(text: str) -> dict:
    ctx: dict = {}
    m = _SEX_RE.search(text)
    if m:
        raw = m.group(1).lower()
        ctx["sex"] = "male" if raw in ("m", "male") else "female"
        ctx["sex_source"] = "report"
    a = _AGE_RE.search(text)
    if a:
        ctx["age"] = int(a.group(1))
        ctx["age_source"] = "report"
    return ctx


# ----------------------------------------------------------------- regex parse
# One value line. Label (letters first), value (optional < >), optional unit
# (must start with a letter or %), optional printed range, optional H/L flag char.
_LINE_RE = re.compile(
    r"^\s*"
    r"(?P<label>[A-Za-z][A-Za-z0-9 ()/,.\-+'µ]*?)"
    r"\s*[:=]?\s+"
    r"(?P<value>[<>]?=?\s?-?\d+(?:\.\d+)?)"
    r"\s*"
    r"(?P<unit>%|[A-Za-zµ][A-Za-zµ°/^*0-9·\-]*)?"
    r"\s*"
    r"(?:[\(\[]\s*(?P<low>-?\d+(?:\.\d+)?)\s*[-–—]+\s*(?P<high>-?\d+(?:\.\d+)?)\s*[\)\]]"
    r"|(?P<low2>-?\d+(?:\.\d+)?)\s*[-–—]\s*(?P<high2>-?\d+(?:\.\d+)?))?"
    r"\s*(?P<flag>[HL*]{1,2})?\s*$"
)

# Lines that look like a value line but are not analytes.
_SKIP_LABELS = {
    "age", "sex", "gender", "name", "patient", "date", "dob", "nric", "id",
    "tel", "phone", "mrn", "ward", "bed", "page", "ref", "report", "collected",
    "received", "printed", "time", "doctor", "dr", "lab", "no",
}


def _to_float(token: str) -> float | None:
    cleaned = token.replace(" ", "").lstrip("<>=")
    try:
        return float(cleaned)
    except ValueError:
        return None


def parse_text(text: str) -> Extraction:
    """Deterministic parse: JSON if it is JSON, else line-by-line regex."""
    stripped = text.strip()

    # Path 1: structured JSON input (from an upstream extractor or API caller).
    if stripped[:1] in "[{":
        try:
            return _from_json(json.loads(stripped))
        except (json.JSONDecodeError, KeyError, TypeError):
            pass  # fall through to regex

    # Path 2: regex line parse.
    ex = Extraction(method="regex", context=_extract_context(text))
    for line in text.splitlines():
        if not line.strip():
            continue
        m = _LINE_RE.match(line)
        if not m:
            continue
        label = m.group("label").strip(" :-\t")
        if not label or label.lower() in _SKIP_LABELS or len(label) < 2:
            continue
        raw = m.group("value").replace(" ", "")
        low = m.group("low") or m.group("low2")
        high = m.group("high") or m.group("high2")
        ex.measurements.append(Measurement(
            label=label,
            value=_to_float(raw),
            raw_value=raw,
            unit=(m.group("unit") or None),
            printed_low=_to_float(low) if low else None,
            printed_high=_to_float(high) if high else None,
            printed_range=(f"{low}–{high}" if low and high else None),
            source_text=line.strip(),
        ))
    return ex


def _from_json(obj, source: str = "provided") -> Extraction:
    """Accept [{analyte,value,unit,low,high}] or {patient:{}, measurements:[]}.

    `source` tags sex/age provenance: 'report' when read off the report by the
    vision extractor, 'provided' when a caller passed structured context.
    """
    if isinstance(obj, dict):
        rows = obj.get("measurements") or obj.get("results") or []
        patient = obj.get("patient") or obj.get("context") or {}
    else:
        rows, patient = obj, {}
    ctx: dict = {}
    if patient.get("sex"):
        s = str(patient["sex"]).lower()
        ctx["sex"] = "male" if s in ("m", "male") else "female"
        ctx["sex_source"] = source
    if patient.get("age") is not None:
        ctx["age"] = patient["age"]
        ctx["age_source"] = source

    ms = []
    for r in rows:
        label = r.get("analyte") or r.get("label") or r.get("name") or ""
        if not label:
            continue
        val = r.get("value")
        try:
            fval = float(val)
        except (TypeError, ValueError):
            fval = None
        low, high = r.get("low") or r.get("ref_low"), r.get("high") or r.get("ref_high")
        ms.append(Measurement(
            label=str(label), value=fval, raw_value=str(val),
            unit=r.get("unit"),
            printed_low=float(low) if low is not None else None,
            printed_high=float(high) if high is not None else None,
            printed_range=(f"{low}–{high}" if low is not None and high is not None else None),
            source_text=json.dumps(r, ensure_ascii=False),
        ))
    return Extraction(measurements=ms, context=ctx, method="json")


# --------------------------------------------------------------- OpenAI (opt-in)
_OPENAI_SYSTEM = (
    "You are a lab-report data extractor. Read the report (text or image) and "
    "return ONLY JSON of the form "
    '{"patient": {"sex": "male|female|null", "age": <int|null>}, '
    '"measurements": [{"analyte": str, "value": <number|string>, "unit": str|null, '
    '"low": <number|null>, "high": <number|null>}]}. '
    "Transcribe every measured analyte and its printed reference range exactly as "
    "shown. Do NOT flag, interpret, diagnose, or decide whether a value is normal. "
    "If a value is unreadable, include it with the raw text as the value."
)


def _openai_available() -> bool:
    return bool(getattr(settings, "openai_api_key", None))


def extract_with_openai(text: str = "", image_path: str | None = None) -> Extraction:
    """Sponsor path: GPT vision/text extraction into the same Measurement shape."""
    if not _openai_available():
        return Extraction(method="none", notes=["OpenAI key not configured"])
    try:
        from openai import OpenAI
    except ImportError:
        return Extraction(method="none", notes=["openai package not installed"])

    client = OpenAI(api_key=settings.openai_api_key, timeout=60, max_retries=2)
    content: list[dict] = []
    if text.strip():
        content.append({"type": "text", "text": text})
    if image_path:
        if image_path.lower().endswith(".pdf"):
            try:
                content.extend(_pdf_image_parts(image_path))
            except ImportError:
                return Extraction(method="none",
                                  notes=["scanned PDF needs PyMuPDF — pip install pymupdf"])
        else:
            b64, mime = _encode_image(image_path)
            content.append({"type": "image_url",
                            "image_url": {"url": f"data:{mime};base64,{b64}"}})
    if not content:
        content.append({"type": "text", "text": "(no content)"})

    try:
        resp = client.chat.completions.create(
            model=settings.openai_model,
            messages=[{"role": "system", "content": _OPENAI_SYSTEM},
                      {"role": "user", "content": content}],
            response_format={"type": "json_object"},
        )
        payload = json.loads(resp.choices[0].message.content)
    except Exception as e:  # network, timeout, auth, bad model, malformed JSON
        return Extraction(method="none",
                          notes=[f"OpenAI extraction failed: {type(e).__name__}: {str(e)[:200]}"])
    ex = _from_json(payload, source="report")  # vision read these off the report
    ex.method = "openai"
    return ex


def _pdf_image_parts(path: str, max_pages: int = 8) -> list[dict]:
    """Render PDF pages to PNG image parts for the vision model (scanned PDFs).
    Caps at max_pages and logs nothing silently — a truncated PDF is rare here."""
    import fitz  # PyMuPDF — pip-only, no system binary
    parts: list[dict] = []
    with fitz.open(path) as doc:
        for i, page in enumerate(doc):
            if i >= max_pages:
                break
            pix = page.get_pixmap(dpi=150)
            b64 = base64.b64encode(pix.tobytes("png")).decode()
            parts.append({"type": "image_url",
                          "image_url": {"url": f"data:image/png;base64,{b64}"}})
    return parts


def _encode_image(image_path: str) -> tuple[str, str]:
    """Base64-encode, downscaling large photos (cuts vision cost + latency).
    Falls back to the raw bytes if Pillow isn't installed."""
    raw = open(image_path, "rb").read()
    try:
        import io

        from PIL import Image
        im = Image.open(io.BytesIO(raw)).convert("RGB")
        longest = max(im.size)
        if longest > 1600:
            scale = 1600 / longest
            im = im.resize((round(im.width * scale), round(im.height * scale)))
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=85)
        return base64.b64encode(buf.getvalue()).decode(), "image/jpeg"
    except Exception:
        ext = image_path.rsplit(".", 1)[-1].lower()
        return base64.b64encode(raw).decode(), ("image/png" if ext == "png" else "image/jpeg")


# --------------------------------------------------------------------- facade
def extract(text: str = "", image_path: str | None = None,
            prefer_openai: bool = False) -> Extraction:
    """Deterministic-first extraction with optional OpenAI fallback.

    - A photo/scan (image_path, no text) needs the model: use OpenAI if available.
    - Text is parsed deterministically; if that yields nothing and a key exists,
      fall back to OpenAI on the raw text.
    """
    if image_path and not text.strip():
        ex = extract_with_openai(text=text, image_path=image_path)
        if not ex.measurements:
            ex.notes.append("image supplied but no measurements extracted "
                            "(configure OPENAI_API_KEY for photo/scan input)")
        return ex

    if prefer_openai and _openai_available():
        ex = extract_with_openai(text=text, image_path=image_path)
        if ex.measurements:
            return ex

    ex = parse_text(text)
    if not ex.measurements and _openai_available():
        fallback = extract_with_openai(text=text, image_path=image_path)
        if fallback.measurements:
            return fallback
        ex.notes.extend(fallback.notes)
    return ex
