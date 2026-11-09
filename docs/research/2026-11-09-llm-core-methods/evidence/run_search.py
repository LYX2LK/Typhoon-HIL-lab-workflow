"""Use the installed skill API; its CLI currently lacks the documented --json flag."""
import json
import sys
from pathlib import Path

sys.path.insert(0, 'D:/LYX/Documents/毕业论文/.codex/skills/paper-search/scripts')
from search_papers import search_papers
from postprocess import dedup, rank

if __name__ == '__main__':
    queries = ['large language model cyber physical falsification',
               'large language model time series anomaly diagnosis',
               'large language model active fault diagnosis']
    results = search_papers(queries, 2023, 2026, max_results=6,
                            end_date='2026-11-09')
    merged = dedup(results)
    ranked, dropped = rank(merged, queries, min_score=None)
    out = Path(__file__).parent / 'paper-search-results.json'
    out.write_text(json.dumps({'queries': queries, 'start_year': 2023,
        'end_date': '2026-11-09', 'results': results, 'ranked': ranked,
        'duplicate_count': sum(map(len, results.values()))-len(merged)},
        ensure_ascii=False, indent=2), encoding='utf-8')
    print({s: len(p) for s,p in results.items()}, flush=True)
    print(f'{len(ranked)} unique papers; saved {out}', flush=True)
