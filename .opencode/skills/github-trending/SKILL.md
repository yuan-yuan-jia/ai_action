---
name: github-trending
description: 当需要采集 GitHub 热门开源项目时使用此技能
allowed-tools: Read, Grep, Glob, WebFetch
---

# GitHub Trending 采集技能

## 使用场景

- 定时采集 GitHub 上一周内创建的热门开源仓库
- 聚焦 AI/LLM/Agent/Rust/操作系统 等垂直领域
- 为下游 Analyzer Agent 提供结构化原始数据

## 执行步骤

### 第 1 步：搜索热门仓库

调用 GitHub Search API 查询近 7 天内创建且星标最高的仓库：

```
GET https://api.github.com/search/repositories
  ?q=created:>{7天前日期}
  &sort=stars
  &order=desc
  &per_page=30
```

### 第 2 步：提取仓库基本信息

从 API 响应中提取每个仓库的：

- `full_name`（owner/repo）
- `html_url`（仓库链接）
- `description`（英文描述）
- `stargazers_count`（星标数）
- `language`（主要编程语言）
- `topics`（主题标签）
- `created_at`（创建时间）

### 第 3 步：按主题过滤

**纳入**以下主题相关的仓库（满足任一即保留）：

- `ai`、`artificial-intelligence`、`machine-learning`、`deep-learning`
- `llm`、`large-language-model`、`chatgpt`、`gpt`
- `agent`、`ai-agent`、`agent-framework`、`multi-agent`
- `rust`、`rust-lang`、`rust-crate`
- `operating-system`、`os`、`kernel`

**排除**以下类型（满足任一即丢弃）：

- 主题与上述标签完全无关的通用项目
- 纯前端 UI 库 / CSS 框架 / 图标库（不含 AI 成分）
- 面试题 / 算法题库 / 课程作业
- 加密货币 / 区块链 / NFT / Web3
- 中文教程 / 文档翻译 / 资源汇总类仓库

### 第 4 步：抓取仓库 README

对通过过滤的每个仓库，使用 WebFetch 抓取其 README 内容：

```
https://github.com/{owner}/{repo}
```

提取 README 中的核心描述段落（前 500 字），作为后续摘要生成的原文依据。

### 第 5 步：生成中文摘要

基于仓库 description + README 内容，生成 100 字以内的中文摘要。要求：

- 点明项目解决什么问题和核心技术方案
- 突出亮点或独特价值
- 语言简洁平实，避免营销措辞

### 第 6 步：生成 HTML 浏览页面

将本次采集结果渲染为单文件 `{date}-github-trending-list.html`，包含：

- 页面标题、采集日期、数据来源说明
- 每个仓库的名称（含链接）、星标数、语言、创建日期、英文描述、中文摘要
- 简洁 CSS 样式，便于本地浏览
- 只包含通过过滤的仓库，按星标数降序排列

### 第 7 步：输出结构化数据

将采集结果保存到 `knowledge/raw/` 目录，输出两个文件：

| 文件 | 格式 | 命名规则 |
|------|------|----------|
| 结构化数据 | JSON | `github-trending-{YYYY-MM-DD}.json` |
| 浏览页面 | HTML | `{YYYY-MM-DD}-github-trending-list.html` |

## 注意事项

1. **API 限流**：GitHub Search API 未认证限速 10 req/min，认证后 30 req/min。建议使用 Personal Access Token 发起请求，并在请求间留足间隔。
2. **WebFetch 稳定性**：抓取 README 时可能遇到 404 或反爬，此时将 `fetch_status` 标记为 `partial` 或 `failed`，摘要降级为仅基于 description 生成。
3. **时区统一**：所有时间戳使用 UTC，格式为 ISO 8601（`YYYY-MM-DDTHH:mm:ssZ`）。
4. **去重**：如果 `knowledge/raw/` 中已存在同日期的 JSON 文件，在原文件基础上增量更新而非覆盖。
5. **不采集已归档仓库**：搜索过滤条件中排除 `archived:true` 的仓库。
6. **摘要必须基于原文**：不得凭空编造，`fetch_status: "full"` 表示已读取 README，`"partial"` 表示仅基于 description。

## 输出格式

### JSON 结构

```json
{
  "source": "github_trending",
  "skill": "github-trending",
  "collected_at": "2026-04-27T02:04:11Z",
  "items": [
    {
      "name": "owner/repo",
      "url": "https://github.com/owner/repo",
      "summary": "AI 生成的中文摘要（100 字以内）"
    }
  ]
}
```

### 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `source` | string | 固定值 `"github_trending"` |
| `skill` | string | 固定值 `"github-trending"` |
| `collected_at` | string | 采集完成时间，ISO 8601 UTC |
| `items` | array | 过滤后的仓库列表 |
| `items[].name` | string | 仓库全名 `owner/repo` |
| `items[].url` | string | 仓库主页链接 |
| `items[].summary` | string | AI 生成的中文摘要 |
