"""Shared patient store (SQLite, stdlib only).

One small table holds the synthetic patients a clinician picks between, plus any
chest X-ray they've uploaded and its cached imaging read — so when a patient is
re-opened, their scan is already there. PHI note: synthetic data only; data/ is
gitignored.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from app.config import settings

# data/ lives next to the uploads dir; both are gitignored.
_DATA_DIR = Path(settings.upload_dir).parent
_DB_PATH = _DATA_DIR / "clinic.db"
XRAY_DIR = _DATA_DIR / "xrays"


def connect() -> sqlite3.Connection:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


_SCHEMA = """
CREATE TABLE IF NOT EXISTS patients (
    id            TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    age           INTEGER,
    sex           TEXT,
    summary       TEXT,
    lab_text      TEXT,
    xray_path     TEXT,
    imaging_draft TEXT,
    created_at    TEXT DEFAULT CURRENT_TIMESTAMP
);
"""

# Synthetic patients, tuned so lab triage yields a spread of acuity levels:
#   immediate (L1) from a critical value, urgent (L3) from other abnormals,
#   non-urgent (L5) when everything is in range.
_SEED: list[dict] = [
    {
        "id": "PX-1048", "name": "Aisha Tan", "age": 58, "sex": "F",
        "summary": "58F, 2 weeks of fatigue, exertional dyspnoea, intermittent chest tightness, poorly controlled diabetes.",
        "lab_text": "Haemoglobin 8.9 g/dL\nMCV 72 fL\nWBC 6.2 10^9/L\nPlatelets 280 10^9/L\nPotassium 4.1 mmol/L\nCreatinine 78 umol/L",
        "xray": True,
        "imaging_draft": {
            "modality": "Chest X-Ray",
            "findings": ["Mild cardiomegaly without focal consolidation.",
                         "No pleural effusion or pneumothorax on preliminary review."],
            "possible_diagnoses": [
                {"condition": "Cardiomegaly / early cardiac strain",
                 "rationale": "Enlarged cardiac silhouette on a background of exertional dyspnoea and anaemia.",
                 "confidence": "medium"},
                {"condition": "High-output state from anaemia",
                 "rationale": "Low haemoglobin can enlarge the cardiac shadow without primary heart disease.",
                 "confidence": "low"},
            ],
            "limitations": ["Preliminary AI read; clinician correlation required."],
            "impression": "Mild cardiomegaly. Correlate clinically for anaemia-related symptoms and cardiac risk.",
            "urgency": "urgent",
        },
    },
    {
        "id": "PX-2091", "name": "Marcus Lee", "age": 67, "sex": "M",
        "summary": "67M, nausea and reduced urine output on a background of chronic kidney disease.",
        "lab_text": "Potassium 6.9 mmol/L\nCreatinine 320 umol/L\nUrea 28 mmol/L\nSodium 133 mmol/L\nHaemoglobin 11.2 g/dL",
        "xray": False, "imaging_draft": None,
    },
    {
        "id": "PX-3320", "name": "Priya Nair", "age": 34, "sex": "F",
        "summary": "34F, 3 months of tiredness, cold intolerance and mild weight gain.",
        "lab_text": "TSH 9.8 mIU/L\nFree T4 8.0 pmol/L\nALT 70 U/L\nHaemoglobin 12.8 g/dL",
        "xray": False, "imaging_draft": None,
    },
    {
        "id": "PX-4102", "name": "Daniel Ong", "age": 45, "sex": "M",
        "summary": "45M, routine pre-employment health screen. Asymptomatic.",
        "lab_text": "Haemoglobin 15.0 g/dL\nWBC 6.5 10^9/L\nPlatelets 250 10^9/L\nPotassium 4.2 mmol/L\nSodium 140 mmol/L\nCreatinine 88 umol/L",
        "xray": False, "imaging_draft": None,
    },
    {
        "id": "PX-5567", "name": "Sofia Garcia", "age": 72, "sex": "F",
        "summary": "72F, progressive fatigue and easy bruising over 6 weeks.",
        "lab_text": "Haemoglobin 7.8 g/dL\nPlatelets 90 10^9/L\nWBC 2.8 10^9/L\nMCV 105 fL",
        "xray": True,
        "imaging_draft": {
            "modality": "Chest X-Ray",
            "findings": ["Clear lung fields. No focal consolidation or effusion."],
            "possible_diagnoses": [
                {"condition": "No acute cardiopulmonary process",
                 "rationale": "Clear lung fields with a normal cardiac silhouette on preliminary review.",
                 "confidence": "high"},
            ],
            "limitations": ["Preliminary AI read; clinician correlation required."],
            "impression": "No acute cardiopulmonary abnormality on preliminary review.",
            "urgency": "non-urgent",
        },
    },
]


def init_db() -> None:
    """Create the schema and seed synthetic patients on first run."""
    conn = connect()
    try:
        conn.executescript(_SCHEMA)
        already = conn.execute("SELECT COUNT(*) AS n FROM patients").fetchone()["n"]
        if not already:
            _seed(conn)
        conn.commit()
    finally:
        conn.close()


def _seed(conn: sqlite3.Connection) -> None:
    XRAY_DIR.mkdir(parents=True, exist_ok=True)
    for p in _SEED:
        xray_path = None
        if p.get("xray"):
            xray_path = str(XRAY_DIR / f"{p['id']}.png")
            _make_synthetic_xray(xray_path)
        conn.execute(
            "INSERT INTO patients (id, name, age, sex, summary, lab_text, xray_path, imaging_draft)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (p["id"], p["name"], p["age"], p["sex"], p["summary"], p["lab_text"],
             xray_path, json.dumps(p["imaging_draft"]) if p.get("imaging_draft") else None),
        )


def _make_synthetic_xray(path: str) -> None:
    """Draw a plausible synthetic chest X-ray (no real PHI)."""
    try:
        from PIL import Image, ImageDraw
    except Exception:
        Path(path).write_bytes(b"")  # tolerate missing Pillow; UI shows empty
        return
    w, h = 480, 560
    img = Image.new("L", (w, h), 12)
    d = ImageDraw.Draw(img)
    d.ellipse([110, 150, 235, 430], fill=42)   # right lung
    d.ellipse([245, 150, 370, 430], fill=42)   # left lung
    d.rectangle([232, 120, 248, 470], fill=120)  # spine
    for i in range(7):                            # ribs
        y = 160 + i * 40
        d.arc([120, y - 24, 360, y + 64], 200, 340, fill=165, width=3)
    img.save(path)
