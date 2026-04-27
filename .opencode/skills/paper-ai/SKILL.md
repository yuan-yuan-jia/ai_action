---
name: paper-ai
description: 当需要采集最新的 arXiv AI 论文时使用此技能
allowed-tools: Read, Grep, Glob, WebFetch
---

# arXiv AI 论文采集与分析技能

## 使用场景

- 定时采集 arXiv 上最新发布的 AI/ML/NLP/CV 等领域论文
- 对论文进行深度分析，生成精炼摘要、提炼技术亮点、评定研究价值
- 从多篇论文中识别研究方向趋势和新兴概念，输出结构化分析报告

## 执行步骤

### 第 1 步：读取最新采集数据

使用 Glob 和 Read 定位 `knowledge/raw/ai_paper/` 中最近日期的采集文件：

```
优先读取 *.json 文件（结构化数据），
辅助参考 *.html 或 *.md 文件（论文原始摘要和上下文）。
```

提取每篇论文的 `title`、`url`（arXiv 链接）、`authors`、`abstract`（英文原文）、`categories`（arXiv 分类）、`published_at` 等已有字段。

### 第 2 步：逐条深度分析

对每篇论文执行四维分析，按以下规则产出：

#### a) 摘要（≤ 50 字）

用一句话概括核心贡献与技术方法，干净利落，不带修饰语。要求：

- 必须包含「解决什么问题」+「提出什么方法」
- 不超过 50 个汉字
- 不说废话（禁止「本文提出」「该论文研究」等开头）

#### b) 技术亮点（2-3 个）

每项亮点一句话，用事实说话，必须可验证：

- 引用具体数字（实验指标、SOTA 提升幅度、参数量级等）
- 引用具体技术方案（模型架构名称、训练方法、数据集等）
- 引用可重复验证的结果（公开代码、benchmark 性能等）

不允许写「思路新颖」「效果显著」等空泛评价。

#### c) 评分（1-10 分，附理由）

| 分数段 | 含义 | 适用情形 |
|--------|------|----------|
| 9-10 | 改变格局 | 全新范式、颠覆性发现、开源生态里程碑级工作 |
| 7-8 | 直接有帮助 | 显著 SOTA 提升、解决关键瓶颈、方法可复现 |
| 5-6 | 值得了解 | 增量改进、方向正确但突破有限、特定领域工作 |
| 1-4 | 可略过 | 缺乏实质贡献、纯调参、实验不充分 |

评分理由从 **技术原创性、实验说服力、领域影响力、可复现性** 四个维度中选取相关项阐述，限制在一句话内。

**硬性约束**：每批 15 篇论文中，9-10 分的条目不超过 2 篇。

#### d) 标签建议

为论文推荐 1-3 个标签，优先从预定义集合中选取：

```
AI, LLM, Agent, Rust, OS, Tool, Framework, RAG, Research
```

如预定义集合无法覆盖，可自定标签（如 `CV`、`NLP`、`RL`、`Diffusion` 等），但需在理由中说明。

### 第 3 步：趋势发现

通读全部分析结果后，总结 2-4 条跨论文趋势：

- **共同主题**：多篇论文围绕同一问题或方法展开
- **新兴概念**：出现新的术语、架构或训练范式（至少 3 篇论文共同体现）
- **技术路线信号**：某个方法族（如 RLHF、MoE、RAG）集中改进或翻新

每条趋势用论文标题的一部分作为证据引用。

### 第 4 步：输出分析结果 JSON

将完整分析结果写入 `knowledge/raw/ai_paper/` 目录，与原始采集文件同日期命名：

```
paper-ai-{YYYY-MM-DD}.json
```

## 注意事项

1. **分析必须基于原文**：不得直接使用论文 URL 简介作为分析结果，必须回溯到 arXiv 原始 abstract 内容。
2. **摘要独立性**：第二步的摘要是对论文 abstract 的深度加工和压缩，而非简单翻译。
3. **评分克制**：严格遵守评分标准，9-10 分入口收紧——无论批次大小，每 15 篇中 9-10 分不超过 2 篇。宁可低分勿滥高分。
4. **语言风格**：分析措辞平实客观，技术描述精确，避免营销修辞和夸张表达。论文分析应保持学术语言的克制感。
5. **不做定性判断**：评分以技术原创性和实验说服力为准，不因作者机构（名校/大厂）、论文热度（高引用/少引用）或写作语言（英文/中文）而产生偏见。
6. **趋势发现可读性**：每条趋势以加粗关键词开头，紧跟一句话解释，末尾用括号列出相关联的论文标题的关键词作为证据。
7. **论文特殊性**：论文分析重在方法论创新和实验可靠性，不同于工程项目分析——不关注星标数和社区热度，关注的是学术贡献和技术深度。

## 输出格式

### JSON 结构

```json
{
  "source": "arxiv",
  "skill": "paper-ai",
  "analyzed_at": "2026-04-27T12:00:00Z",
  "batch_info": {
    "total": 10,
    "score_distribution": {"9-10": 0, "7-8": 3, "5-6": 5, "1-4": 2},
    "source_file": "arxiv-ai-cs-2026-04-27.json"
  },
  "trends": [
    {
      "keyword": "趋势关键词",
      "description": "一句话解释该趋势",
      "evidence": ["论文标题关键词A", "论文标题关键词B", "论文标题关键词C"]
    }
  ],
  "items": [
    {
      "title": "论文标题（原文）",
      "url": "https://arxiv.org/abs/XXXX.XXXXX",
      "authors": ["Author One", "Author Two"],
      "categories": ["cs.AI", "cs.CL"],
      "summary": "不超过 50 字的中文摘要",
      "highlights": [
        "可验证的技术亮点 1（附具体数据/方法）",
        "可验证的技术亮点 2（附具体数据/方法）"
      ],
      "score": 7,
      "score_reason": "简要评分理由（一句话）",
      "tags": ["Agent", "Research"]
    }
  ]
}
```

### 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `source` | string | 固定值 `"arxiv"` |
| `skill` | string | 固定值 `"paper-ai"` |
| `analyzed_at` | string | 分析完成时间，ISO 8601 UTC |
| `batch_info` | object | 批次统计信息 |
| `batch_info.total` | number | 分析论文总数 |
| `batch_info.score_distribution` | object | 各分数段论文数 |
| `batch_info.source_file` | string | 依赖的原始采集文件名 |
| `trends` | array | 跨论文趋势发现 |
| `trends[].keyword` | string | 趋势关键词（3-6 字） |
| `trends[].description` | string | 趋势描述，一句话 |
| `trends[].evidence` | string[] | 关联论文标题关键词列表 |
| `items` | array | 逐篇分析结果 |
| `items[].title` | string | 论文标题（原文） |
| `items[].url` | string | arXiv 论文链接 |
| `items[].authors` | string[] | 作者列表 |
| `items[].categories` | string[] | arXiv 分类标签 |
| `items[].summary` | string | 深度分析摘要，≤ 50 字 |
| `items[].highlights` | string[] | 技术亮点，2-3 条，用事实说话 |
| `items[].score` | number | 评分 1-10 |
| `items[].score_reason` | string | 评分理由，一句话 |
| `items[].tags` | string[] | 标签，1-3 个，优先预定义集合 |
