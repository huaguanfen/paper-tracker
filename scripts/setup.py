#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""解析期刊目录.csv，生成 data/config.json 配置文件"""
import csv
import json
import os
import re
import sys
import io

# Windows 控制台 UTF-8 输出
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

CSV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '期刊目录.csv')
CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'config.json')

# 分类配色方案
COLORS = {
    "综合TOP": "#92400e",
    "经济学": "#1e40af",
    "管理学": "#0369a1",
    "统计学": "#4f46e5",
    "环境科学": "#059669",
}

# 分类英文 key 映射
CATEGORY_KEY_MAP = {
    "综合TOP": "top",
    "综合top": "top",
    "经济学": "economics",
    "管理学": "management",
    "统计学": "statistics",
    "环境科学": "environment",
}

# 需要跳过的 JCR/AJG 值（表示无数据或无效）
NULL_VALUES = {"", "不适用", "待核验", "待核验（JCR 2025/2024数据）", "否/不适用", "不在AJG/未匹配"}


def clean(value):
    """清理字段值，返回 None 表示无效"""
    v = value.strip() if value else ""
    return None if v in NULL_VALUES else v


def main():
    csv_path = CSV_PATH
    if not os.path.exists(csv_path):
        # 尝试从命令行参数获取
        if len(sys.argv) > 1:
            csv_path = sys.argv[1]
        if not os.path.exists(csv_path):
            print(f"错误: 找不到 {csv_path}")
            print("用法: python setup.py [期刊目录.csv路径]")
            sys.exit(1)

    categories = {}
    total_journals = 0

    with open(csv_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            cat_name = row.get("学科归类", "").strip()
            if not cat_name:
                continue

            if cat_name not in categories:
                # 优先使用预定义的 key，其次自动生成纯 ASCII key
                raw_key = cat_name.lower().replace(" ", "_").replace("&", "and")
                ascii_key = CATEGORY_KEY_MAP.get(cat_name) or CATEGORY_KEY_MAP.get(raw_key)
                if not ascii_key:
                    ascii_key = re.sub(r'[^a-z0-9_]', '', raw_key)
                    if not ascii_key:
                        ascii_key = f"cat_{len(categories)}"
                categories[cat_name] = {
                    "key": ascii_key,
                    "label": cat_name,
                    "color": COLORS.get(cat_name, "#3b82f6"),
                    "journals": []
                }

            # 官网 URL（优先官网网址，中文期刊 fallback 到核验检索链接）
            url = row.get("官网网址", "").strip()
            if url in ("", "待核验"):
                url = None

            # ISSN/CN
            issn = row.get("ISSN或CN号", "").strip()
            if issn in ("", "待核验"):
                issn = None

            # 语种
            language = "zh" if row.get("语种", "").strip() == "中文" else "en"

            # 中文期刊 fallback：使用官网核验检索链接
            if not url and language == "zh":
                fallback_url = row.get("官网核验检索链接", "").strip()
                if fallback_url and fallback_url not in ("", "待核验"):
                    url = fallback_url

            # 标签信息
            badges = {
                "jcr": clean(row.get("JCR分区", "")),
                "ajg": clean(row.get("AJG/ABS分区", "")),
                "cssci": row.get("是否CSSCI", "").strip() == "是",
                "ft50": row.get("是否FT50", "").strip() == "是",
                "utd24": row.get("是否UTD24", "").strip() == "是",
            }

            journal_name = row.get("期刊名称", "").strip()
            original_category = row.get("原目录类别", "").strip()

            categories[cat_name]["journals"].append({
                "name": journal_name,
                "issn": issn,
                "url": url,
                "language": language,
                "original_category": original_category,
                "badges": badges
            })
            total_journals += 1

    config = {
        "categories": list(categories.values())
    }

    # 确保输出目录存在
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)

    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

    print(f"✅ 配置生成完成！")
    print(f"   分类数: {len(config['categories'])} 个")
    print(f"   期刊数: {total_journals} 本")
    print(f"   输出文件: {CONFIG_PATH}")
    print()

    for cat in config['categories']:
        cn_count = sum(1 for j in cat['journals'] if j['language'] == 'zh')
        en_count = len(cat['journals']) - cn_count
        print(f"   📂 {cat['label']} ({cat['key']}): {len(cat['journals'])} 本 "
              f"[中文 {cn_count} | 英文 {en_count}]  颜色: {cat['color']}")


if __name__ == "__main__":
    main()
