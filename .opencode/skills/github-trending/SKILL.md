---
name: github-trending
description: Fetch GitHub Trending top 50 repos via HTML parsing, filter by AI/LLM/Agent/ML/OS/Rust topics (with text fallback), output JSON with total+weekly stars to stdout. Use when user asks to collect/crawl/fetch/scrape/grab/pull/get GitHub trending, hot projects, popular repos, star rankings, trending repositories; or in Chinese: GitHub趋势, 热门仓库, 趋势榜, 采集/爬/抓GitHub, 排行, 热门项目; or wants to discover/browse/surf AI/LLM/Agent/ML/OS/Rust open source projects on GitHub.
allowed-tools: Bash, Read, Write
---

# GitHub Trending 采集技能

## Quick start

```bash
python .opencode/skills/github-trending/scripts/parse_trending.py
```

脚本自动抓取 `https://github.com/trending?since=weekly`，解析 HTML，按 topic 过滤，获取 total stars，输出 JSON 到 stdout。零外部依赖。

## 执行步骤

### 第 1 步：运行解析脚本

```bash
python .opencode/skills/github-trending/scripts/parse_trending.py
```

脚本内部自动完成所有工作，无需手动抓页面或管道传数据。

检查退出码：
- **exit 0**：成功，stdout 为 JSON 数组（可能为 `[]` 表示今日无匹配仓库）
- **exit 1**：出错，stderr 有错误信息，stdout 为 `[]`

### 第 2 步：验证输出

输出的 JSON 数组必须符合下方 Schema。

## 过滤规则

双层过滤（任一命中即保留）：

| 层级 | 数据源 | 逻辑 |
|------|--------|------|
| Topic 匹配 | 仓库 topic 标签 | `topics ∩ filter_topics ≠ ∅`（不区分大小写） |
| 文本降级 | 仓库名 + 描述 | `name + description` 包含 fallback_keywords 中任一关键词 |

Topic 为空或不足时，文本降级自动兜底，避免静默空返回。

### 可配置关键词

编辑 `scripts/config.json` 即可修改过滤词，无需改代码：

```json
{
  "filter_topics": ["ai", "llm", "agent", "ml", ...],
  "fallback_keywords": ["artificial intelligence", "large language model", ...]
}
```

## 注意事项

1. **不用 GitHub API** — Search API 限速 10 req/min，坚持 HTML 解析。
2. **不存文件** — 结果仅 stdout，caller 决定存储。
3. **不做去重** — 每次独立输出，caller 负责去重。
4. **超时宽松** — 默认 60s（含 total stars 抓取），可配置。
5. **区分错误与空结果** — exit 1 = 出错（stderr），exit 0 = 正常（含真无匹配）。
6. **Total stars 限流** — 默认最多抓取 30 个仓库的 total stars，超限则剩余仓库 `stars` 为 0。
7. **HTML 结构变更告警** — 解析到 0 个仓库时 stderr 输出 WARNING。
8. **Total stars 抓取失败不阻塞** — 单个仓库失败仅记 0，不影响整体输出。

## 输出格式

### JSON 示例

```json
[
  {
    "name": "owner/repo",
    "url": "https://github.com/owner/repo",
    "stars": 12345,
    "stars_this_week": 1234,
    "topics": ["ai", "llm", "agent"],
    "description": "A brief description of the repository"
  }
]
```

### 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `name` | string | 仓库全名，格式 `owner/repo` |
| `url` | string | 仓库主页链接 |
| `stars` | integer | 仓库总星标数（total stars），抓取失败时为 0 |
| `stars_this_week` | integer | 本周新增星标数，≥0 |
| `topics` | string[] | 仓库 topic 标签列表 |
| `description` | string | 仓库描述原文 |

### JSON Schema

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "array",
  "items": {
    "type": "object",
    "required": ["name", "url", "stars", "stars_this_week", "topics", "description"],
    "properties": {
      "name": { "type": "string", "pattern": "^[^/]+/[^/]+$" },
      "url": { "type": "string", "format": "uri" },
      "stars": { "type": "integer", "minimum": 0 },
      "stars_this_week": { "type": "integer", "minimum": 0 },
      "topics": {
        "type": "array",
        "items": { "type": "string" }
      },
      "description": { "type": "string" }
    },
    "additionalProperties": false
  }
}
```

## 配置文件

`scripts/config.json` — 所有可调参数：

| 键 | 类型 | 默认值 | 说明 |
|----|------|--------|------|
| `trending_url` | string | `https://github.com/trending?since=weekly` | 抓取地址 |
| `filter_topics` | string[] | 18 个 AI/OS/Rust 关键词 | topic 匹配白名单 |
| `fallback_keywords` | string[] | 18 个关键词 | 文本降级兜底 |
| `timeout_seconds` | int | 60 | 总超时秒数 |
| `max_stars_fetches` | int | 30 | total stars 最大抓取数 |
| `user_agent` | string | `github-trending-skill/1.0` | HTTP User-Agent |
