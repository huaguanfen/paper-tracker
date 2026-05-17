#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据清理脚本
功能：清理 papers.json 中的重复文献和超期文献
用法：python scripts/cleanup.py
"""

import json
import os
import sys
import io
from datetime import datetime

# Windows 控制台 UTF-8 输出
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')


def get_base_dir():
    """获取项目根目录"""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_papers():
    """加载已有文献"""
    papers_path = os.path.join(get_base_dir(), 'data', 'papers.json')
    if os.path.exists(papers_path):
        with open(papers_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []


def save_papers(papers):
    """保存文献到文件"""
    papers_path = os.path.join(get_base_dir(), 'data', 'papers.json')
    os.makedirs(os.path.dirname(papers_path), exist_ok=True)
    with open(papers_path, 'w', encoding='utf-8') as f:
        json.dump(papers, f, ensure_ascii=False, indent=2)


def normalize_doi(doi):
    """规范化 DOI：去掉 URL 前缀，统一小写"""
    if not doi:
        return ''
    doi = doi.lower().strip()
    if doi.startswith('https://doi.org/'):
        doi = doi[16:]
    elif doi.startswith('http://doi.org/'):
        doi = doi[15:]
    return doi


def cleanup_papers():
    """主清理函数"""
    papers = load_papers()
    total_before = len(papers)
    today = datetime.now().date()

    print("=" * 60)
    print("数据清理脚本")
    print("=" * 60)
    print(f"清理前文献总数: {total_before}")
    print()

    # 第一步：全局去重（DOI 优先，title+first_author 兜底）
    seen_dois = set()
    seen_title_author = set()
    deduped = []
    dup_doi_count = 0
    dup_title_count = 0

    for p in papers:
        doi = normalize_doi(p.get('doi', ''))
        title = (p.get('title') or '').lower().strip()
        authors = p.get('authors') or []
        first_author = (authors[0] if authors else '').lower().strip()

        if doi:
            if doi in seen_dois:
                dup_doi_count += 1
                continue
            seen_dois.add(doi)
        elif title and first_author:
            # 没有 DOI 时用 title+author 兜底去重
            ta_key = f"{title}||{first_author}"
            if ta_key in seen_title_author:
                dup_title_count += 1
                continue
            seen_title_author.add(ta_key)

        deduped.append(p)

    dup_count = dup_doi_count + dup_title_count
    if dup_doi_count > 0:
        print(f"【去重】移除重复文献（DOI 重复）: {dup_doi_count} 篇")
    if dup_title_count > 0:
        print(f"【去重】移除重复文献（标题+作者重复）: {dup_title_count} 篇")
    if dup_count == 0:
        print("【去重】未发现重复文献")

    # 第二步：删除未来日期文献
    cleaned = []
    future_count = 0

    for p in deduped:
        pub_date = p.get('published_date', '')
        if pub_date:
            try:
                if datetime.strptime(pub_date[:10], '%Y-%m-%d').date() > today:
                    future_count += 1
                    continue
            except ValueError:
                pass  # 日期格式异常，保留
        cleaned.append(p)

    if future_count > 0:
        print(f"【日期】移除未来日期文献: {future_count} 篇")
    else:
        print("【日期】未发现未来日期文献")

    total_after = len(cleaned)
    removed = total_before - total_after

    print()
    print(f"清理完成:")
    print(f"  移除总数: {removed} 篇")
    print(f"  剩余总数: {total_after} 篇")
    print()

    save_papers(cleaned)
    print("已保存清理后的数据到 data/papers.json")

    return removed, total_after


if __name__ == '__main__':
    cleanup_papers()
