# 更新日志

所有值得关注的版本变更均记录在此文件中。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，版本遵循 [Semantic Versioning](https://semver.org/lang/zh-CN/)。

---

## ✅ v3.2 — 2026-04-26

### ✨ 新功能

1. **网络代理系统** — 支持 HTTP / SOCKS5 代理，可按服务粒度控制（ArXiv / OpenAlex / Semantic Scholar / LLM API / 通知 / 检查更新），WebUI 提供完整的代理设置面板。
2. **WebDAV 数据同步** — 按需同步配置和数据文件到 WebDAV 服务器（坚果云、NextCloud 等），支持手动 / 定时 / 报告后自动三种同步模式。内置坚果云 HEAD 请求不兼容的修复（使用 PROPFIND 替代），同步范围可选配置文件、历史记录、关键词数据、报告。
3. **配置一键导出** — WebUI 数据管理面板支持一键将 `config.json` 和 `.env` 打包为 zip 下载，兼容 Docker 卷挂载路径。
4. **Docker 版本更新通知** — Docker 环境下通过 GitHub API 检查最新版本，发现新版本时通过已配置的通知渠道推送更新提醒。
5. **通知模板外部化** — 更新通知使用 `configs/templates/` 下的独立模板文件，支持按平台自定义格式，加载失败时自动回退到内置格式。
6. **每日推送 Tab** — 原「运行管理」Tab 重组为「每日推送」，新增「每日研究设置」区域，集中管理 HTML 报告、Markdown 报告、包含所有论文三个开关，评分 Tab 中的「包含所有论文」开关同步迁移至此。
7. **Markdown 报告独立开关** — 新增 `enable_markdown_report` 配置项，Markdown 和 HTML 报告可独立启用/关闭，在「每日推送」Tab 中直接控制。
8. **趋势分析输出格式双开关** — 输出格式从多选下拉框改为两个独立 Toggle（Markdown / HTML），默认均开启，在「趋势分析」Tab 中操作。
9. **运行日志刷新自动跳转** — 「每日推送」Tab 的日志刷新按钮改为自动打开最新的非系统日志，无需手动选择。
10. **高级设置重组** — 原「报告」分区重命名为「功能开关」，HTML 报告 Toggle 移出，仅保留 Token 追踪和自动更新检查。

### 🐛 Bug 修复 / 优化

1. **WebDAV 坚果云兼容修复** — 坚果云不支持 HEAD 请求（返回 403），webdavclient3 的 `check()` 方法依赖 HEAD 导致所有连接操作失败。传入 `disable_check=True` 并改用 PROPFIND (Depth 0) 进行存在性检查，彻底修复。
2. **ArXiv 抓取逻辑优化** — 顺序遍历最新论文并在收集到 `max_results` 篇新论文后立即停止；保留连续已处理论文早停机制（阈值 50 篇），在不突破用户上限的前提下跨过 history 边界。
3. **Docker Compose 位置调整** — `docker-compose.yml` 从 `docker/` 目录移至项目根目录，简化 Docker 命令。
4. **Docker 镜像优化** — 移除未使用的系统依赖，精简镜像体积。
5. **配置导出路径修复** — 修复 Docker 卷挂载环境下配置导出显示"未找到可导出文件"的问题，增加多路径候选检测。
6. **每日深度分析可配置** — 新增 `daily_research.enable_deep_analysis` 配置项，可独立控制每日研究模式是否执行 PDF 深度分析。
7. **Telegram 通知 HTML 渲染修复** — 修复 Telegram 通知中 HTML 标签未被正确渲染的问题。

### 📦 架构变更

1. **WebUI 面板风格统一** — 所有 Tab 内分节标题统一为 `section-title` 样式（粗体蓝色下划线 + 语境化 emoji）。
2. **配置系统扩展** — `config.json` 新增 `proxy.scope.update_check` 和 `report_settings.enable_markdown_report` 字段。
3. **趋势分析面板优化** — 运行控制按钮移至 Tab 顶部，关键词输入紧跟其后，提升操作效率。

---

## ✅ v3.1 — 2026-04-15

### ✨ 新功能 / 重构

1. **运行管理 Tab 完全重构** — 统一本地模式与 Docker 模式的立即运行体验；支持停止任务、查看状态、清理失效锁。
2. **日志查看器升级** — 日志区域按"系统日志 / 运行日志 / 其他日志"三栏分组，选中即展示，共享同一内容区；默认优先展示时间最新且非系统日志。
3. **趋势分析 Tab 完整双语化** — 趋势分析界面的参数、状态、按钮、Skill 标签等文本全部纳入 i18n。
4. **趋势分析配置收口到独立 Tab** — 趋势研究相关的排序、最大结果数、TLDR、输出格式与 Skill 选择统一放入「趋势分析」Tab。
5. **ArXiv 抓取超时守卫** — 新增 `data_sources.arxiv.fetch_timeout_seconds` 配置，使用硬超时保护单个领域抓取。
6. **运行锁超龄回收** — 对超过 `run_lock.max_age_hours` 的任务尝试自动终止旧进程并回收锁。
7. **报告查看增强** — 默认自动打开当前可见范围内最新的报告；刷新后重新跳转到最新可见报告。

### 🐛 Bug 修复

1. **报告日期导航修复** — 修复同一日期有多份报告时，前一天/后一天导航可能错误定位的问题。
2. **日志默认选择逻辑修复** — 运行管理页首次进入时，不再默认打开系统日志，优先显示最新的实际运行日志。
3. **i18n 条目补齐** — 新增并补齐运行管理、日志查看、趋势分析等相关翻译项。

---

## ✅ v3.0 — 2026-03-09

### ✨ 新功能

1. **研究趋势分析模式** — 全新 `trend_research` 运行模式，支持指定关键词和时间范围批量检索 ArXiv 论文，LLM 逐篇生成 TLDR，SMART_LLM 单次调用综合分析五个维度（热点话题、时间演变、核心研究者、研究空白、方法论趋势）。CLI 通过 `--mode trend_research --keywords "..."` 启动，支持 `--date-from`、`--date-to`、`--sort-order`、`--max-results`、`--categories` 参数。
2. **趋势分析 Skills 系统** — 五个分析维度合并为一个综合 Skill 单次调用，支持在 `config.json` 中配置启用的 Skill。
3. **研究趋势专属通知模板** — 新增趋势分析成功/失败通知模板（Markdown + HTML）。
4. **Token 消耗追踪** — 全局 Token 计数器，线程安全单例，对所有 LLM 调用无侵入式埋点，按模型统计输入/输出 Token 数。每次运行结束展示在报告和通知中。
5. **关键词趋势 HTML 报告** — 生成独立 HTML 趋势报告，使用 CSS 彩色水平柱状图、颜色编码图例表格和趋势热图。
6. **交互式配置向导 + Docker 自动触发** — 7 步 CLI 向导，Docker 首次部署自动运行。
7. **Streamlit 配置面板** — 浏览器配置面板，6 个配置 Tab 页覆盖所有配置项，支持 LLM 连接测试、SMTP 测试、实时计算评分预览。
8. **运行专用日志文件** — 每次运行自动创建独立日志文件：`daily_YYYYMMDD_HHMMSS.log` / `trend_YYYYMMDD_HHMMSS.log`。
9. **统一依赖管理** — WebUI 容器不再使用独立的 `requirements-webui.txt`，与主容器共用 `requirements.txt`。
10. **并发运行互斥锁** — 基于 `fcntl.LOCK_EX | LOCK_NB` 文件锁，防止同一任务被重复并发触发。daily_research 全局互斥，trend_research 按参数哈希独立互锁。
11. **Streamlit 报告查看器** — 三列并排展示全部类型报告文件，页内嵌入渲染 HTML。

### 📦 架构变更

1. **双模式 CLI 入口** — `main.py` 新增 `argparse` 命令行解析。
2. **报告目录重组** — 所有报告统一归入 `data/reports/`，按类型分目录。
3. **`modes/` 目录完整化** — 每日研究流水线提取为 `DailyResearchPipeline` 类。
4. **`report/` 目录按模式拆分** — 按运行模式重组为 `report/daily/`、`report/trend/`、`report/keyword_trend/`。
5. **配置管理基础模块** — 新增 `src/utils/config_io.py`，统一的 `.env` / `config.json` 双向读写能力。

---

## ✅ v2.3 — 2026-03-09

### ✨ 新功能

1. **邮件通知 HTML 精美模板** — 6 个模板（运行成功/失败 + 4 种错误告警）采用响应式卡片设计，内嵌 inline CSS 兼容主流邮件客户端。
2. **通知渠道独立开关** — 各渠道的 `enabled` 开关，可精细控制每个渠道的启用状态。

---

## ✅ v2.2 — 2026-03-03

### 📦 源代码结构重构

1. 按功能模块拆分 `src/` 目录为 `agents/`、`sources/`、`report/`、`notifications/`、`parsers/`、`keyword_tracker/`。

### 🐛 Bug 修复

1. 修复 JSON 转义修复器正则表达式失效
2. 修复并发模式下历史记录读取的竞态条件
3. 修复并发模式下 SQLite "database is locked" 错误
4. 修复并发模式下临时 PDF 文件名冲突
5. 修复 PDF 文件句柄泄漏
6. 修复 OpenAlex 分页数日志 Off-by-one
7. 修复合成 DOI 生成无效 URL
8. 修复关键词缓存目录未创建导致保存静默失败
9. 修复 `INSERT OR IGNORE` 后 `lastrowid` 不可靠
10. 修复参考 PDF 关键词分配逻辑
11. 修复 `git rev-list` 返回码未检查

---

## ✅ v2.1 — 2026-03-03

### 📋 许可证变更

1. 许可证从 CC BY-NC-SA 4.0 变更为 AGPL-3.0。

### ✨ 新功能

1. 通知消息 Markdown 模板系统
2. 运行时错误实时告警通知

---

## ✅ v2.0 — 2026-03-03

### 📦 项目结构重构

1. 源代码目录化（`src/`）
2. 配置文件集中管理（`configs/`）
3. 运行脚本集中管理（`scripts/`）
4. Docker 文件集中管理（`docker/`）
5. 精简 `.gitignore` / `.dockerignore`

### ✨ 新功能

1. 自动更新检查
2. Docker 一键部署
3. 多渠道通知系统（邮件、企业微信、钉钉、Telegram、Slack、通用 Webhook）
4. GitHub Actions 定时工作流
5. 自动重试机制（tenacity 指数退避）
6. 并发处理（ThreadPoolExecutor）
7. HTML 报告生成
8. MinerU 云端 PDF 解析
9. HTML 报告 CSS 外置
10. 报告目录结构优化
11. 关键词数据目录整理
12. 日志轮转管理
13. 按数据源单独配置搜索数量
14. Makefile 便捷命令
15. VSCode 工作区配置

---

## ✅ v1.3 — 2026-03-01

### 🐛 Bug 修复

1. 修复 OpenAlex 数据源每页只处理最后一篇论文的严重 Bug
2. 修复关键词标准化 JSON 解析失败
3. 修复关键词标准化 JSON 截断问题

---

## ✅ v1.2 — 2026-02-08

### 🐛 重要修复

1. 修复 OpenAlex 源缩进错误

### ⚡ 性能优化

1. 翻译缓存机制
2. KeywordTracker 实例优化

### ✨ 功能增强

1. ArXiv 优先策略
2. 增强 Semantic Scholar 集成

---

## ✅ v1.1 — 2026-02-05

### ✨ 运行脚本增强

1. 新增虚拟环境自动检测与创建
2. 新增 macOS 运行脚本
3. 新增 Windows PowerShell 脚本
4. 增强 Linux 运行脚本

---

## ✅ v1.0 — 2026-02-06

### 🎉 首次正式发布

1. 多数据源支持（ArXiv + 20+ 学术期刊，基于 OpenAlex）
2. 智能评分系统（关键词加权 + 动态及格线）
3. 深度 PDF 分析（LLM 驱动，PyMuPDF 本地解析）
4. 关键词趋势追踪（SQLite 存储 + Mermaid 可视化）
5. AI 关键词标准化（批量语义归并）
6. Markdown 报告生成（按数据源分目录）
