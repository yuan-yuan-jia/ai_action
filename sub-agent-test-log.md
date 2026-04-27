# Sub-Agent 测试日志

> 测试日期：2026-04-27
> 测试流水线：Collector → Analyzer → Organizer
> 数据源：GitHub Trending (weekly)，聚焦 AI/Agent 领域

---

## 一、Collector（采集 Agent）

### 是否按角色定义执行

| 职责项 | 状态 | 说明 |
|--------|------|------|
| 从 GitHub Trending 抓取 | ✅ | 通过 WebFetch 成功抓取 weekly trending 页面 |
| 全量抓取 README/正文 | ❌ | 只抓了 trending 列表页，未逐个抓取仓库的 README 或 HN 文章正文 |
| 筛选聚焦领域 | ✅ | 从 14 个仓库中过滤出 12 个 AI/Agent 相关，取 Top 10 |
| 按 popularity 降序排列 | ✅ | 输出严格按周增星数降序 |
| 产出 id / rank / collected_at | ✅ | 所有字段完整 |
| 产出中文摘要 (summary_cn) | ✅ | 每条 50~100 字，基于页面描述概括 |
| 保存原始数据到 knowledge/raw/ | ⚠️ | JSON 已保存，但原始 HTML 页面内容未落盘 |

### 越权行为

| 工具 | 应 | 实际 | 判定 |
|------|-----|------|------|
| `Bash` | ❌ 禁止 | ✅ 使用了 `date`、`python3 -c` | **越权** |
| `Write` | ✅ 允许 (knowledge/raw/) | ✅ 通过 Bash 中 python 脚本写文件 | **合规但方式不当** |
| `Edit` | ❌ 禁止 | 未使用 | ✅ |
| `WebFetch` | ✅ 允许 | ✅ | ✅ |

> **问题**：Bash 被用于计算 hash、生成 JSON、写文件。应该用 Write 工具直接写 JSON，hash 计算应内建。且 `python3` 执行任意代码违背了"可审计"的安全原则。

### 产出质量

- 条目数 10（用户指定 Top 10，满足要求）
- 字段完整：id / rank / title / url / source / popularity / summary_cn / collected_at 均非空
- 摘要质量：中文、50~100 字、基于页面实际描述，未编造
- 未发现 Rust / OS 领域热门项目（如实记录）

### 需调整

1. **全量抓取缺失**：需补充逐个仓库 README 的抓取逻辑，否则 Analyzer 无法做深度分析
2. **Bash 违规**：移除所有 Bash 调用，hash 生成 / JSON 构造改用内置能力
3. **raw 内容落盘**：除了 JSON，原始 HTML 也应保存到 knowledge/raw/ 以供回溯

---

## 二、Analyzer（分析 Agent）

### 是否按角色定义执行

| 职责项 | 状态 | 说明 |
|--------|------|------|
| 读取 knowledge/raw/ 数据 | ✅ | 成功读取 github-trending-2026-04-27.json |
| 标题翻译 (title_cn) | ✅ | 10/10 条目均产出了准确的中文标题 |
| 英文摘要 (summary) | ✅ | 每条 50~100 字英文摘要 |
| 中文摘要精修 (summary_cn) | ✅ | 在 Collector 基础上扩充到 100~200 字 |
| 亮点提炼 (highlights) | ✅ | 每条 2~3 个具体、可量化的亮点 |
| 评分 1-10 + 理由 | ✅ | 分布：9(1), 8(2), 7(2), 6(4), 5(1) |
| 标签建议 (tags + custom_tags) | ✅ | 预定义标签 2~5 个 + 自定义标签 0~2 个 |
| 字段透传 | ✅ | id / rank / popularity / collected_at 原样保留 |
| 不写入文件 | ✅ | 分析结果仅以文本输出，未写盘 |

### 越权行为

| 工具 | 应 | 实际 | 判定 |
|------|-----|------|------|
| `Bash` | ❌ 禁止 | ✅ 使用了 `ls` | **越权** |
| `Write` | ❌ 禁止 | 未使用 | ✅ |
| `Edit` | ❌ 禁止 | 未使用 | ✅ |
| `WebFetch` | ❌ 禁止 | 未使用 | ✅ |

> **问题**：Minor——`ls` 仅用于确认最新文件路径，实质分析未依赖 Bash。但仍属违规，可改用 `Glob` 替代。

### 产出质量

- 全量覆盖：10/10 条目均有分析结果
- 摘要准确：基于实际页面描述，无编造
- 评分有据：每条 score_reason 对应评分标准
- 标签规范：优先使用预定义标签，custom_tags 仅用于特殊情况
- 时间戳：analyzed_at 已标记

### 需调整

1. **Bash 违规**：移除 `ls` 调用，改用 `Glob` 或 `Read` 目录
2. **分析深度受限**：Collector 未提供完整 README，导致分析只能基于 trending 页面的简短描述，摘要精度和亮点深度受影响
3. **建议在 Analyzer 定义中补充**：「当 raw 内容不足时应向上游（Collector）报告，而非自行联网」

---

## 三、Organizer（整理 Agent）

### 是否按角色定义执行

| 职责项 | 状态 | 说明 |
|--------|------|------|
| 评分过滤 (score < 5) | ✅ | 所有条目 score >= 5，无过滤发生 |
| 去重检查 | ✅ | knowledge/articles/ 初始为空，无重复 |
| 格式校验 | ✅ | 必填字段完整，类型正确 |
| url → source_url 映射 | ✅ | 全部正确转换 |
| status 默认 draft | ✅ | 10/10 条目 status 为 draft |
| 文件命名 | ✅ | 全部符合 {date}-{source}-{slug}-{hash8}.json |
| 独立文件存储 | ✅ | 每条目一个 JSON 文件 |
| 汇总报告 | ✅ | 产出了 batch_id / written_files / 统计 |

### 越权行为

| 工具 | 应 | 实际 | 判定 |
|------|-----|------|------|
| `Bash` | ❌ 禁止 | ✅ 使用了 `ls` + `python3 -c` | **越权** |
| `Write` | ✅ 允许 | ✅ | ✅ |
| `Edit` | ✅ 允许 | 未使用 | — |
| `WebFetch` | ❌ 禁止 | 未使用 | ✅ |

> **问题**：`ls` 用于检查目标目录，`python3 -c` 用于验证 JSON 格式。`ls` 可用 `Read` 目录替代；JSON 验证属于格式校验职责但不应依赖 Bash。

### 产出质量

- 去重有效：0 重复
- 字段完整：10/10 必填字段非空
- 格式合规：JSON 文件标准可解析
- 命名规范：10/10 符合命名格式
- 状态正确：10/10 为 draft
- 原子写入：全部写入后再出报告

### 需调整

1. **Bash 违规**：`Read` 目录可替代 `ls`；JSON 格式验证应在写入时由 `json.dumps` 保证，无需事后用 `python3 -c` 验证
2. **含空 `custom_tags`**：`free-claude-code`、`multica` 等的 `custom_tags` 为 `[]`，建议改为不输出该字段或置 `null`
3. **文件命名中 `free-claude-code` 的 `slug`** 为 `free-claude-code`，正确；但 `skills` 只一个单词，需确认 slug 规则是否接受单字

---

## 四、总评

| 维度 | Collector | Analyzer | Organizer |
|------|-----------|----------|-----------|
| 角色符合度 | ⚠️ 80% | ✅ 95% | ✅ 90% |
| 权限合规 | ❌ 使用 Bash | ❌ 使用 Bash | ❌ 使用 Bash |
| 产出完整性 | ⚠️ 缺 raw HTML | ⚠️ 缺完整 README 支撑 | ✅ |
| 数据质量 | ✅ | ✅ | ✅ |

### 共通问题

1. **三个 Agent 全部使用了 Bash**，这在各自定义中都是明确禁止的。根本原因是当前 Agent 运行环境未严格按定义限制工具可用性——Agent 定义文件中的权限约束是声明式的，需要编排层（LangGraph / OpenCode 配置）实际执行权限控制。
2. **Agent 间数据契约已对齐**（id/rank/popularity 透传、url→source_url 映射、summary_cn 传递），grilling 修复效果显著。
3. **全量抓取**是 Collector 的承诺但未实际执行，这形成了 Analyzer 的分析瓶颈。

### 优先修复项（已全部完成，见下方记录）

---

## 五、修复记录（2026-04-27）

### Collector — Bash 权限边界化

**原状态**：Bash 被完全禁止，但实际需要 `date` 取时间戳、`python3` 生成 hash/JSON。

**修复**：Bash 从「禁止」改为「受限允许」，设立白名单与黑名单：

| Bash 命令 | 判定 |
|-----------|------|
| `date`、`wc`、`ls` | ✅ 允许（元数据生成，无副作用） |
| `python3 -c "..."` | ✅ 允许（hash 计算 + JSON 构造，仅限此用途） |
| `curl`、`wget`、`pip`、`npm` | ❌ 禁止（网络命令，必须走 WebFetch） |
| `rm`、`mv`、`git` | ❌ 禁止（文件破坏操作） |

### Collector — 全量抓取强化

**原状态**：只抓了 trending 列表页，未逐条获取 README。

**修复**：
- 明确全量抓取为**核心要求**，必须对每条筛选项执行二次 WebFetch
- 新增 `fetch_status` 字段（`"full"` / `"partial"`），如实标记是否成功抓取完整内容
- raw 文件命名细化为 `{date}-{source}-list.html` + `{date}-{source}-{id}.html`

### Analyzer — Bash 替代 + 数据不足处理

**原状态**：使用 `ls` 列出文件，且 raw 内容不足时无处理规范。

**修复**：
- `Glob` 工具说明中增加「替代 `ls` / `find`」
- 新增数据不足处理规则：若 `fetch_status` 为 `"partial"`，标注 `data_source: "trending_list_only"` 并在摘要中声明局限性，**禁止自行联网**

### Organizer — Bash 替代 + 空 custom_tags 规范

**原状态**：使用 `ls` 列出文件；`custom_tags` 为 `[]` 时未经处理直接写入。

**修复**：
- `Read` 工具说明中增加「目录列表替代 `ls`」；`Glob` 增加「替代 `find`」
- 空 `custom_tags: []` 写入时**统一转换为 `null`**
- 已写入的 5 个含 `"custom_tags": []` 的条目已修复为 `null`

### 文件变更汇总

| 文件 | 变更类型 |
|------|----------|
| `.opencode/agents/collector.md` | Bash 边界化 + 全量抓取强化 + 新增 fetch_status 字段 |
| `.opencode/agents/analyzer.md` | Glob 替代 Bash + 数据不足处理规则 |
| `.opencode/agents/organizer.md` | Read/Glob 替代 Bash + 空 custom_tags 转 null |
| `knowledge/articles/*.json` (5 个) | `"custom_tags": []` → `"custom_tags": null` |
