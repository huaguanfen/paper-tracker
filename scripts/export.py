#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""数据导出脚本 - 自动读取 config.json，生成前端所需的 data.json"""
import json
import os
import re
import sys
import io
import argparse
from datetime import datetime, timedelta
from collections import Counter

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')


def get_base_dir():
    """获取项目根目录"""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_config():
    """加载配置"""
    config_path = os.path.join(get_base_dir(), 'data', 'config.json')
    with open(config_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_papers():
    """加载文献数据"""
    papers_path = os.path.join(get_base_dir(), 'data', 'papers.json')
    if not os.path.exists(papers_path):
        return []
    with open(papers_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def export():
    """生成 data.json"""
    cfg = load_config()
    papers = load_papers()

    if not papers:
        print("⚠ 没有文献数据，请先运行 crawler.py")
        # 生成空数据文件
        empty_data = build_output(cfg, [], {})
        save_output(empty_data)
        return

    # 基本统计
    now = datetime.now()
    stats = {
        'total': len(papers),
        'journals': len({p.get('journal_name', '') for p in papers if p.get('journal_name')}),
        'last_update': now.strftime('%Y-%m-%d %H:%M:%S'),
    }

    # 各分类文献数
    for cat in cfg['categories']:
        key = cat['key']
        count = sum(1 for p in papers if p.get('category') == key)
        stats[f'{key}_count'] = count

    # 今日新增
    today_str = now.strftime('%Y-%m-%d')
    stats['today'] = sum(1 for p in papers if p.get('published_date', '') == today_str)

    # 各期刊文献数
    journal_counter = Counter()
    for p in papers:
        jname = p.get('journal_name', '')
        if jname:
            journal_counter[jname] += 1
    stats['by_journal'] = [
        {'name': name, 'count': count}
        for name, count in journal_counter.most_common()
    ]

    # 近 30 天趋势
    trend = {}
    for i in range(29, -1, -1):
        date_str = (now - timedelta(days=i)).strftime('%Y-%m-%d')
        trend[date_str] = 0
    for p in papers:
        pub_date = p.get('published_date', '')[:10]
        if pub_date in trend:
            trend[pub_date] += 1
    stats['trend'] = [
        {'date': d, 'count': c}
        for d, c in sorted(trend.items())
    ]

    # 输出
    output = build_output(cfg, papers, stats)
    save_output(output)

    # 打印摘要
    print(f"✅ 数据导出完成！")
    print(f"   总文献数: {stats['total']}")
    print(f"   覆盖期刊: {stats['journals']} 本")
    print(f"   今日新增: {stats['today']}")
    print()
    for cat in cfg['categories']:
        key = cat['key']
        count = stats.get(f'{key}_count', 0)
        label = cat['label']
        print(f"   📂 {label}: {count} 篇")


def build_output(cfg, papers, stats):
    """构建输出数据结构"""
    return {
        'papers': papers,
        'stats': stats,
        'config': cfg,
        'export_time': datetime.now().isoformat()
    }


def save_output(data):
    """保存 data.json"""
    output_path = os.path.join(get_base_dir(), 'data', 'data.json')
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"   📄 输出文件: {output_path}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='导出文献数据到 data.json')
    parser.add_argument('--init', action='store_true', help='初始化模式（无数据时也生成文件）')
    args = parser.parse_args()

    if args.init:
        # 初始化空数据
        cfg = load_config()
        papers = load_papers()
        stats = {'total': 0, 'journals': 0, 'last_update': datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'today': 0, 'by_journal': [], 'trend': []}
        for cat in cfg['categories']:
            stats[f'{cat["key"]}_count'] = 0
        output = build_output(cfg, papers, stats)
        save_output(output)
        print("✅ 初始化完成（空数据）")
    else:
        export()
