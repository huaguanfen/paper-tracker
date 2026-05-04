#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""OpenAlex 文献爬虫 - 自动读取 config.json 配置"""
import requests
import json
import time
import os
import html
import re
import argparse
import io
import sys
from datetime import datetime, timedelta

# Windows 控制台 UTF-8 输出
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

OPENALEX_BASE = "https://api.openalex.org"
EMAIL = os.environ.get('EMAIL', 'literature-tracker@example.com')
HEADERS = {'User-Agent': 'Literature Tracker (mailto:{})'.format(EMAIL), 'Accept': 'application/json'}

# 非学术性文章标题关键词
NON_ACADEMIC_PATTERNS = [
    'celebrating', 'anniversary', 'in memoriam', 'editorial board',
    'preface:', 'introduction to the issue', 'issue information',
    'cover image', 'table of contents', 'front matter', 'back matter',
    'corrigendum', 'erratum', 'retraction', 'retraction note', 'withdrawn',
    'book review', 'review essay', 'commentary:', 'letter to the editor',
    'call for papers', 'conference report', 'meeting report', 'proceedings',
    'about this journal', 'about the authors', 'dedication', 'tribute to',
    'obituary', 'list of reviewers', 'thank you to reviewers',
    'acknowledgement to reviewers', 'annual index', 'index to volume',
    'author index', 'subject index', 'contents', 'instructions to authors',
]
NON_ACADEMIC_EXACT = {
    'reviewers', 'acknowledgment', 'acknowledgments', 'preface',
    'editorial', 'commentary', 'correction', 'abstracts', 'index',
    'foreword', 'afterword', 'colophon', 'imprint',
}

CONFIG_CACHE = None


def get_base_dir():
    """获取项目根目录"""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_config():
    """加载并缓存配置"""
    global CONFIG_CACHE
    if CONFIG_CACHE is None:
        config_path = os.path.join(get_base_dir(), 'data', 'config.json')
        with open(config_path, 'r', encoding='utf-8') as f:
            CONFIG_CACHE = json.load(f)
    return CONFIG_CACHE


def normalize_journal_name(name):
    """根据配置标准化期刊名称"""
    if not name:
        return name
    cleaned = html.unescape(name).strip()
    cfg = load_config()
    for cat in cfg['categories']:
        for j in cat['journals']:
            if cleaned.lower() == j['name'].lower():
                return j['name']
            # 处理 & 和 and 的互换
            if cleaned.lower().replace('&', 'and') == j['name'].lower().replace('&', 'and'):
                return j['name']
    return cleaned


def search_by_issn(issn):
    """通过 ISSN 在 OpenAlex 搜索期刊"""
    if not issn:
        return None
    try:
        r = requests.get(
            f"{OPENALEX_BASE}/sources",
            headers=HEADERS,
            params={'filter': f'issn:{issn}', 'mailto': EMAIL},
            timeout=30
        )
        if r.status_code == 200:
            data = r.json()
            if data.get('results'):
                return data['results'][0]
    except Exception as e:
        print(f"    ⚠ ISSN搜索失败 [{issn}]: {e}")
    return None


def search_by_name(name):
    """通过期刊名称在 OpenAlex 搜索"""
    try:
        r = requests.get(
            f"{OPENALEX_BASE}/sources",
            headers=HEADERS,
            params={'search': name, 'mailto': EMAIL},
            timeout=30
        )
        if r.status_code == 200:
            data = r.json()
            if data.get('results'):
                # 优先精确匹配
                for item in data['results']:
                    item_name = item.get('display_name', '')
                    if name.lower() in item_name.lower() or item_name.lower() in name.lower():
                        return item
                return data['results'][0]
    except Exception as e:
        print(f"    ⚠ 名称搜索失败 [{name}]: {e}")
    return None


def get_source_id(journal):
    """获取期刊在 OpenAlex 中的 source ID"""
    name = journal['name']
    issn = journal.get('issn')

    # 优先 ISSN 匹配
    if issn:
        result = search_by_issn(issn)
        if result:
            print(f"    ✅ ISSN匹配: {name}")
            return result.get('id')

    # 其次名称匹配
    result = search_by_name(name)
    if result:
        print(f"    ✅ 名称匹配: {name} → {result.get('display_name', '')}")
        return result.get('id')

    print(f"    ❌ 未找到: {name}")
    return None


def is_non_academic(title):
    """判断标题是否为非学术性文章"""
    if not title:
        return True
    t = title.lower().strip()
    if t in NON_ACADEMIC_EXACT:
        return True
    for pattern in NON_ACADEMIC_PATTERNS:
        if pattern in t:
            return True
    return False


def clean_text(text):
    """清理 HTML 标签和多余空白"""
    if not text:
        return ''
    text = re.sub(r'<[^>]+>', '', text)
    return re.sub(r'\s+', ' ', text).strip()


def reconstruct_abstract(inverted_index):
    """从倒排索引重建摘要文本"""
    if not inverted_index:
        return ''
    try:
        word_positions = {}
        for word, positions in inverted_index.items():
            for pos in positions:
                word_positions[pos] = word
        return ' '.join(word_positions[i] for i in sorted(word_positions))
    except Exception:
        return ''


def parse_work(work, cfg):
    """解析 OpenAlex 返回的单篇文献数据"""
    try:
        title = clean_text(work.get('display_name', ''))
        if is_non_academic(title):
            return None

        abstract = reconstruct_abstract(work.get('abstract_inverted_index', {}))

        # 发布日期
        pub_date = work.get('publication_date', '')
        if not pub_date:
            year = work.get('publication_year', '')
            pub_date = f"{year}-01-01" if year else ''

        # 期刊信息
        loc = work.get('primary_location', {}) or {}
        src = loc.get('source', {}) or {}
        journal_name = normalize_journal_name(src.get('display_name', ''))

        # 引用数
        cited_by = work.get('cited_by_count', 0)

        return {
            'openalex_id': work.get('id', '').replace('https://openalex.org/', ''),
            'title': title,
            'abstract': abstract,
            'journal_name': journal_name,
            'published_date': pub_date,
            'url': loc.get('landing_page_url', '') or work.get('id', ''),
            'doi': work.get('doi', '') or '',
            'cited_by_count': cited_by,
            'keywords': [k.get('display_name', '') for k in (work.get('keywords') or []) if k],
            'authors': [
                a.get('author', {}).get('display_name', '')
                for a in (work.get('authorships') or [])
                if a.get('author')
            ]
        }
    except Exception as e:
        print(f"    ⚠ 解析文献出错: {e}")
        return None


def fetch_papers(source_id, from_date=None, to_date=None, per_page=100):
    """从 OpenAlex 获取指定期刊的文献列表"""
    url = f"{OPENALEX_BASE}/works"
    filters = [f'primary_location.source.id:{source_id}']
    if from_date:
        filters.append(f'from_publication_date:{from_date}')
    if to_date:
        filters.append(f'to_publication_date:{to_date}')

    params = {
        'filter': ','.join(filters),
        'per-page': per_page,
        'sort': 'publication_date:desc',
        'mailto': EMAIL
    }

    papers = []
    cursor = '*'
    cfg = load_config()

    while cursor:
        if cursor != '*':
            params['cursor'] = cursor

        try:
            r = requests.get(url, headers=HEADERS, params=params, timeout=60)
            if r.status_code == 429:
                print("    ⏳ 请求限速，等待 10 秒...")
                time.sleep(10)
                continue
            if r.status_code != 200:
                print(f"    ⚠ 请求失败: HTTP {r.status_code}")
                break

            data = r.json()
            results = data.get('results', [])
            if not results:
                break

            new_count = 0
            for work in results:
                paper = parse_work(work, cfg)
                if paper:
                    papers.append(paper)
                    new_count += 1

            print(f"    📄 获取 {len(papers)} 篇 (本批 +{new_count})")

            cursor = data.get('meta', {}).get('next_cursor')
            if not cursor or len(results) < per_page:
                break

            time.sleep(0.5)

        except Exception as e:
            print(f"    ⚠ 出错: {e}")
            break

    return papers


def load_existing_papers():
    """加载已有的文献数据"""
    papers_path = os.path.join(get_base_dir(), 'data', 'papers.json')
    if os.path.exists(papers_path):
        with open(papers_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []


def save_papers(papers):
    """保存文献数据"""
    cfg = load_config()
    # 标准化所有期刊名称
    for p in papers:
        if 'journal_name' in p:
            p['journal_name'] = normalize_journal_name(p['journal_name'])

    papers_path = os.path.join(get_base_dir(), 'data', 'papers.json')
    os.makedirs(os.path.dirname(papers_path), exist_ok=True)
    with open(papers_path, 'w', encoding='utf-8') as f:
        json.dump(papers, f, ensure_ascii=False, indent=2)


def crawl(days=30):
    """执行爬取
    
    策略：
    - 有存量数据时，从最新 published_date 回退 3 天作为 from_date，
      避免 OpenAlex 数据延迟导致漏爬
    - 无存量数据时，使用 (now - days) 作为 from_date
    """
    cfg = load_config()
    to_date = datetime.now().strftime('%Y-%m-%d')
    
    existing = load_existing_papers()
    
    if existing:
        # 找到已有数据中最新的 published_date，往前退 3 天作为缓冲
        latest_date = max(
            p.get('published_date', '1970-01-01')
            for p in existing
        )
        from_date = (
            datetime.strptime(latest_date, '%Y-%m-%d') - timedelta(days=3)
        ).strftime('%Y-%m-%d')
        print(f"📦 检测到存量数据，最新日期: {latest_date}，回退缓冲 3 天")
    else:
        # 首次运行或数据丢失
        from_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    
    print("=" * 70)
    print(f"📅 爬取范围: {from_date} 至 {to_date}")
    print(f"📂 分类数: {len(cfg['categories'])}")
    total_journals = sum(len(c['journals']) for c in cfg['categories'])
    print(f"📚 期刊总数: {total_journals}")
    print("=" * 70)

    existing_ids = {p['openalex_id'] for p in existing}

    total_added = 0
    stats = {}  # {journal_name: added_count}
    skip_count = 0

    # 构建期刊列表: [(journal_info, category_key)]
    all_journals = []
    for cat in cfg['categories']:
        for journal in cat['journals']:
            if journal.get('language') == 'zh':
                print(f"    [跳过] 中文期刊: {journal['name']}")
                continue
            all_journals.append((journal, cat['key']))

    for idx, (journal, cat_key) in enumerate(all_journals, 1):
        print(f"\n[{idx}/{len(all_journals)}] [{cat_key}] {journal['name']}")
        print(f"    ISSN: {journal.get('issn') or '无'}")

        source_id = get_source_id(journal)
        if not source_id:
            skip_count += 1
            time.sleep(1)
            continue

        papers = fetch_papers(source_id, from_date, to_date)
        added = 0

        for p in papers:
            if p['openalex_id'] not in existing_ids:
                p['category'] = cat_key
                existing.append(p)
                existing_ids.add(p['openalex_id'])
                added += 1

        stats[journal['name']] = added
        total_added += added
        print(f"    ✅ 新增 {added} 篇")

        # 礼貌延时
        time.sleep(1)

    # 清理超过30天的旧文献，防止数据无限累积
    cutoff_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
    before_trim = len(existing)
    existing = [p for p in existing if p.get('published_date', '')[:10] >= cutoff_date]
    trimmed = before_trim - len(existing)
    if trimmed > 0:
        print(f"\n🗑 清理 {trimmed} 篇超过30天的旧文献")

    save_papers(existing)

    print("\n" + "=" * 70)
    print(f"🏁 爬取完成！")
    print(f"   新增文献: {total_added} 篇")
    print(f"   清理旧文献: {trimmed} 篇")
    print(f"   当前总文献: {len(existing)} 篇")
    print(f"   跳过期刊: {skip_count} 本（未在 OpenAlex 中找到）")
    print("=" * 70)

    return total_added, stats


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='OpenAlex 文献爬虫')
    parser.add_argument('--days', type=int, default=30, help='爬取最近多少天的文献（默认30天）')
    args = parser.parse_args()
    crawl(days=args.days)
