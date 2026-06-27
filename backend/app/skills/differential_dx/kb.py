from __future__ import annotations
import json, re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DIR = Path(__file__).parent / 'kb'

@dataclass
class Lab:
    code: str
    name: str
    units: str
    low: float | None = None
    high: float | None = None
    uln: float | None = None
    critical_low: float | None = None
    critical_high: float | None = None
    parse: list[str] | None = None

class KB:
    def __init__(self) -> None:
        self.labs: dict[str, Lab] = {}
        self.conditions: list[dict[str, Any]] = []
        self.red_flags: list[dict[str, Any]] = []
    @classmethod
    def load(cls) -> 'KB':
        kb = cls()
        labs = json.loads((DIR / 'labs.json').read_text(encoding='utf-8-sig'))
        for item in labs.get('labs', []):
            kb.labs[item['code']] = Lab(**item)
        kb.conditions = json.loads((DIR / 'conditions.json').read_text(encoding='utf-8-sig')).get('conditions', [])
        kb.red_flags = json.loads((DIR / 'red_flags.json').read_text(encoding='utf-8-sig')).get('red_flags', [])
        return kb

LAB_VALUE_RE = re.compile(r"(?P<name>[A-Za-z][A-Za-z+ ]{0,30})\s*[:]??\s*(?P<val>[-+]?(?:\d+\.?\d*|\.\d+))\s*(?P<unit>[/A-Za-z0-9^%μm\.]+)?", re.IGNORECASE)

def _match_lab_name(token: str, kb: KB) -> str | None:
    t = token.strip().lower()
    for code, lab in kb.labs.items():
        names = [lab.name.lower()] + [*(lab.parse or [])]
        if any(t == n.lower() for n in names):
            return code
    return None

def parse_labs_from_text(text: str, kb: KB) -> dict[str, dict[str, Any]]:
    found: dict[str, dict[str, Any]] = {}
    for m in LAB_VALUE_RE.finditer(text):
        name = m.group('name').strip()
        code = _match_lab_name(name, kb)
        if not code:
            continue
        try:
            val = float(m.group('val'))
        except ValueError:
            continue
        unit = (m.group('unit') or '').strip()
        found[code] = {'value': val, 'units': unit}
    return found

def flag_observations(observations: dict[str, dict[str, Any]], kb: KB, context: dict | None = None) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for code, obs in observations.items():
        lab = kb.labs.get(code)
        if not lab:
            continue
        val = obs['value']
        flag = 'normal'
        fold = None
        if lab.low is not None and val < lab.low:
            flag = 'low'
        if lab.high is not None and val > lab.high:
            flag = 'high'
        if lab.uln and val and lab.uln > 0:
            fold = val / lab.uln
        out[code] = {"value": val,
            "units": (obs.get("units") or lab.units or "").rstrip(" .;,"),
            "flag": flag,
            "fold_over_uln": fold}
    return out

def evaluate_red_flags(obs: dict[str, dict[str, Any]], kb: KB) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    for rule in kb.red_flags:
        r = rule.get('rule', {})
        if r.get('lab') and r.get('op') in {'ge', 'gt', 'le', 'lt', 'fold_ge'}:
            code = r['lab']
            if code in obs:
                v = obs[code]['value']
                if r['op'] == 'ge' and v >= r['value']:
                    hits.append(rule)
                if r['op'] == 'gt' and v > r['value']:
                    hits.append(rule)
                if r['op'] == 'le' and v <= r['value']:
                    hits.append(rule)
                if r['op'] == 'lt' and v < r['value']:
                    hits.append(rule)
                if r['op'] == 'fold_ge' and obs[code].get('fold_over_uln') and obs[code]['fold_over_uln'] >= r.get('value', 0):
                    hits.append(rule)
    return hits

def score_conditions(obs: dict[str, dict[str, Any]], kb: KB) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for cond in kb.conditions:
        score = 0.0
        matched: list[str] = []
        edges: dict[str, Any] = cond.get('edges', {})
        for key, weight in edges.items():
            parts = key.split('.')
            if len(parts) < 2:
                continue
            lab_code, feat = parts[0], '.'.join(parts[1:])
            ob = obs.get(lab_code)
            if not ob:
                continue
            if feat in {'low', 'high'} and ob['flag'] == feat:
                score += float(weight)
                matched.append(f"{lab_code}.{feat}")
            if feat == 'normal_or_high' and ob['flag'] in {'normal', 'high'}:
                score += float(weight)
                matched.append(f"{lab_code}.normal_or_high")
            if feat.startswith('fold_gt_') and ob.get('fold_over_uln'):
                try:
                    n = float(feat.replace('fold_gt_', '').replace('x', ''))
                except ValueError:
                    n = None
                if n and ob['fold_over_uln'] > n:
                    score += float(weight)
                    matched.append(f"{lab_code}.fold_gt_{n}x")
        if score > 0:
            results.append({
                'condition': cond['name'],
                'code': cond['code'],
                'score': score,
                'matched': matched,
                'next_steps': cond.get('first_steps', []),
                'citations': cond.get('citations', [])
            })
    results.sort(key=lambda x: x['score'], reverse=True)
    return results
