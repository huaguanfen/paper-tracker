#!/usr/bin/env python3
import json, os
from datetime import datetime, timedelta

base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
papers_path = os.path.join(base, 'data', 'papers.json')

papers = json.load(open(papers_path, 'r', encoding='utf-8'))
cutoff = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
filtered = [p for p in papers if p.get('published_date', '')[:10] >= cutoff]

with open(papers_path, 'w', encoding='utf-8') as f:
    json.dump(filtered, f, ensure_ascii=False, indent=2)

print(f'原始: {len(papers)} -> 保留: {len(filtered)} (删除 {len(papers)-len(filtered)} 篇)')
dates = sorted(set(p.get('published_date', '')[:10] for p in filtered if p.get('published_date')))
print(f'日期范围: {dates[0]} ~ {dates[-1]}')
