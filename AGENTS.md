# AGENTS.md — AI 知识库助手

## 项目概述

自动从 GitHub Trending 和 Hacker News 采集 AI/LLM/Agent/Rust/操作系统领域的技术动态，经 LLM 分析后结构化存储为 JSON 知识条目，并通过 Telegram/飞书/WeChat 等多渠道分发。全程由 OpenCode 编排多 Agent 协作完成。

## 技术栈

| 类别 | 选型 |
|------|------|
| 语言/运行时 | Python 3.12（uv 虚拟环境 `.venv/`） |
| 编排框架 | **OpenCode**（Agent 编排 + Skill 管理）+ 国产大模型 |
| 工作流引擎 | **LangGraph**（采集→分析→整理的有状态图） |
| 数据采集 | **OpenClaw**（通用爬虫框架） |
| 存储 | JSON 文件（`knowledge/articles/`） |

## 编码规范

- **风格**：PEP 8，`snake_case` 命名
- **文档**：Google 风格 docstring（含 Args / Returns / Raises）
- **日志**：禁止裸 `print()`，统一使用 `logging` 模块
- **类型**：所有函数签名必须标注类型 hint

## 项目结构

```
ai_action/
├── .opencode/
│   ├── agents/          # Agent 定义（采集/分析/整理）
│   └── skills/          # Skill 脚本（可复用的工具函数）
├── knowledge/
│   ├── raw/             # 原始抓取内容（HTML/Markdown）
│   └── articles/        # 结构化后的 JSON 知识条目
├── .venv/               # uv 虚拟环境
├── specs/               # 需求/设计文档
├── main.py              # 入口
├── pyproject.toml
├── README.md
└── AGENTS.md
```

## 知识条目 JSON 格式

```json
{
  "id": "uuid 或 hash",
  "title": "文章标题（原文）",
  "title_cn": "文章标题（AI 中文翻译）",
  "source": "github_trending | hacker_news",
  "source_url": "原文链接",
  "summary": "AI 生成的 200 字以内摘要（原文）",
  "summary_cn": "AI 生成的中文摘要",
  "tags": ["AI", "LLM", "Agent", "Rust", "OS"],
  "status": "draft | reviewed | published",
  "collected_at": "2026-04-25T12:00:00Z",
  "analyzed_at": "2026-04-25T12:05:00Z"
}
```

## Agent 角色概览

| 角色 | 职责 | 输入 | 输出 |
|------|------|------|------|
| **采集器 (Collector)** | 定时从 GitHub Trending / HN 抓取原始内容 | 源 URL + 调度信号 | 原始 HTML/Markdown → `knowledge/raw/` |
| **分析器 (Analyzer)** | 调用 LLM 提取摘要、打标签、质量过滤 | `knowledge/raw/` 的原始内容 | 结构化 JSON → `knowledge/articles/` |
| **整理器 (Publisher)** | 按渠道要求格式化并推送分发 | `knowledge/articles/` 的条目 | Telegram / 飞书 / WeChat 消息 |

三个 Agent 通过 LangGraph 构成流水线：**采集 → 分析 → 整理**，每个节点可独立重试与回退。

## 红线（绝对禁止）

1. **禁止将 API Key / Token 等凭证提交到 Git**
2. **禁止对采集内容做任何手动修改**（所有加工必须通过 Agent 完成）
3. **禁止跳过 Analyze 环节直接发布未经审核的条目**
4. **禁止在非 `.venv` 环境下安装依赖**
5. **禁止裸 `print()` — 必须使用 `logging`**
6. **禁止在 `main.py` 之外的地方定义入口逻辑**
