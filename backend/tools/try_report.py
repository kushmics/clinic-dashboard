"""Quick CLI to test lab_triage on a real report — no server, no frontend.

    .venv/bin/python tools/try_report.py path/to/lab.jpg --sex female --age 40

Accepts a photo (.jpg/.png — uses GPT vision), or a PDF/DOCX/TXT with a text
layer. Uses the OPENAI_API_KEY from your .env. SYNTHETIC reports only — never
real patient data (this is a prototype, not a cleared device).
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.text_processing import route_file
from app.skills.base import SkillInput
from app.skills.lab_triage.skill import LabTriageSkill


def main() -> None:
    ap = argparse.ArgumentParser(description="Test lab_triage on a report file.")
    ap.add_argument("path", help="lab report: .jpg/.png/.pdf/.docx/.txt")
    ap.add_argument("--sex", choices=["male", "female"], help="override if not in report")
    ap.add_argument("--age", type=int, help="override if not in report")
    ap.add_argument("--json", action="store_true", help="print full draft JSON")
    args = ap.parse_args()

    path = str(Path(args.path).expanduser().resolve())
    if not Path(path).exists():
        sys.exit(f"file not found: {path}")

    ctx: dict = {}
    if args.sex:
        ctx["sex"], ctx["sex_source"] = args.sex, "provided"
    if args.age is not None:
        ctx["age"], ctx["age_source"] = args.age, "provided"

    kind, payload = route_file(path)
    if kind == "image":
        tag = "scanned PDF" if path.lower().endswith(".pdf") else "image"
        print(f"→ {tag} input; sending to vision model…")
        skill_input = SkillInput(image_path=payload, context=ctx)
    else:
        print(f"→ extracted {len(payload)} chars of text (no model needed)")
        skill_input = SkillInput(text=payload, context=ctx)

    draft = LabTriageSkill().run(skill_input).draft
    meta = draft.get("meta", {})

    print("\n" + "=" * 60)
    print(f"URGENCY: {draft['urgency'].upper()}   "
          f"(extracted via {meta.get('extraction_method')})")
    for note in meta.get("extraction_notes", []):
        print(f"  ! {note}")
    print("=" * 60)
    print(draft["summary"])

    if draft["abnormals"]:
        print("\nABNORMAL:")
        for a in draft["abnormals"]:
            ts = a["threshold_source"]
            prov = " [provisional]" if a.get("provisional") else ""
            print(f"  • {a['analyte']}: {a['value']} {a['unit'] or ''}  "
                  f"[{a['flag']}]  vs {a.get('reference_range') or '—'}  "
                  f"({ts['table']} {ts['rule']} {ts.get('threshold')}){prov}")
    if draft["unassessed"]:
        print("\nNOT ASSESSED:")
        for x in draft["unassessed"]:
            print(f"  • {x['analyte']}: {x['value']} {x['unit'] or ''} — {x['reason']}")
    if draft["normals"]:
        print(f"\nWITHIN RANGE: {len(draft['normals'])} "
              f"({', '.join(n['analyte'] for n in draft['normals'][:8])}"
              f"{'…' if len(draft['normals']) > 8 else ''})")
    if draft["assumptions"]:
        print("\nASSUMPTIONS:")
        for a in draft["assumptions"]:
            print(f"  • {a}")

    print(f"\ncontext: {draft['context_used']}")
    if args.json:
        print("\n--- full draft ---")
        print(json.dumps(draft, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
