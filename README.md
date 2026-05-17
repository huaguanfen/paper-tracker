# 📚 Research Atlas - 学术文献追踪系统

基于 GitHub Actions 自动爬取、GitHub Pages 免费托管的学术文献追踪平台。覆盖 **299 本期刊**，涵盖 **5 大学科领域**。

🌐 **在线访问**: https://hgf.github.io/paper-tracker/

---

## ✨ 核心特性

| 特性 | 说明 |
|------|------|
| 🆓 **完全免费** | GitHub Actions + Pages 零成本部署，无服务器费用 |
| 🔄 **自动更新** | 每天北京时间 00:00 自动爬取最新文献 |
| 📚 **五大学科** | 综合TOP + 经济学 + 管理学 + 统计学 + 环境科学 |
| 🔐 **PIN 验证** | 访问控制，支持设置验证密码 |
| 📊 **热词分析** | 近90天标题热词 + 摘要热词，支持分学科筛选 |
| 📈 **发文趋势** | 近30天文献发表趋势，支持分模块展示 |
| 🗂️ **智能收藏** | 书签收藏 + 文件夹分类 + 导入导出 |
| 🔍 **高级搜索** | 多字段组合检索（标题/摘要/作者/关键词） |
| 📑 **期刊导航** | 299 本期刊分类筛选 + 实时搜索 |
| 🎨 **现代UI** | 毛玻璃拟态设计 + 学术风格配色 |
| 📱 **响应式** | 完美适配手机/平板/电脑 |

---

## 📚 覆盖期刊（299本）

| 学科 | 数量 | 说明 |
|------|------|------|
| 综合TOP | 4 本 | 顶级综合期刊 |
| 经济学 | 113 本 | 含 SSCI 经济学期刊 |
| 管理学 | 158 本 | 含 SSCI 管理学期刊 |
| 统计学 | 1 本 | 统计学相关 |
| 环境科学 | 23 本 | 环境科学相关 |

> 期刊列表通过 `期刊目录.csv` 配置，支持自定义修改。

---

## 🚀 快速开始

### 1. 准备期刊目录

编辑 `期刊目录.csv`，按格式填入期刊信息：

| 期刊名称 | 学科领域 | ISSN | 语言 | 标签 |
|---------|---------|------|------|------|
| Journal of Public Administration | 综合TOP | 0022-3896 | en | FT50 |

支持的标签：`CSSCI`、`FT50`、`UTD24`、`JCR`、`AJG`。

### 2. 生成配置文件

```bash
python scripts/setup.py "期刊目录.csv"
```

生成 `data/config.json`，包含分类和期刊信息。

### 3. 爬取文献数据

```bash
python scripts/crawler.py --days 90
```

爬取近 90 天的文献，保存到 `data/papers.json`。

### 4. 导出前端数据

```bash
python scripts/export.py
```

生成 `data/data.json`，供前端使用。

### 5. 部署到 GitHub Pages

```bash
git add -A
git commit -m "update data"
git push origin main
```

在仓库 **Settings → Pages** 中启用 GitHub Pages（Source 选 Deploy from a branch → main / root）。

---

## 📁 项目结构

```
.
├── .github/workflows/
│   └── crawl.yml          # GitHub Actions 定时任务
├── data/
│   ├── config.json        # 期刊配置（由 setup.py 生成）
│   ├── papers.json        # 文献数据（由 crawler.py 生成）
│   └── data.json          # 前端数据（由 export.py 生成）
├── scripts/
│   ├── setup.py           # 从 CSV 生成 config.json
│   ├── crawler.py         # 爬虫脚本（OpenAlex API）
│   └── export.py          # 数据导出
├── 期刊目录.csv            # 期刊列表源文件
├── index.html             # 前端页面（单页应用）
└── README.md              # 本文件
```

---

## 🎯 功能模块

### 1️⃣ 发现模块
- **统计卡片** - 五大学科文献数量概览，可点击跳转
- **发文趋势** - 近30天文献发表趋势，支持分学科筛选
- **最新更新** - 查看最近收录的文献
- **热词分析** - 近90天标题热词 + 摘要热词，支持分学科筛选
- **精彩推荐** - 随机推荐优质文献
- **置顶按钮** - 快速回到页面顶部

### 2️⃣ 学科分类（综合TOP / 经济学 / 管理学 / 统计学 / 环境科学）
- 期刊筛选 + 时间范围筛选
- 排序（日期/相关性）
- 文献卡片（标题/作者/摘要/关键词/引用数）
- 分页浏览

### 3️⃣ 收藏模块
- **文件夹管理** - 新建/删除/重命名
- **书签收藏** - 点击书签选择目标文件夹
- **批量操作** - 多选删除
- **导入导出** - JSON 格式，支持跨设备迁移

### 4️⃣ 期刊导航
- 299 本期刊分类展示
- 学科筛选 + 实时搜索
- 桌面端表格布局 / 移动端折叠列表

### 5️⃣ 搜索模块
- 多字段组合检索
- 学科/时间范围筛选
- 关键词高亮显示

---

## ⚙️ 自定义配置

### 修改期刊列表

编辑 `期刊目录.csv`，然后重新运行：

```bash
python scripts/setup.py "期刊目录.csv"
python scripts/crawler.py --days 90
python scripts/export.py
```

### 修改爬取频率

编辑 `.github/workflows/crawl.yml`：

```yaml
schedule:
  - cron: '0 16 * * *'  # 每天 UTC 16:00（北京时间 00:00）
```

### 修改邮箱

编辑 `scripts/crawler.py`：

```python
EMAIL = "your-email@example.com"
```

---

## 🔧 本地开发

```bash
# 克隆仓库
git clone https://github.com/HGF/paper-tracker.git
cd paper-tracker

# 安装依赖
pip install requests

# 生成配置（首次或修改期刊后）
python scripts/setup.py "期刊目录.csv"

# 运行爬虫
python scripts/crawler.py --days 7

# 导出数据
python scripts/export.py

# 本地预览
python -m http.server 8000
# 访问 http://localhost:8000
```

---

## 📝 数据来源

- **OpenAlex API** (https://openalex.org/)
- 免费、开源、无 API Key 限制
- 支持 polite pool 提升速率限制

---

## 🔄 更新日志

### 2026-04-27
- ✅ 系统重构为 5 大学科（综合TOP/经济学/管理学/统计学/环境科学）
- ✅ 期刊扩展至 299 本
- ✅ 新增配置驱动架构（CSV → config.json）
- ✅ 新增热词分析功能（标题热词+摘要热词）
- ✅ 新增期刊导航筛选功能
- ✅ 新增页面置顶按钮
- ✅ 新增 PIN 访问验证
- ✅ UI 全面升级

---

## 📄 许可证

MIT License

---

Made with ❤️ for Scholars
