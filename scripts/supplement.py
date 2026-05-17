#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Crossref + Semantic Scholar 补爬脚本
功能：通过 Crossref 按 ISSN 发现 OpenAlex 漏爬的文献，
      再通过 Semantic Scholar 补全摘要等信息，合并写入 papers.json
用法：python scripts/supplement.py [--days 30] [--rows 100]

查询策略（双查询，防漏爬）：
  主查询：sort=created + from-created-date（按 Crossref 索引时间，能捕获 early view）
          取回数据后在本地二次过滤：只要 online/print/created 任一日期 >= since_date 即保留
  兜底查询：sort=published + from-pub-date（旧方式，主查询 < 20 条时触发）
"""

import requests
import json
import time
import os
import sys
import re
import io
import argparse
from datetime import datetime, timedelta

# Windows 控制台 UTF-8 输出
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# ── 非学术文章过滤规则（与 crawler.py 保持一致）─────────────────────────

NON_ACADEMIC_TITLE_PATTERNS = [
    'celebrating', 'anniversary', 'in memoriam', 'editorial board',
    'editorial:', 'preface:', 'introduction to the issue', 'issue information',
    'cover image', 'table of contents', 'front matter', 'back matter',
    'corrigendum', 'erratum', 'retraction', 'retraction note', 'withdrawn',
    'book review', 'review essay', 'commentary:', 'letter to the editor',
    'call for papers', 'conference report', 'meeting report', 'proceedings',
    'about this journal', 'about the authors', 'dedication', 'tribute to',
    'obituary', 'list of reviewers', 'thank you to reviewers',
    'acknowledgement to reviewers', 'annual index', 'index to volume',
    'author index', 'subject index', 'instructions to authors',
]

NON_ACADEMIC_TITLE_EXACT = {
    'reviewers', 'acknowledgment', 'acknowledgments', 'preface',
    'editorial', 'commentary', 'correction', 'abstracts', 'index',
    'foreword', 'afterword', 'colophon', 'imprint',
}


def is_non_academic_title(title):
    """检查标题是否为非学术文章"""
    if not title:
        return True
    t = title.lower().strip()
    if t in NON_ACADEMIC_TITLE_EXACT:
        return True
    for pattern in NON_ACADEMIC_TITLE_PATTERNS:
        if pattern in t:
            return True
    return False


def clean_text(text):
    """清理文本中的 HTML 标签"""
    if not text:
        return ''
    text = re.sub(r'<[^>]+>', '', text)
    return re.sub(r'\s+', ' ', text).strip()


# ── 路径工具 ─────────────────────────────────────────────────────────────────

def get_base_dir():
    """获取项目根目录"""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ── 配置 ─────────────────────────────────────────────────────────────────────

S2_API_KEY = os.environ.get('S2_API_KEY', '')
CROSSREF_EMAIL = os.environ.get('EMAIL', 'literature-tracker@example.com')
CROSSREF_HEADERS = {
    'User-Agent': f'LiteratureTracker/1.0 (mailto:{CROSSREF_EMAIL})'
}

S2_HEADERS = {
    'User-Agent': f'LiteratureTracker/1.0 (mailto:{CROSSREF_EMAIL})'
}
if S2_API_KEY:
    S2_HEADERS['x-api-key'] = S2_API_KEY


# ── 配置加载 ─────────────────────────────────────────────────────────────────

def load_config():
    """从 data/config.json 加载期刊配置"""
    config_path = os.path.join(get_base_dir(), 'data', 'config.json')
    with open(config_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def get_all_journals(cfg):
    """
    从 config.json 中提取所有英文期刊列表
    返回 [(journal_dict, category_key), ...]
    跳过中文期刊（language='zh'）
    """
    result = []
    for cat in cfg['categories']:
        cat_key = cat['key']
        for j in cat['journals']:
            if j.get('language') == 'zh':
                continue
            if not j.get('issn'):
                continue
            result.append((j, cat_key))
    return result


# ── 工具函数 ─────────────────────────────────────────────────────────────────

def load_papers():
    """加载已有论文"""
    papers_path = os.path.join(get_base_dir(), 'data', 'papers.json')
    if os.path.exists(papers_path):
        with open(papers_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []


def save_papers(papers):
    """保存论文到文件"""
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


def build_existing_dedup_keys(papers):
    """
    构建已有论文的去重 key 集合
    - DOI（规范化小写）
    - title+第一作者（兜底，处理 DOI 缺失情况）
    """
    keys = set()
    for p in papers:
        doi = normalize_doi(p.get('doi') or '')
        if doi:
            keys.add(doi)
        title = (p.get('title') or '').lower().strip()
        authors = p.get('authors') or []
        first_author = (authors[0] if authors else '').lower().strip()
        if title and first_author:
            keys.add(f"{title}||{first_author}")
    return keys


# ── Crossref：按 ISSN 获取最新论文 ──────────────────────────────────────────

def parse_date_parts(date_parts):
    """解析 Crossref 的 date-parts 格式 → YYYY-MM-DD"""
    if date_parts and date_parts[0]:
        parts = date_parts[0]
        year  = parts[0] if len(parts) > 0 else None
        month = parts[1] if len(parts) > 1 else 1
        day   = parts[2] if len(parts) > 2 else 1
        if year:
            return f"{year:04d}-{int(month):02d}-{int(day):02d}"
    return ''


def _parse_crossref_items(items):
    """
    解析 Crossref items 列表，提取论文信息。
    不在此处做日期过滤——调用方通过 _filter_by_any_date() 统一处理。
    """
    results = []
    today = datetime.now().date()

    for item in items:
        doi = normalize_doi(item.get('DOI', '').strip())
        if not doi:
            continue

        title_list = item.get('title', [])
        title = clean_text(title_list[0]) if title_list else ''
        if not title or is_non_academic_title(title):
            continue

        # 解析 online / print 日期
        online_parts = item.get('published-online', {}).get('date-parts', [[]])
        published_online = parse_date_parts(online_parts)

        print_parts = item.get('published-print', {}).get('date-parts', [[]])
        published_print = parse_date_parts(print_parts)

        # 解析 Crossref created 时间戳（索引创建时间）
        crossref_created = ''
        created_str = item.get('created', {}).get('date-time', '')
        if created_str:
            try:
                crossref_created = datetime.strptime(created_str[:10], '%Y-%m-%d').strftime('%Y-%m-%d')
            except ValueError:
                pass

        # 确定 published_date：优先 online，其次 print，跳过未来日期，兜底 created
        published_date = ''
        for d in [published_online, published_print]:
            if d:
                try:
                    if datetime.strptime(d, '%Y-%m-%d').date() <= today:
                        published_date = d
                        break
                except ValueError:
                    continue
        if not published_date and crossref_created:
            try:
                if datetime.strptime(crossref_created, '%Y-%m-%d').date() <= today:
                    published_date = crossref_created
            except ValueError:
                pass

        if not published_date:
            continue  # 没有任何有效日期，跳过

        # 作者
        authors = []
        for author in item.get('author', []):
            given  = author.get('given', '')
            family = author.get('family', '')
            full   = f"{given} {family}".strip()
            if full:
                authors.append(full)

        # 期刊名
        container  = item.get('container-title', [])
        journal_name = container[0] if container else ''

        # URL
        item_url = item.get('URL', '') or f"https://doi.org/{doi}"

        results.append({
            'doi':              doi,
            'title':            title,
            'published_date':   published_date,
            'published_online': published_online,
            'published_print':  published_print,
            'crossref_created': crossref_created,
            'journal_name':     journal_name,
            'authors':          authors[:10],
            'url':              item_url,
        })

    return results


def _filter_by_any_date(results, since_date):
    """
    本地二次过滤：只要
      published_online / published_print / crossref_created
    任一日期 >= since_date，就保留该条目。
    这样即使 Crossref 的 from-created-date 过滤有误差也能兜底。
    """
    filtered = []
    for r in results:
        dates = [
            r.get('published_online', ''),
            r.get('published_print', ''),
            r.get('crossref_created', ''),
        ]
        if any(d and d >= since_date for d in dates):
            filtered.append(r)
    return filtered


def fetch_crossref_by_issn(issn, since_date, rows_main=200, rows_fallback=100):
    """
    通过 Crossref API 按 ISSN 获取最新论文（双查询策略）

    主查询：sort=created + from-created-date（捕获 early view / ahead-of-print）
            取回全部数据后在本地做二次日期过滤。
    兜底查询：sort=published + from-pub-date（主查询结果 < 20 条时触发）
             保留旧方式，防止少数期刊不支持 created 排序。

    参数：
        issn          期刊 ISSN
        since_date    查询起始日期（YYYY-MM-DD）
        rows_main     主查询最大返回条数（默认 200，增大捕获面）
        rows_fallback 兜底查询最大返回条数（默认 100）

    返回 list of dict
    """
    base_url  = f"https://api.crossref.org/journals/{issn}/works"
    all_results  = []
    main_count   = 0   # 主查询过滤后数量（用于判断是否触发兜底）

    # ===== 主查询：按索引时间（created）排序 =====
    try:
        params_main = {
            'sort':    'created',
            'order':   'desc',
            'rows':    rows_main,
            'filter':  f'from-created-date:{since_date}',
            'mailto':  CROSSREF_EMAIL,
        }
        resp = requests.get(base_url, headers=CROSSREF_HEADERS,
                            params=params_main, timeout=30)
        if resp.status_code == 200:
            items       = resp.json().get('message', {}).get('items', [])
            parsed      = _parse_crossref_items(items)
            # 本地二次过滤：任一日期 >= since_date 才保留
            filtered    = _filter_by_any_date(parsed, since_date)
            all_results.extend(filtered)
            main_count  = len(filtered)
            print(f"    [主查询-created] 原始 {len(items)} 条 → 解析 {len(parsed)} 条 → 过滤后 {main_count} 条")
        else:
            print(f"    [主查询-created] HTTP {resp.status_code}，跳过")
    except Exception as e:
        print(f"    [主查询-created] 异常: {e}")

    # ===== 兜底查询：按发表日期（published）排序 =====
    # 触发条件：主查询结果 < 20 条（说明该期刊可能不支持 created 排序，或近期论文很少）
    if main_count < 20:
        try:
            params_fb = {
                'sort':   'published',
                'order':  'desc',
                'rows':   rows_fallback,
                'filter': f'from-pub-date:{since_date}',
                'mailto': CROSSREF_EMAIL,
            }
            resp = requests.get(base_url, headers=CROSSREF_HEADERS,
                                params=params_fb, timeout=30)
            if resp.status_code == 200:
                items    = resp.json().get('message', {}).get('items', [])
                parsed   = _parse_crossref_items(items)
                # 兜底结果同样做二次过滤
                filtered = _filter_by_any_date(parsed, since_date)

                # 去重：只追加主查询中未出现的 DOI
                existing_dois = {r['doi'] for r in all_results}
                new_from_fb   = [r for r in filtered if r['doi'] not in existing_dois]
                all_results.extend(new_from_fb)
                print(f"    [兜底-published] 原始 {len(items)} 条 → 过滤后 {len(filtered)} 条 → 新增 {len(new_from_fb)} 条")
            else:
                print(f"    [兜底-published] HTTP {resp.status_code}，跳过")
        except Exception as e:
            print(f"    [兜底-published] 异常: {e}")

    return all_results


# ── Semantic Scholar：批量补全摘要 ───────────────────────────────────────────

def fetch_s2_batch(doi_list):
    """
    通过 Semantic Scholar 批量 API 补全摘要等信息
    返回 dict: {doi_lower: {abstract, citationCount, authors, year}}
    """
    if not doi_list:
        return {}

    ids     = [f"DOI:{d}" for d in doi_list]
    url     = "https://api.semanticscholar.org/graph/v1/paper/batch"
    params  = {'fields': 'title,abstract,citationCount,authors,year,externalIds'}
    headers = dict(S2_HEADERS)
    headers['Content-Type'] = 'application/json'

    try:
        resp = requests.post(
            url, headers=headers, params=params,
            json={'ids': ids}, timeout=60
        )
        if resp.status_code != 200:
            print(f"    [S2] 批量请求失败: HTTP {resp.status_code}")
            return {}

        results = {}
        for paper in resp.json():
            if not paper:
                continue
            ext = paper.get('externalIds', {}) or {}
            doi = normalize_doi(ext.get('DOI') or '')
            if doi:
                results[doi] = {
                    'abstract':      paper.get('abstract') or '',
                    'citationCount': paper.get('citationCount') or 0,
                    'authors':       [a.get('name', '') for a in (paper.get('authors') or [])],
                    'year':          paper.get('year') or None,
                }
        return results

    except Exception as e:
        print(f"    [S2] 批量请求异常: {e}")
        return {}


def supplement_with_s2(doi_list):
    """分批调用 S2 批量 API，每批最多 500 个"""
    result  = {}
    total   = len(doi_list)
    batches = [doi_list[i:i+500] for i in range(0, total, 500)]
    print(f"    [S2] 共 {total} 个 DOI，分 {len(batches)} 批查询...")

    for i, batch in enumerate(batches):
        print(f"    [S2] 批次 {i+1}/{len(batches)} ({len(batch)} 个)...")
        batch_result = fetch_s2_batch(batch)
        result.update(batch_result)
        if i < len(batches) - 1:
            time.sleep(3)  # 速率限制：未注册 100次/5分钟

    found = sum(1 for d in doi_list if d in result)
    print(f"    [S2] 补全完成: {found}/{total} 找到摘要")
    return result


# ── 主流程 ───────────────────────────────────────────────────────────────────

def run_supplement(days=30, rows_per_journal=100):
    """
    主函数：
    1. 从 config.json 读取期刊列表
    2. 加载已有论文，构建去重 key
    3. Crossref 按 ISSN 双查询发现新论文（主查询 created + 兜底 published）
    4. S2 批量补全摘要
    5. 全局去重 + 合并写入 papers.json
    """
    print("=" * 60)
    print("Crossref + Semantic Scholar 补爬脚本")
    print("=" * 60)

    # 加载配置
    cfg          = load_config()
    all_journals = get_all_journals(cfg)
    print(f"配置期刊数（英文）: {len(all_journals)}")

    # 加载已有论文
    papers        = load_papers()
    existing_keys = build_existing_dedup_keys(papers)
    print(f"已有论文: {len(papers)} 篇 | 去重 key 数: {len(existing_keys)}")
    print()

    # 动态窗口：基于已有数据最新日期计算 since_date，往前退 3 天作缓冲
    today = datetime.now().date()
    if papers:
        valid_dates = [
            p.get('published_date', '')
            for p in papers
            if p.get('published_date')
        ]
        valid_dates = [
            d for d in valid_dates
            if d <= today.strftime('%Y-%m-%d')
        ]
        if valid_dates:
            latest_date = max(valid_dates)
            since_date  = (
                datetime.strptime(latest_date, '%Y-%m-%d') - timedelta(days=3)
            ).strftime('%Y-%m-%d')
        else:
            since_date = (today - timedelta(days=days)).strftime('%Y-%m-%d')
    else:
        since_date = (today - timedelta(days=days)).strftime('%Y-%m-%d')

    print(f"Crossref 查询起始日期: {since_date}（动态窗口，退 3 天缓冲）")
    print(f"每刊主查询上限: {rows_per_journal * 2} 条 | 兜底查询上限: {rows_per_journal} 条")
    print()

    # ── 第一步：Crossref 发现新 DOI ─────────────────────────────────────────
    print("【第一步】Crossref 按 ISSN 发现新论文...")
    new_papers    = []        # 待新增论文（尚未补全 S2）
    crossref_seen = set()     # 本批次已处理 DOI（防同批内重复）

    for journal, cat_key in all_journals:
        issn = journal.get('issn', '')
        name = journal.get('name', '')
        print(f"  [{cat_key}] {name} (ISSN: {issn})")

        works = fetch_crossref_by_issn(
            issn,
            since_date     = since_date,
            rows_main      = rows_per_journal * 2,   # 主查询取更多，本地过滤
            rows_fallback  = rows_per_journal,        # 兜底保持原来量级
        )
        added = 0

        for work in works:
            doi         = work['doi']   # 已 normalize
            title       = work.get('title', '').lower().strip()
            authors     = work.get('authors') or []
            first_author = (authors[0] if authors else '').lower().strip()

            # DOI 去重（已有 + 本批次）
            if doi in existing_keys or doi in crossref_seen:
                continue
            # title+author 兜底去重
            if title and first_author and f"{title}||{first_author}" in existing_keys:
                continue

            work['category'] = cat_key
            new_papers.append(work)
            crossref_seen.add(doi)
            existing_keys.add(doi)
            if title and first_author:
                existing_keys.add(f"{title}||{first_author}")
            added += 1

        print(f"    Crossref 返回 {len(works)} 篇，新增 {added} 篇")
        time.sleep(0.5)  # Crossref polite pool

    print(f"\nCrossref 共发现新论文: {len(new_papers)} 篇")

    if not new_papers:
        print("没有发现需要补爬的新论文，退出。")
        return 0, {}

    # ── 第二步：S2 批量补全摘要 ─────────────────────────────────────────────
    print("\n【第二步】Semantic Scholar 批量补全摘要...")
    doi_list = [p['doi'] for p in new_papers]
    s2_data  = supplement_with_s2(doi_list)

    # ── 第三步：全局去重 + 合并 ─────────────────────────────────────────────
    print("\n【第三步】全局去重并合并数据...")

    # 对已有数据做一次全局去重（清理历史遗留重复）
    before_dedup = len(papers)
    seen_keys    = set()
    deduped      = []
    for p in papers:
        doi          = normalize_doi(p.get('doi') or '')
        title        = (p.get('title') or '').lower().strip()
        authors_     = p.get('authors') or []
        first_author = (authors_[0] if authors_ else '').lower().strip()

        key = doi if doi else (f"{title}||{first_author}" if title and first_author else None)
        if key:
            if key in seen_keys:
                continue
            seen_keys.add(key)
        deduped.append(p)

    removed_dup = before_dedup - len(deduped)
    if removed_dup > 0:
        print(f"  历史去重: 移除 {removed_dup} 条重复记录")

    papers          = deduped
    added_count     = 0
    no_abstract_cnt = 0

    for paper in new_papers:
        doi = paper['doi']
        s2  = s2_data.get(doi, {})

        new_record = {
            'openalex_id':      f'crossref:{doi}',
            'title':            paper.get('title', ''),
            'abstract':         s2.get('abstract') or '',
            'journal_name':     paper.get('journal_name', ''),
            'published_date':   paper.get('published_date', ''),
            'published_online': paper.get('published_online', ''),
            'published_print':  paper.get('published_print', ''),
            'url':              paper.get('url', ''),
            'doi':              paper['doi'],
            'cited_by_count':   s2.get('citationCount') or 0,
            'keywords':         [],
            'authors':          s2.get('authors') or paper.get('authors', [])[:10],
            'category':         paper.get('category', 'unknown'),
            'supplement_source': 'crossref+s2',
        }

        # S2 提供年份但缺 published_date 时补全
        if not new_record['published_date'] and s2.get('year'):
            new_record['published_date'] = f"{s2['year']}-01-01"

        if not new_record['abstract']:
            no_abstract_cnt += 1

        papers.append(new_record)
        added_count += 1

    save_papers(papers)

    print(f"合并完成: 新增 {added_count} 篇")
    print(f"  有摘要: {added_count - no_abstract_cnt} 篇")
    print(f"  无摘要: {no_abstract_cnt} 篇（S2 未覆盖）")
    print(f"总计: {len(papers)} 篇")

    # 按期刊统计
    journal_stats = {}
    for p in new_papers:
        name = p.get('journal_name', '未知期刊')
        journal_stats[name] = journal_stats.get(name, 0) + 1

    return added_count, journal_stats


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Crossref+S2 补爬脚本：发现 OpenAlex 漏爬的文献'
    )
    parser.add_argument('--days', type=int, default=30,
                        help='Crossref 查询最近多少天的论文（默认 30）')
    parser.add_argument('--rows', type=int, default=100,
                        help='每个 ISSN 兜底查询上限（默认 100；主查询为 rows*2）')
    args = parser.parse_args()

    run_supplement(days=args.days, rows_per_journal=args.rows)
