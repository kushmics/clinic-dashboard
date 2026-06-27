import time, sys, json, pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from app.skills.differential_dx.kb import KB, parse_labs_from_text, flag_observations, score_conditions, evaluate_red_flags

dir = pathlib.Path(__file__).parent / 'fixtures'
kb = KB.load()
rows = []
start_all = time.perf_counter()
for p in sorted(dir.glob('*.txt')):
    t0 = time.perf_counter()
    text = p.read_text(encoding='utf-8')
    raw = parse_labs_from_text(text, kb)
    # infer simple sex from text
    ctx = {'sex': 'f' if 'female' in text.lower() else ('m' if 'male' in text.lower() else None)}
    obs = flag_observations(raw, kb, ctx)
    scored = score_conditions(obs, kb)[:3]
    red = [r.get('message') or r.get('name') for r in evaluate_red_flags(obs, kb)]
    dur = (time.perf_counter() - t0) * 1000
    rows.append({'case': p.name, 'top': [s['condition'] for s in scored], 'red_flags': red, 'ms': round(dur,1)})

print(json.dumps({'cases': rows, 'total_ms': round((time.perf_counter()-start_all)*1000,1)}, indent=2))
