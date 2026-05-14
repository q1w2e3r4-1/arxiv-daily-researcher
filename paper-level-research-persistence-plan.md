# Paper-level Research Persistence Plan

# Context
当前 daily research 的持久化主语义仍然是“整轮 run 产出一批 report”，而不是“每篇论文独立保存自己的 research record”。这带来两个问题：
- 一旦 run 在中途被打断，已经完成评分/翻译/深度分析的论文缺少统一的 durable paper-level record，恢复和复用都不自然。
- 后续如果要按日期、来源、分类、是否及格、是否完成深度分析等维度筛选，直接从 Markdown/HTML report 反向提取会非常别扭。

同时，当前 `src/modes/daily_research.py` 会在 `_score_single_paper(...)` 结束后立刻调用 `search_agent.mark_as_processed(...)`，而 `src/sources/base_source.py` 的 `mark_as_processed()` 会马上改写 `*_history.json`。这意味着今天的 history 实际语义是“这篇论文已经评分过”，而不是“这篇论文的整条 research 链路已经 durable 完成”。

此外，这个 plan 提出之后，report 的默认展示语义已经变更：
- 顶层摘要优先显示“可见摘要”：`qualified + abstract_cn -> 中文摘要`，否则显示英文摘要。
- 默认正文只保留最小评分信息：总分，以及 committee 模式下的 `model -> score`。
- 唯一折叠区域是“深度分析”。

这意味着持久化层不应围绕旧的 `tldr` / `reasoning` 展示逻辑设计，而应保存原始事实字段，让 Markdown / HTML / 通知在渲染时按当前规则派生出可见摘要。

目标是在**不重写 report / UI 的前提下**，把 daily research 改成“paper-level first，report as view”：每篇论文在评分、翻译、深度分析完成后逐步落盘，打断后不丢已完成成果；报告继续保留，但只是这些 paper records 的一种聚合视图。

# Recommended approach
## 1) 仍然使用 SQLite，但明确它是“项目内单文件存储”，不是额外服务
新增 `src/utils/daily_research_store.py`，复用 `src/keyword_tracker/database.py` 的 SQLite 模式：
- 单次操作独立连接
- `PRAGMA journal_mode=WAL`
- 建表和索引集中在 `_ensure_tables()`
- 通过 `INSERT ... ON CONFLICT DO UPDATE` 做单篇论文的增量 upsert

这条路线仍然是轻量方案，因为：
- Python 自带 `sqlite3` 标准库
- 不需要新增 `pip` 依赖
- 不需要额外安装 PostgreSQL / MySQL 之类的外部数据库服务
- 不需要修改当前 Docker 镜像来安装数据库客户端或服务端

数据库路径固定放在项目内，并且与报告目录分开，避免后续误把它当成可清理产物：
- `settings.DATA_DIR / "daily_research" / "daily_research.db"`
- 即项目路径：`data/daily_research/daily_research.db`

SQLite 在 WAL 模式下，旁边还可能出现：
- `data/daily_research/daily_research.db-wal`
- `data/daily_research/daily_research.db-shm`

这些都是正常文件，不是额外依赖，也不应被清理脚本删除。

## 2) 明确 Docker 可见性与持久性边界
当前 `docker-compose.yml` 已经将：
- `./data:/app/data`

挂载到容器中，而项目默认 `DATA_DIR` 就是仓库内的 `data/`。因此数据库放在：
- 宿主机：`data/daily_research/daily_research.db`
- 容器内：`/app/data/daily_research/daily_research.db`

这意味着：
- 容器重启不会丢数据库
- 宿主机可以直接备份和查看该文件
- 不需要为 SQLite 额外增加 volume 或 sidecar service

实现时只需要保证运行前自动创建：
- `data/daily_research/`

这可以在 store 初始化时完成；不要求 Dockerfile 预创建该目录，但若后续希望更显式，也可以作为很小的运维补丁。

## 3) Schema 以“原始事实 + 少量查询列”为中心，不跟着当前 report 文案走
首版推荐仍建 2 张表：

### `daily_runs`
用于记录一次 daily run 的上下文，字段尽量轻：
- `run_id`
- `started_at`, `completed_at`, `status`
- `search_days`, `max_results`
- `enabled_sources_json`, `keywords_json`
- `report_paths_json`, `token_usage_json`
- `error_message`

### `daily_papers`
以 `(source, paper_id)` 为主键，兼顾未来筛选字段和大 payload：

#### 查询列
- `source`, `paper_id`, `title`, `published_date`
- `url`, `pdf_url`, `doi`, `journal`
- `is_qualified`, `total_score`, `passing_score`, `scoring_method`
- `first_run_id`, `last_run_id`, `completed_run_id`
- `score_completed_at`, `translation_completed_at`, `analysis_completed_at`, `completed_at`, `updated_at`

#### JSON / Text 列
- `metadata_json`
- `authors_json`, `categories_json`
- `abstract`, `abstract_cn`
- `score_json`
- `analysis_json`
- `last_error`

这里有两个重要约束：
1. **不要把 `display_summary` / `tldr` / `reasoning` 设计成持久化权威字段**
   - 当前 report 的摘要显示规则已经变成派生逻辑：
     - `qualified + abstract_cn -> 中文摘要`
     - 否则 -> 英文摘要
   - 因此 store 只需要持久化 `abstract` 与 `abstract_cn`，而不是把某一版 UI 的展示文案固化进 schema。

2. **`score_json` 要保留完整 `WeightedScoreResponse` 结构**
   - 现在 report 默认只显示“总分 + model scores”，但未来可能再次调整展示规则。
   - 因此数据库不能只存简化分数字段，必须保留完整结构，尤其是 committee scoring 下的 `model_judgments` 等原始信息。

这样可以直接支持未来的筛选需求，同时避免把 `WeightedScoreResponse` / 深度分析结构拆成过细的列。

## 4) 持久化写入点放在 `DailyResearchPipeline.run()` 的阶段边界，而不是 worker 内部
首版尽量不让 worker 线程直接写 DB，避免把并发和事务纠缠在一起。

具体做法：
- `_score_single_paper(...)` 改成只负责“评分 + 返回 scored dict”，不再写 history。
- 主线程在拿到 `future.result()` / 串行 `result` 后，立刻调用 store：
  - `upsert_scored_paper(...)`：保存 metadata + score payload
- 翻译 future 完成后：
  - `update_translation(...)`：写入 `abstract_cn` 和 `translation_completed_at`
- 深度分析 future 完成后：
  - `update_analysis(...)`：写入 `analysis_json` 和 `analysis_completed_at`
- 串行模式也走同样的 store helper，只是调用时机变成同步执行

这样既保留现有 overlap 编排，也让 durable state 与阶段完成时机一致。

## 5) 复用 store 做“轻量恢复”，避免中断后整篇论文白跑
在阶段4处理每篇 fetched paper 前，先按 `(source, paper_id)` 查询 store：
- 如果已有 `score_json`，则直接 hydrate 出当前 `scored` dict，跳过重新评分
- 如果已有 `abstract_cn`，则直接复用，跳过翻译
- 如果已有 `analysis_json`，则直接复用，跳过深度分析
- 仅对缺失阶段继续执行

这一步不需要额外从 DB 主动“扫描待恢复论文”；只要**尚未 complete 的论文不要提前写入 history**，下次相同时间窗 rerun 时，source 还会把这些论文重新 fetch 出来，而 pipeline 会自动从 store 里接着做剩余阶段。

这能在不引入第二套调度器的前提下，拿到足够好的 interrupt/resume 效果。

## 6) 把 history 的语义改成“已 durable 完成”，不再等同于“评分过”
`src/sources/base_source.py` 的历史文件继续保留，但写入时机后移：

- **未及格论文**：当 score 已 durably 写入 store 后，再 `mark_as_processed()`
- **及格但无需深度分析的论文**：当翻译已 durably 写入 store 后，再 `mark_as_processed()`
- **及格且要做深度分析的论文**：当翻译 + analysis 都已 durably 写入 store 后，再 `mark_as_processed()`
- **任一后续阶段失败**：写 `last_error`，但不写 history，让下次 run 还能重新遇到这篇论文并补齐后续阶段

这会让 `arxiv_history.json` 重新代表“可以安全跳过的完成论文”，而不是“某次跑到一半时恰好评过分的论文”。

## 7) v1 继续复用现有 Reporter，把 report 保持为兼容视图
首版不重写：
- `src/report/daily/reporter.py`
- `src/report/daily/modules/renderers.py`

具体策略是：
- pipeline 仍然在内存中维护 `scored_papers_by_source` 和 `analyses_by_source`
- 这些对象来自“新抓取结果 + store hydrate 的已有结果 + 本轮新增阶段结果”
- 阶段6继续直接调用 `Reporter.generate_reports_by_source(...)`
- Markdown / HTML / 通知继续按当前展示规则派生“可见摘要”，而不是从 store 中读取某个预烘焙的摘要字段

这样 report 仍然照常生成，通知/UI 也不需要同步重写；但 durable source-of-truth 已经从“整份 report”切换成“单篇 paper record”。

## 8) 首版不做旧 report/history 的回填迁移，只对新 run 生效
为了控制工程量，首版不尝试：
- 从旧 Markdown/HTML 回填 paper store
- 把旧 `arxiv_history.json` 倒灌成完整 paper records
- 为 store 额外做一套跨时间窗的主动恢复任务
- 为 SQLite 增加全文检索、Web UI 查询页或额外导出层

可以接受的边界是：
- 新逻辑上线后的 run 开始享受 paper-level durability
- 旧 history 已标记但未落到新 store 的论文，首版不自动补救
- 真正的“全历史统一检索”作为后续工作再做

# Critical files to modify
- `src/modes/daily_research.py` — 调整 history 写入时机、插入 store upsert/hydrate、维持现有 report 输入形状
- `src/utils/daily_research_store.py` — 新增 SQLite store，负责 runs / papers 的 schema 与 upsert/query

## Optional tiny follow-up files
- `src/sources/base_source.py` — 若实现时需要补一个更明确的 history 注释或极小辅助函数，可做小补丁；默认不改语义本体
- `src/config.py` — 仅在你希望把 DB 路径暴露为设置项时才加；首版推荐不改
- `docker/Dockerfile` — 若希望预创建 `/app/data/daily_research` 可加一行目录创建；不是功能必需项

# Reuse points
- `src/keyword_tracker/database.py`
  - 复用 SQLite 连接、WAL、建表、索引、按操作开连接的写法
- `src/sources/base_source.py`
  - `PaperMetadata.to_dict()` 可直接作为 `metadata_json` 的来源
- `src/agents/analysis_agent.py`
  - `WeightedScoreResponse` 作为 `score_json` 的权威结构，可用 `model_dump()` / `model_validate()` 做持久化与恢复
  - 深度分析返回结构已与 `Stage2Response` 对齐，可直接原样存成 `analysis_json`
- `src/modes/daily_research.py`
  - 现有 `_score_single_paper(...)`
  - 现有 `_translate_single_qualified_paper(...)`
  - 现有 `_deep_analyze_single_paper(...)`
  - 现有 `translation_futures` / `analysis_futures` drain 点，正好是 durable write 的最佳时机
- `src/report/daily/reporter.py`
  - 继续消费当前的 `scored_papers_by_source` / `analyses_by_source`，首版不改输入契约
- `docker-compose.yml`
  - 已有 `./data:/app/data` 挂载，可直接承载 SQLite 文件，无需额外数据库服务

# Engineering size estimate
- **推荐范围**：1 个新模块 + 1 个主文件，必要时 0-2 个小补丁
- **主改动量**：
  - `src/utils/daily_research_store.py` 约 180-280 行
  - `src/modes/daily_research.py` 约 120-220 行净改动
- **总文件数预估**：2-5 个文件
- **总体工程量**：明显小于“全面重写 report / web UI / 搜索入口”的规模，属于一次中等偏小的持久化重构；在你之前给的“10 个文件、平均 50 行”量级附近，不需要引入额外服务或第三方数据库依赖

# Verification
1. **静态/语法检查**
- 跑 `python -m compileall src`，确认新增 store 和 `daily_research.py` 无语法错误。

2. **数据库可见性与路径验证**
- 运行一次小流量 daily。
- 确认以下文件出现：
  - `data/daily_research/daily_research.db`
  - 以及可能的 `-wal` / `-shm`
- 若通过 Docker 运行，确认容器内对应路径可见：
  - `/app/data/daily_research/daily_research.db`

3. **单次小流量持久化验证**
- 用 `SEARCH_DAYS=1`、小上限跑一次 daily。
- 随机抽查：
  - 每篇 fetched paper 都有一条 `daily_papers` 记录
  - 未及格 paper 至少有 `score_json`
  - 及格 paper 有 `abstract_cn`
  - 有 PDF 且分析成功的 paper 有 `analysis_json`

4. **中断恢复验证**
- 运行一次 daily，在部分论文已完成评分/翻译/分析后手动中断。
- 再次运行相同时间窗。
- 观察日志确认：
  - 已有 `score_json` 的论文不会重复评分
  - 已有 `abstract_cn` 的论文不会重复翻译
  - 已有 `analysis_json` 的论文不会重复深度分析
  - 只补跑缺失阶段

5. **history 语义验证**
- 确认 `*_history.json` 不再在“刚评完分”时更新。
- 验证：
  - 未及格论文在 score durable 后进入 history
  - 及格且有 PDF 的论文在 analysis durable 前不进入 history
  - 中途中断后，未 complete 的论文仍可在下次 fetch 中出现

6. **report 兼容性验证**
- 确认 Markdown / HTML 报告仍然正常生成。
- 抽查报告中的：
  - 评分结果
  - 摘要翻译
  - 深度分析
  与 DB 中持久化内容一致。
- 确认“可见摘要”仍遵循当前规则：`qualified + abstract_cn -> 中文摘要`，否则显示英文摘要。

7. **查询性 smoke test**
- 用简单 SQL 验证未来筛选能力，例如：
  - 按 `published_date` 查近期论文
  - 按 `source` / `is_qualified` 查 paper
  - 查 `analysis_completed_at IS NOT NULL` 的论文
- 目标不是做 UI，而是证明 paper-level store 已经能支撑未来的日期/元数据检索。
