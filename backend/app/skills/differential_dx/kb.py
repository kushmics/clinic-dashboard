from __future__ import annotations
import json, re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

HERE = Path(__file__).parent
RANGES_PATH = HERE.parent / 'lab_triage' / 'reference_data' / 'ranges.json'

@dataclass
class Range:
    sex: str | None = None
    age_min: float | None = None
    age_max: float | None = None
    low: float | None = None
    high: float | None = None

@dataclass
class Lab:
    code: str
    name: str
    unit: str
    aliases: list[str] = field(default_factory=list)
    ranges: list[Range] = field(default_factory=list)

class KB:
    def __init__(self) -> None:
        self.labs: dict[str, Lab] = {}
        self.alias_to_code: dict[str, str] = {}
        self.conditions: list[dict[str, Any]] = []
        self.red_flags: list[dict[str, Any]] = []

    @classmethod
    def load(cls) -> 'KB':
        kb = cls()
        # 1) Load lab reference from lab_triage ranges.json (true source)
        data = json.loads(RANGES_PATH.read_text(encoding='utf-8'))
        analytes = data.get('analytes', {})
        code_map = {
            'haemoglobin': 'hb', 'haematocrit': 'hct', 'mcv': 'mcv', 'wbc': 'wbc', 'platelets': 'plt', 'rbc': 'rbc',
            'sodium': 'na', 'potassium': 'k', 'creatinine': 'creat', 'egfr': 'egfr',
            'alt': 'alt', 'ast': 'ast', 'alkaline_phosphatase': 'alp', 'bilirubin_total': 'tbili', 'albumin': 'alb',
            'tsh': 'tsh', 'free_t4': 'ft4', 'free_t3': 'ft3', 'hba1c': 'hba1c', 'crp': 'crp', 'crp_hs': 'crp'
        }
        for key, meta in analytes.items():
            unit = meta.get('unit') or meta.get('units') or ''
            aliases = list({*(meta.get('aliases') or []), key})
            code = code_map.get(key)
            if not code:
                for a in aliases:
                    t = re.sub(r'[^a-z0-9]+', '', a.lower())
                    if 1 <= len(t) <= 5:
                        code = t; break
                if not code:
                    code = key[:6].lower()
            rngs = [Range(sex=(r.get('sex') or None), age_min=r.get('age_min'), age_max=r.get('age_max'), low=r.get('low'), high=r.get('high')) for r in meta.get('ranges', [])]
            lab = Lab(code=code, name=key.replace('_',' ').title(), unit=unit, aliases=aliases + [code], ranges=rngs)
            kb.labs[code] = lab
            for a in lab.aliases:
                kb.alias_to_code[a.lower()] = code
        # 1b) Fallback: merge extra analytes from local labs.json for missing tests (ALT/AST/ALP/egfr/etc.)
        try:
            local_labs = json.loads((HERE / 'kb' / 'labs.json').read_text(encoding='utf-8'))
        except FileNotFoundError:
            local_labs = {}
        for item in (local_labs.get('labs') or []):
            code = item.get('code')
            if not code or code in kb.labs:
                continue
            unit = item.get('units') or ''
            aliases = list(set((item.get('parse') or []) + [code, item.get('name','')]))
            rngs = [Range(sex='any', age_min=None, age_max=None, low=item.get('low'), high=item.get('high'))]
            lab = Lab(code=code, name=item.get('name') or code.upper(), unit=unit, aliases=aliases, ranges=rngs)
            kb.labs[code] = lab
            for a in aliases:
                if a:
                    kb.alias_to_code[a.lower()] = code
        # 2) Load Track C conditions/red_flags from local KB json
        local_kb_dir = HERE / 'kb'
        kb.conditions = json.loads((local_kb_dir / 'conditions.json').read_text(encoding='utf-8')).get('conditions', [])
        kb.red_flags = json.loads((local_kb_dir / 'red_flags.json').read_text(encoding='utf-8')).get('red_flags', [])
        return kb

LAB_VALUE_RE = re.compile(r"(?P<name>[A-Za-z][A-Za-z +]{0,30})s*:?s*(?P<val>[-+]?[0-9]*.?[0-9]+)s*(?P<unit>[/A-Za-z0-9^%um.]+)?", re.IGNORECASE)

def _match_lab_name(token: str, kb: KB) -> str | None:
    t = token.strip().lower()
    if t in kb.alias_to_code:
        return kb.alias_to_code[t]
    t2 = re.sub(r's+', ' ', t)
    return kb.alias_to_code.get(t2)

def _select_range(lab: Lab, ctx: dict | None) -> Range | None:
    sex = ((ctx or {}).get('sex') or '').lower() or 'any'
    age = (ctx or {}).get('age')
    candidates = [r for r in lab.ranges if (r.sex or 'any').lower() in {sex, 'any'}]
    def fits(r: Range) -> bool:
        if age is None:
            return True
        if r.age_min is not None and age < r.age_min: return False
        if r.age_max is not None and age > r.age_max: return False
        return True
    for r in candidates:
        if fits(r):
            return r
    return lab.ranges[0] if lab.ranges else None

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
        r = _select_range(lab, context)
        flag = 'normal'
        if r and r.low is not None and val < r.low:
            flag = 'low'
        if r and r.high is not None and val > r.high:
            flag = 'high'
        fold = None
        if r and r.high and r.high > 0:
            fold = val / r.high
        out[code] = {
            'value': val,
            'units': (obs.get('units') or lab.unit or '').rstrip(' .;,'),
            'flag': flag,
            'fold_over_uln': fold,
        }
    return out

def evaluate_red_flags(obs: dict[str, dict[str, Any]], kb: KB) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    for rule in kb.red_flags:
        r = rule.get('rule', {})
        if r.get('lab') and r.get('op') in {'ge','gt','le','lt','fold_ge'}:
            code = r['lab']
            if code in obs:
                v = obs[code]['value']
                if r['op']=='ge' and v >= r['value']: hits.append(rule)
                if r['op']=='gt' and v >  r['value']: hits.append(rule)
                if r['op']=='le' and v <= r['value']: hits.append(rule)
                if r['op']=='lt' and v <  r['value']: hits.append(rule)
                if r['op']=='fold_ge' and obs[code].get('fold_over_uln') and obs[code]['fold_over_uln'] >= r.get('value',0):
                    hits.append(rule)
        if r.get('text_contains'):
            pass
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
            if feat in {'low','high'} and ob['flag'] == feat:
                score += float(weight); matched.append(f'{lab_code}.{feat}')
            if feat == 'normal_or_high' and ob['flag'] in {'normal','high'}:
                score += float(weight); matched.append(f'{lab_code}.normal_or_high')
            if feat.startswith('fold_gt_') and ob.get('fold_over_uln'):
                try:
                    n = float(feat.replace('fold_gt_','').replace('x',''))
                except ValueError:
                    n = None
                if n and ob['fold_over_uln'] > n:
                    score += float(weight); matched.append(f'{lab_code}.fold_gt_{n}x')
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
