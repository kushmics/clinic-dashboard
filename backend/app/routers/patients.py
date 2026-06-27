"""Shared patient directory: pick a patient, load their first-pass context.

A patient carries demographics, a lab report (triaged on the fly), and any chest
X-ray they've uploaded plus its cached imaging read. Selecting a patient returns
everything the dashboard needs to resume review where it left off.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app import acuity, db
from app.skills.imaging_report.skill import ImagingReportSkill
from app.skills.lab_triage.skill import LabTriageSkill
from app.skills.base import SkillInput

router = APIRouter(prefix="/patients", tags=["patients"])

_lab_skill = LabTriageSkill()
_imaging_skill = ImagingReportSkill()

_SEX = {"F": "female", "M": "male"}


def _get(conn: sqlite3.Connection, patient_id: str) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM patients WHERE id = ?", (patient_id,)).fetchone()
    if row is None:
        raise HTTPException(404, f"unknown patient: {patient_id}")
    return row


def _lab_draft(row: sqlite3.Row) -> dict | None:
    if not row["lab_text"]:
        return None
    ctx = {"sex": _SEX.get(row["sex"], row["sex"]), "age": row["age"]}
    return _lab_skill.run(SkillInput(text=row["lab_text"], context=ctx)).draft


def _imaging_draft(row: sqlite3.Row) -> dict | None:
    return json.loads(row["imaging_draft"]) if row["imaging_draft"] else None


def _acuity(lab: dict | None, imaging: dict | None) -> str | None:
    return acuity.most_acute([
        (lab or {}).get("urgency"),
        (imaging or {}).get("urgency"),
    ])


@router.get("")
def list_patients() -> dict:
    conn = db.connect()
    try:
        rows = conn.execute("SELECT * FROM patients ORDER BY name").fetchall()
        out = []
        for r in rows:
            lab = _lab_draft(r)
            imaging = _imaging_draft(r)
            out.append({
                "id": r["id"], "name": r["name"], "age": r["age"], "sex": r["sex"],
                "summary": r["summary"], "has_xray": bool(r["xray_path"]),
                "urgency": _acuity(lab, imaging),
            })
        return {"patients": out}
    finally:
        conn.close()


@router.get("/{patient_id}")
def get_patient(patient_id: str) -> dict:
    conn = db.connect()
    try:
        row = _get(conn, patient_id)
        lab = _lab_draft(row)
        imaging = _imaging_draft(row)
        return {
            "id": row["id"], "name": row["name"], "age": row["age"], "sex": row["sex"],
            "summary": row["summary"],
            "lab_draft": lab,
            "imaging_draft": imaging,
            "has_xray": bool(row["xray_path"]),
            "xray_url": f"/patients/{row['id']}/xray" if row["xray_path"] else None,
            "urgency": _acuity(lab, imaging),
        }
    finally:
        conn.close()


@router.get("/{patient_id}/xray")
def get_xray(patient_id: str) -> FileResponse:
    conn = db.connect()
    try:
        row = _get(conn, patient_id)
        path = row["xray_path"]
    finally:
        conn.close()
    if not path or not Path(path).exists():
        raise HTTPException(404, "no X-ray on file for this patient")
    return FileResponse(path, media_type="image/png")


@router.post("/{patient_id}/xray")
async def upload_xray(patient_id: str, file: UploadFile) -> dict:
    conn = db.connect()
    try:
        row = _get(conn, patient_id)
        db.XRAY_DIR.mkdir(parents=True, exist_ok=True)
        dest = db.XRAY_DIR / f"{patient_id}.png"
        dest.write_bytes(await file.read())

        result = _imaging_skill.run(SkillInput(
            image_path=str(dest),
            context={"modality_hint": "xray", "patient": dict(row)},
        ))
        draft = result.draft
        conn.execute(
            "UPDATE patients SET xray_path = ?, imaging_draft = ? WHERE id = ?",
            (str(dest), json.dumps(draft), patient_id),
        )
        conn.commit()
        return {"draft": draft, "xray_url": f"/patients/{patient_id}/xray"}
    finally:
        conn.close()
