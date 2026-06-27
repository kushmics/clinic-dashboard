from __future__ import annotations
import argparse, json, sys
from .kb import KB, parse_labs_from_text, flag_observations, score_conditions, evaluate_red_flags


def main() -> int:
    p = argparse.ArgumentParser(description='Run Track C differential scorer over free-text case')
    p.add_argument('--text', help='Case text (labs + summary)')
    p.add_argument('--file', help='Path to text file with case')
    args = p.parse_args()
    text = args.text or ''
    if args.file:
        text = open(args.file, 'r', encoding='utf-8').read()

    kb = KB.load()
    raw = parse_labs_from_text(text, kb)
    obs = flag_observations(raw, kb)
    scored = score_conditions(obs, kb)
    red = evaluate_red_flags(obs, kb)

    out = {
        'observations': obs,
        'differentials': [{
            'condition': s['condition'],
            'score': s['score'],
            'matched': s['matched'],
            'next_steps': s.get('next_steps', []),
        } for s in scored[:5]],
        'red_flags': [r.get('message') or r.get('name') for r in red],
    }
    print(json.dumps(out, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
