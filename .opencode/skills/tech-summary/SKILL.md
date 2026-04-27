---
name: tech-summary
description: 当需要对采集的技术内容进行深度分析总结时使用此技能
allowed-tools: Read, Grep, Glob, WebFetch
---

# 技术深度分析总结技能

## 使用场景

- 对 Collector Agent 采集的原始技术内容进行深度分析
- 为每条内容生成精炼摘要、提炼技术亮点、评定价值分数
- 从多条目中识别共性趋势和新兴概念，输出结构化分析报告

## 执行步骤

### 第 1 步：读取最新采集数据

使用 Glob 和 Read 定位 `knowledge/raw/` 中最近日期的采集文件：

```
优先读取 *.json 文件（结构化数据），
辅助参考 *.html 文件（原始描述和上下文）。
```

提取每个条目的 `name`、`url`、`description`（英文原文）、`summary`（Collector 初版摘要）、`topics`、`language`、`stargazers_count` 等已有字段。

### 第 2 步：逐条深度分析

对每条内容执行四维分析，按以下规则产出：

#### a) 摘要（≤ 50 字）

用一句话概括核心功能与技术方案，干净利落，不带修饰语。要求：

- 必须包含「解决什么问题」+「用什么技术方案」
- 不超过 50 个汉字
- 不说废话（禁止「该项目是」「这是一款」等开头）

#### b) 技术亮点（2-3 个）

每项亮点一句话，用事实说话，必须可验证：

- 引用具体数字（星标数、性能数据、支持平台数等）
- 引用具体技术方案（架构名称、协议、模型名称等）
- 引用具体场景（工业验证、生产部署等）

不允许写「设计精美」「体验极佳」等空泛评价。

#### c) 评分（1-10 分，附理由）

| 分数段 | 含义 | 适用情形 |
|--------|------|----------|
| 9-10 | 改变格局 | 基础设施级创新、开源生态里程碑、定义新范式 |
| 7-8 | 直接有帮助 | 解决明确痛点、技术方案成熟、社区验证充分 |
| 5-6 | 值得了解 | 方向正确但受众窄、技术深度一般、长期存疑 |
| 1-4 | 可略过 | 缺乏实质内容、纯营销项目、技术含量极低 |

评分理由从 **技术创新性、实用价值、社区影响力、生态扩展潜力** 四个维度中选取相关项阐述，限制在一句话内。

**硬性约束**：每批 15 个项目中，9-10 分的条目不超过 2 个。

#### d) 标签建议

为条目推荐 1-3 个标签，优先从预定义集合中选取：

```
AI, LLM, Agent, Rust, OS, Tool, Framework, RAG, Research
```

如预定义集合无法覆盖，可自定标签，但需在理由中说明。

### 第 3 步：趋势发现

通读全部分析结果后，总结 2-4 条跨条目趋势：

- **共同主题**：多个项目围绕同一问题或同一技术方向
- **新兴概念**：出现新的术语、范式或架构模式（至少 3 个项目共同体现）
- **生态信号**：某个工具链/平台/模型的衍生项目集中涌现

每条趋势用项目名称作为证据引用。

### 第 4 步：输出分析结果 JSON

将完整分析结果写入 `knowledge/raw/` 目录，与原始采集文件同日期命名：

```
tech-summary-{YYYY-MM-DD}.json
```

## 注意事项

1. **分析必须基于原文**：不得直接使用 Collector 的初版摘要作为分析结果，必须回溯到原始 description 和 README 内容。
2. **摘要独立性**：第二步的摘要是对 Collector 摘要的深度加工和压缩，而非简单改写。
3. **评分克制**：严格遵守评分标准，9-10 分入口收紧——无论批次大小，每 15 条中 9-10 分不超过 2 个。宁可低分勿滥高分。
4. **语言风格**：分析措辞平实客观，技术描述精确，避免营销修辞和夸张表达。
5. **不做定性判断**：评分以技术创新性和实用性为准，不因项目来源（个人/大厂）、语言偏好（中文/英文）或主题偏好而产生偏见。
6. **趋势发现可读性**：每条趋势以加粗关键词开头，紧跟一句话解释，末尾用括号列出相关联的项目名称作为证据。

## 输出格式

### JSON 结构

```json
{
  "source": "github_trending | hacker_news",
  "skill": "tech-summary",
  "analyzed_at": "2026-04-27T12:00:00Z",
  "batch_info": {
    "total": 10,
    "score_distribution": {"9-10": 0, "7-8": 3, "5-6": 5, "1-4": 2},
    "source_file": "github-trending-2026-04-27.json"
  },
  "trends": [
    {
      "keyword": "趋势关键词",
      "description": "一句话解释该趋势",
      "evidence": ["owner/repo1", "owner/repo2", "owner/repo3"]
    }
  ],
  "items": [
    {
      "name": "owner/repo",
      "url": "https://github.com/owner/repo",
      "summary": "不超过 50 字的中文摘要",
      "highlights": [
        "可验证的技术亮点 1（附具体数据/方案）",
        "可验证的技术亮点 2（附具体数据/方案）"
      ],
      "score": 7,
      "score_reason": "简要评分理由（一句话）",
      "tags": ["Agent", "Tool"]
    }
  ]
}
```

### 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `source` | string | 数据来源，`"github_trending"` 或 `"hacker_news"` |
| `skill` | string | 固定值 `"tech-summary"` |
| `analyzed_at` | string | 分析完成时间，ISO 8601 UTC |
| `batch_info` | object | 批次统计信息 |
| `batch_info.total` | number | 分析条目总数 |
| `batch_info.score_distribution` | object | 各分数段条目数 |
| `batch_info.source_file` | string | 依赖的原始采集文件名 |
| `trends` | array | 跨条目趋势发现 |
| `trends[].keyword` | string | 趋势关键词（3-6 字） |
| `trends[].description` | string | 趋势描述，一句话 |
| `trends[].evidence` | string[] | 关联项目名称列表 |
| `items` | array | 逐条分析结果 |
| `items[].name` | string | 仓库全名 `owner/repo` |
| `items[].url` | string | 仓库主页链接 |
| `items[].summary` | string | 深度分析摘要，≤ 50 字 |
| `items[].highlights` | string[] | 技术亮点，2-3 条，用事实说话 |
| `items[].score` | number | 评分 1-10 |
| `items[].score_reason` | string | 评分理由，一句话 |
| `items[].tags` | string[] | 标签，1-3 个，优先预定义集合 |
