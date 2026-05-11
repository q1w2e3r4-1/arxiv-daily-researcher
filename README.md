<div align="center">

# 🔬 ArXiv Daily Researcher

**基于 LLM 的智能学术论文监控、筛选、深度分析与趋势研究系统**

[![Version](https://img.shields.io/badge/version-3.2-brightgreen.svg)](CHANGELOG.md)
[![License: AGPL v3](https://img.shields.io/badge/License-AGPL%20v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/downloads/)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?logo=docker&logoColor=white)](https://www.docker.com/)
[![GitHub Actions](https://img.shields.io/badge/GitHub_Actions-Supported-2088FF?logo=github-actions&logoColor=white)](https://github.com/features/actions)
[![Streamlit](https://img.shields.io/badge/Config_Panel-Streamlit-FF4B4B?logo=streamlit&logoColor=white)](#️-streamlit-配置面板)

*每天接收高质量论文摘要；一行命令纵览一年研究趋势；一个面板完成配置、运行、预览与排障。*

</div>

---
## 作者注(使用须知)

这个项目fork自原版ArXiv Daily Researcher。本人在上面稍作修改，利用了它的爬取+总结框架，再加上了一些自己想要的内容，主要变更如下：

1. **筛选目标调整为 MLSys / AI Infra 导向**：当前更关注训练、推理、部署、调度、运行时、编译、GPU/NPU 利用、Agent 系统、端侧 / on-device / resource-constrained AI 等方向；纯系统但和 AI 无关的论文不会通过，而端侧系统，如检测到“NPU、移动端、资源受限部署”相关字眼，会获得额外加分。

2. **使用多模型平均分进行文章筛选**：在 `mlsys_multi_model` 策略下，使用多个 LLM 对论文的标题与摘要做一步式筛选。每个模型都会独立给出分数、是否通过和简短理由，系统最终直接对 4 个模型的最终分数取平均；若平均分 >= 6 则通过。若某个模型连续重试后仍失败，则记为带错误标记的 fallback 结果，并按 5 分计入平均，避免单个模型异常变成隐式反对票。

3. **使用“致远一号”模型作为服务提供商**: 这东西真是量大管饱，一个月10B token, 目前想不到怎么花，唯一的缺点就是速度慢以及模型不是很新，但对于这种非实时任务来说完全够用。这个服务商提供了四个模型：glm-5.1,minimax-m2.7,qwen3.5-27b,deepseek-v3.2，我们在评测中同时使用了这四个模型，结果显示它们的表现都不错，甚至有些指标上比之前用的模型还要好。

4. **针对Eurosys 2026的评测结果进行分析**：我们对之前跑的那轮评测结果进行了详细分析，发现了模型在准确率、召回率、F1分数等方面的表现，并且比较了单模型和委员会的结果。总体来说，glm-5.1表现最好，但委员会在暴露可能的标签误差方面也很有价值。虽然这个结果对项目本身没啥用，而且ground truth也不是很truth, 不过依然为未来可能的测试提供了一个基准。
---

ArXiv Daily Researcher 会自动从 **ArXiv** 与 **20+ 学术期刊**抓取论文，利用可配置的关键词权重评分系统筛选相关工作，下载 PDF 进行深度分析，跟踪关键词演变趋势，生成 Markdown / HTML 报告，并将结果推送到多种通知渠道。

当前版本已同时支持：
- **每日研究模式**：面向日常监控与高相关论文追踪
- **趋势研究模式**：面向指定主题的中长期趋势洞察
- **Streamlit 可视化面板**：面向日常配置、立即运行、日志查看与报告预览

---

## ✨ 核心功能

<table>
<tr>
<td colspan="2" align="center"><sub>— 数据获取 & 智能筛选 —</sub></td>
</tr>
<tr>
<td width="50%" valign="top">

### 📡 多数据源抓取

支持 **ArXiv** 与 **20+ 顶级期刊**（PRL、Nature、Science 等）。期刊论文若存在 ArXiv 版本，系统会自动切换到 ArXiv 获取更完整的摘要与可下载 PDF。可选接入 **Semantic Scholar** 补充引用数与 AI TLDR。

</td>
<td width="50%" valign="top">

### 🎯 双 LLM 评分筛选

`CHEAP_LLM` 对每篇论文按关键词逐项评分（0–10），根据**关键词权重总和**与**动态及格线**判断是否进入后续深度分析。支持主关键词、参考 PDF 自动提取关键词、专家作者加分。

</td>
</tr>
<tr>
<td colspan="2" align="center"><sub>— 深度分析 & 知识积累 —</sub></td>
</tr>
<tr>
<td width="50%" valign="top">

### 🔍 深度 PDF 分析

通过筛选的论文会自动下载 PDF，并由 `SMART_LLM` 提取 **研究方法、创新点、技术栈、关键结论、局限性、研究关联、未来方向** 七个维度。支持 **MinerU 云端解析**与 **PyMuPDF 本地解析**双模式，MinerU 不可用时自动降级。

</td>
<td width="50%" valign="top">

### 📈 关键词趋势追踪

评分阶段提取出的关键词会写入 SQLite，随后通过 AI 进行语义归并与标准化。系统可生成 Mermaid 图表与独立的 HTML 关键词趋势报告，包含**彩色柱状图、趋势热图与统一颜色图例**。

</td>
</tr>
<tr>
<td colspan="2" align="center"><sub>— 趋势研究 & 成本可观测 —</sub></td>
</tr>
<tr>
<td width="50%" valign="top">

### 🔬 趋势研究模式

独立的 `trend_research` 模式支持指定关键词、日期范围与 ArXiv 分类过滤，批量检索相关论文，逐篇生成 TLDR，并由 `SMART_LLM` **单次综合分析**热点话题、时间演变、核心研究者、研究空白与方法论趋势。

</td>
<td width="50%" valign="top">

### 📊 Token 消耗追踪

内置线程安全 Token 计数器，统计每次运行中各模型的输入 / 输出 Token 消耗，并展示在**报告末尾**与**通知消息**中，方便精确掌握运行成本。

</td>
</tr>
<tr>
<td colspan="2" align="center"><sub>— 报告输出 & 通知推送 —</sub></td>
</tr>
<tr>
<td width="50%" valign="top">

### 📄 Markdown + HTML 双格式报告

支持三类报告：**每日研究**、**趋势研究**、**关键词趋势**。Markdown 适合归档与版本管理，可独立开关；HTML 适合浏览器阅读与分享，使用外置 CSS 控制样式，已集成 **KaTeX** 公式渲染。

</td>
<td width="50%" valign="top">

### 🔔 六渠道通知

支持 **邮件、企业微信、钉钉、Telegram、Slack、通用 Webhook**。每个渠道均有独立启用开关；邮件支持 HTML 模板；运行异常（MinerU 过期、LLM 异常、网络问题）实时告警。

</td>
</tr>
<tr>
<td colspan="2" align="center"><sub>— 配置管理 & 部署运维 —</sub></td>
</tr>
<tr>
<td width="50%" valign="top">

### 🧙 交互式配置向导

首次部署可通过 7 步 CLI 向导完成 LLM、搜索、数据源、关键词、评分、通知与高级设置。Docker 首次部署时可**自动触发**，并自动生成 `.env` 与 `configs/config.json`。

</td>
<td width="50%" valign="top">

### 🖥️ Streamlit 配置面板 <sup><kbd>v3.2</kbd></sup>

提供 **11 个 Tab** 的浏览器管理界面：每日推送（运行管理 + 报告开关）、报告查看、趋势分析、关键词、搜索、评分、通知、数据管理（配置导出 + WebDAV 同步）、API 配置、网络代理与高级设置。

</td>
</tr>
<tr>
<td width="50%" valign="top">

### 🚀 三种部署方式

支持 **Docker 容器**（推荐）、**本地脚本 + Cron**、**GitHub Actions** 三种部署模式。Docker 是首选方案，开箱即用，生产稳定。

</td>
<td width="50%" valign="top">

### 🛡️ 生产级可靠性

内置**指数退避重试**、**MinerU 智能降级**、**文件锁防重并发**、**锁超龄回收**、**运行专用日志**、**自动更新检查**、**网络代理**与**WebDAV 跨设备数据同步**，适合长期无人值守运行。

</td>
</tr>
</table>

---

## 📑 导航目录

<table>
<tr>
<td width="50%" valign="top">

### 📘 快速上手

|           章节           | 简介                        |
| :----------------------: | :-------------------------- |
| [✨ 核心功能](#-核心功能) | 核心能力总览                |
| [🚀 快速开始](#-快速开始) | 三步完成首次运行            |
| [🛠️ 配置工具](#️-配置工具) | CLI 向导 + Streamlit 面板   |
| [🐳 部署方式](#-部署方式) | Docker / Actions / 本地定时 |

</td>
<td width="50%" valign="top">

### 📗 深入了解

|            章节            | 简介                         |
| :------------------------: | :--------------------------- |
|  [📖 功能详解](#-功能详解)  | 运行模式、报告、通知、锁机制 |
|  [📁 项目结构](#-项目结构)  | 目录与模块说明               |
|  [❓ 常见问题](#-常见问题)  | 10 个实战排障与深度使用指南  |
| [📝 更新日志](CHANGELOG.md) | 完整版本变更历史             |

</td>
</tr>
</table>

---

## 🚀 快速开始

### 第一步：克隆与安装

```bash
git clone https://github.com/yzr278892/arxiv-daily-researcher.git
cd arxiv-daily-researcher
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 第二步：完成配置

推荐先运行交互式配置向导：

```bash
python src/utils/setup_wizard.py
```

向导会引导你完成：

- LLM 配置
- 搜索参数
- 数据源选择
- 关键词与研究背景
- 评分参数
- 通知渠道
- 高级设置

完成后自动生成：
- `.env`
- `configs/config.json`

> [!TIP]
> 若已有配置，向导会预填已有值；只需修改想变更的字段，其余按 Enter 保留。

<details>
<summary><b>手动配置（跳过向导）</b></summary>

**1）复制环境变量模板：**

```bash
cp .env.example .env
```

**2）填写 LLM：**

```env
CHEAP_LLM__API_KEY=sk-your-key
CHEAP_LLM__BASE_URL=https://api.openai.com/v1
CHEAP_LLM__MODEL_NAME=gpt-4o-mini

SMART_LLM__API_KEY=sk-your-key
SMART_LLM__BASE_URL=https://api.openai.com/v1
SMART_LLM__MODEL_NAME=gpt-4o
```

**3）填写核心关键词与领域：**

```jsonc
{
  "keywords": {
    "primary_keywords": {
      "weight": 1.0,
      "keywords": ["quantum error correction", "surface code"]
    },
    "research_context": "我的研究方向是容错量子计算与量子纠错码"
  },
  "target_domains": {
    "domains": ["quant-ph"]
  }
}
```

</details>

### 第三步：运行

```bash
# 每日研究模式（默认）
python main.py

# 趋势研究模式
python main.py --mode trend_research --keywords "quantum error correction"
```

运行结果默认输出到：
- 报告：`data/reports/`
- 日志：`logs/`

---

## 🛠️ 配置工具

本项目提供两种主要配置方式：**CLI 配置向导**与 **Streamlit 配置面板**。

### 🧙 交互式配置向导

适合首次部署、SSH 环境与无头服务器：

```bash
python src/utils/setup_wizard.py
```

| 步骤  | 内容     | 说明                                      |
| :---: | :------- | :---------------------------------------- |
|   1   | LLM 配置 | 选择 Provider、填写 API Key、可选连接测试 |
|   2   | 搜索设置 | 搜索天数、每源最大结果数                  |
|   3   | 数据源   | ArXiv 与期刊启用、ArXiv 分类              |
|   4   | 关键词   | 主关键词、参考 PDF 提取、研究背景         |
|   5   | 评分     | 基础分、权重系数、作者加分                |
|   6   | 通知     | 渠道启用与凭据填写                        |
|   7   | 高级设置 | PDF 解析、并发、日志保留等                |

向导写入前会自动备份已有配置到 `.bak` 文件。

---

### 🖥️ Streamlit 配置面板

#### 启动方式

```bash
# 本地运行
streamlit run src/webui/config_panel.py
```

```bash
# Docker 运行
docker compose up -d config-panel
```

浏览器访问：`http://localhost:8501`

配置面板与主程序共用同一套 `.env` 和 `configs/config.json`，修改后在下次任务运行时立即生效。

#### 11 个 Tab 页详解

|   #   | Tab          | 功能                                                                                                                                                         |
| :---: | :----------- | :----------------------------------------------------------------------------------------------------------------------------------------------------------- |
|   1   | **每日推送** | 一键立即运行每日研究；运行状态监控（锁文件 / PID）；**每日研究设置**（HTML 报告 / Markdown 报告 / 包含所有论文）；运行日志查看器，刷新自动跳转最新非系统日志 |
|   2   | **报告查看** | 三列展示每日研究 / 趋势研究 / 关键词趋势 HTML 报告；默认自动打开最新可见报告；支持报告预览、趋势 metadata 展示、同数据源前后日期导航                         |
|   3   | **趋势分析** | 设置关键词、日期范围、分类过滤、排序、最大结果数、TLDR、Markdown / HTML 双开关输出格式与 Skill，一键启动 / 停止趋势研究任务                                  |
|   4   | **关键词**   | 管理主关键词、参考 PDF 提取、相似度阈值、权重分布、研究背景                                                                                                  |
|   5   | **搜索**     | 搜索天数、单源抓取数量、数据源开关、ArXiv 分类与抓取超时                                                                                                     |
|   6   | **评分**     | 及格线公式、每关键词最高分、作者加分、实时评分预览                                                                                                           |
|   7   | **通知**     | 全局开关、成功 / 失败 / 附件控制、六大渠道配置、SMTP 测试                                                                                                    |
|   8   | **数据管理** | 一键导出配置文件（config.json + .env）为 zip；**WebDAV 同步**（手动 / 定时 / 报告后自动），含连接测试、上传、下载                                            |
|   9   | **API**      | 配置 CHEAP_LLM / SMART_LLM / MinerU，支持连接测试                                                                                                            |
|  10   | **网络代理** | HTTP/SOCKS5 代理配置，支持 per-service 粒度控制（ArXiv / OpenAlex / Semantic Scholar / LLM API / 通知 / 检查更新），兼容 Docker 与 GitHub Actions            |
|  11   | **高级**     | PDF 解析模式、并发、Token 追踪、自动更新检查、关键词趋势追踪、重试、日志轮转与运行锁超龄回收                                                                 |

### 🖼️ WebUI 界面预览

<table>
  <tr>
    <td align="center" width="50%">
      <img src="assets/img_en.png" alt="English WebUI" width="100%" />
      <br />
      <sub>英文 WebUI 主界面</sub>
    </td>
    <td align="center" width="50%">
      <img src="assets/img_noti.png" alt="Notification settings" width="100%" />
      <br />
      <sub>中文通知设置界面</sub>
    </td>
  </tr>
  <tr>
    <td align="center" width="50%">
      <img src="assets/img_prev.png" alt="Report preview" width="100%" />
      <br />
      <sub>中文报告预览界面</sub>
    </td>
    <td align="center" width="50%">
      <img src="assets/img_serh.png" alt="Search sources settings" width="100%" />
      <br />
      <sub>中文搜索源设置界面</sub>
    </td>
  </tr>
</table>

<details>
<summary><b>配置向导 vs 配置面板，该用哪个？</b></summary>

| 工具                             | 适用场景                    | 特点                                          |
| :------------------------------- | :-------------------------- | :-------------------------------------------- |
| **配置向导** (`setup_wizard.py`) | 首次部署、SSH、无浏览器环境 | CLI 交互、适合初始化、可连接测试              |
| **配置面板** (`config_panel.py`) | 日常调参、报告预览、排障    | 11 个 Tab，所见即所得，支持运行管理与趋势分析 |

**建议**：首次安装先跑向导，后续日常使用面板更高效。

</details>

---

## 🐳 部署方式

### Docker 部署 <sup>推荐</sup>

Docker 是**推荐部署方式**，适合长期后台运行。默认主研究容器使用 `network_mode: host`，便于直接访问宿主机本地 LLM 服务。

#### 启动

```bash
git clone https://github.com/yzr278892/arxiv-daily-researcher.git
cd arxiv-daily-researcher
cp .env.example .env
docker compose up -d
```

默认容器行为：
- `CRON_SCHEDULE=0 8 * * *`
- `RUN_ON_STARTUP=false`
- `MODE=cron`
- `SETUP_WIZARD=auto`

也就是说，默认会：
1. 首次部署时自动检查是否需要启动配置向导
2. 同时启动主研究服务与 WebUI 配置面板（`http://localhost:8501`）
3. 主研究容器启动后不立即运行（如需立即运行可将 `RUN_ON_STARTUP` 设为 `true`）
4. 后续每天 08:00 自动执行

#### 常用命令

```bash
# 查看运行状态
docker compose ps

# 查看日志
docker compose logs -f

# 启动 / 停止 WebUI
docker compose up -d config-panel
docker compose stop config-panel

# 容器内直接执行趋势研究
docker exec -it arxiv-daily-researcher python main.py --mode trend_research \
  --keywords "quantum error correction" \
  --date-from 2025-01-01 \
  --categories quant-ph

# 停止主服务
docker compose down
```

#### WebUI 立即运行机制

WebUI 通过共享卷写入触发文件来请求主容器执行任务：
- WebUI 写入：`data/run/webui_run_trigger.flag`
- 主容器 `entrypoint.sh` 中的 `trigger_watcher` 每 5 秒轮询
- 检测到后启动 `python main.py --mode daily_research`
- 运行日志写入 `logs/manual_*.log`
- 真正的 Python PID 写入 `data/run/webui_triggered.pid`

<details>
<summary><b>容器环境变量</b></summary>

| 变量             | 默认值          | 说明                                               |
| :--------------- | :-------------- | :------------------------------------------------- |
| `TZ`             | `Asia/Shanghai` | 时区                                               |
| `CRON_SCHEDULE`  | `0 8 * * *`     | 每日定时执行时间                                   |
| `RUN_ON_STARTUP` | `false`         | 启动时是否立即运行一次（默认否）                   |
| `MODE`           | `cron`          | `cron` 为定时模式，`run-once` 为单次执行           |
| `SETUP_WIZARD`   | `auto`          | `auto` 首次自动触发，`true` 强制触发，`false` 跳过 |

</details>

<details>
<summary><b>使用本地 LLM（Ollama 等）</b></summary>

由于主研究容器使用 `network_mode: host`，可以直接访问宿主机上的本地服务：

```env
CHEAP_LLM__API_KEY=ollama
CHEAP_LLM__BASE_URL=http://127.0.0.1:11434/v1
CHEAP_LLM__MODEL_NAME=qwen2.5:7b
```

</details>

---

### GitHub Actions 云端运行

适合没有常驻服务器的场景。支持两个工作流：
- `daily-run.yml`：每日研究
- `trend-research.yml`：手动趋势研究

> [!IMPORTANT]
> **使用建议**：GitHub Actions 适合简单使用或测试。请遵守 GitHub 使用规则，不要滥用 Actions 资源。`daily-run.yml` 中的定时触发默认是**注释掉的**，需要时再手动启用。**长期生产使用推荐 Docker 部署**。

#### 配置步骤

1. Fork 本仓库
2. 进入 **Settings → Secrets and variables → Actions**
3. 配置至少以下 Secrets：

| Secret 名称            | 必填  | 说明                         |
| :--------------------- | :---: | :--------------------------- |
| `CHEAP_LLM_API_KEY`    |   ✅   | 低成本 LLM API Key           |
| `CHEAP_LLM_BASE_URL`   |   ✅   | 低成本 LLM API 地址          |
| `CHEAP_LLM_MODEL_NAME` |   ✅   | 低成本 LLM 模型              |
| `SMART_LLM_API_KEY`    |   ✅   | 高性能 LLM API Key           |
| `SMART_LLM_BASE_URL`   |   ✅   | 高性能 LLM API 地址          |
| `SMART_LLM_MODEL_NAME` |   ✅   | 高性能 LLM 模型              |
| 通知相关 Secrets       | 可选  | SMTP / Telegram / Webhook 等 |

> [!NOTE]
> `daily-run.yml` 中的 `schedule:` 默认是注释掉的。Fork 后请先配置 Secrets，再取消注释定时触发，避免空配置导致失败。

#### 手动趋势研究

`trend-research.yml` 支持传入：
- `keywords`
- `date_from`
- `date_to`
- `categories`
- `sort_order`
- `max_results`

报告会作为 Artifact 保存 30 天。

---

### 本地定时运行（系统 Cron）

如果你不想使用 Docker 或 GitHub Actions，也可以直接使用系统 Cron：

```bash
crontab -e
0 8 * * * cd /path/to/arxiv-daily-researcher && ./scripts/run_daily.sh >> /tmp/arxiv-cron.log 2>&1
```

---

## 📖 功能详解

### 🔄 两种运行模式

| 维度     | `daily_research`（默认）       | `trend_research`               |
| :------- | :----------------------------- | :----------------------------- |
| 定位     | 每日自动追踪最新论文           | 指定主题的长期趋势分析         |
| 数据源   | ArXiv + 期刊                   | ArXiv                          |
| 时间范围 | 最近 N 天                      | 任意日期区间                   |
| 筛选方式 | 关键词加权评分                 | 无评分，全量保留               |
| 核心分析 | 高分论文 PDF 深度分析          | 全量 TLDR + 趋势综合分析       |
| 触发方式 | Cron / Docker / Actions / 面板 | CLI / 面板 / Actions           |
| 输出路径 | `data/reports/daily_research/` | `data/reports/trend_research/` |

### 📅 每日研究流水线

```text
1. 准备关键词与动态及格线
2. 从 ArXiv / 期刊抓取论文
3. 跳过历史已处理论文
4. 使用 CHEAP_LLM 逐关键词评分
5. 提取并追踪论文关键词
6. 对通过筛选的论文执行 PDF 深度分析
7. 生成 Markdown 报告（可独立关闭）/ HTML 报告（可独立关闭）
8. 发送通知
```

### 🔬 趋势研究流水线

```text
1. 按关键词、日期、分类搜索 ArXiv
2. 逐篇生成 TLDR
3. 由 SMART_LLM 综合分析五个维度
4. 输出 Markdown / HTML 报告（双开关独立控制）/ metadata.json
5. 推送趋势分析通知
```

### 🎯 动态及格线公式

当前配置文件中的默认示例为：

```text
及格线 = base_score + weight_coefficient × Σ(关键词权重)
```

在当前仓库默认 `configs/config.json` 中：
- `base_score = 1.5`
- `weight_coefficient = 2.5`

你可以在 **每日推送** Tab 的「每日研究设置」或 `configs/config.json` 中自由调整。

### 📡 数据源与 ArXiv 优先策略

- ArXiv：使用官方 `arxiv` Python 库抓取
- 期刊：通过 OpenAlex 获取最新论文
- 若期刊论文存在 ArXiv 版本，优先切换到 ArXiv 元数据与 PDF
- 可选接入 Semantic Scholar 获取引用数与 AI TLDR

### 🔍 PDF 解析与智能降级

支持两种解析方式：

| 模式      | 优点                         | 限制                |
| :-------- | :--------------------------- | :------------------ |
| `mineru`  | 结构化效果更好，适合复杂论文 | 需要 Token          |
| `pymupdf` | 纯本地、零外部依赖           | 解析质量受 PDF 影响 |

当 MinerU 不可用时，系统会自动降级到 PyMuPDF，避免整次任务失败。

### 📈 关键词趋势追踪

关键词追踪模块会：
- 将原始关键词写入 SQLite
- 用 AI 对关键词做批量标准化
- 生成频率统计与趋势图
- 输出独立 HTML 关键词趋势报告

常用配置项：
- `keyword_tracker.enabled`
- `keyword_normalization_enabled`
- `keyword_normalization_batch_size`
- `keyword_report_frequency`

### 🔒 并发运行互斥锁

为避免重复运行，系统使用 `fcntl` 文件锁：

| 模式             | 锁文件                                 |
| :--------------- | :------------------------------------- |
| `daily_research` | `data/run/daily_research.lock`         |
| `trend_research` | `data/run/trend_research_<hash8>.lock` |

特点：
- 相同任务重复启动时直接安全退出
- 锁文件写入 PID 与启动时间
- 支持**超龄锁回收**（默认 12 小时）
- 回收失败时保守退出，避免双实例并发

### ⏱️ ArXiv 抓取超时守卫

ArXiv 抓取已加入硬超时保护：
- 配置项：`data_sources.arxiv.fetch_timeout_seconds`
- 当前默认值：`180`
- 单个领域超时后会重试并记录日志

### 📄 报告系统

#### 每日研究报告

路径：
- `data/reports/daily_research/markdown/<source>/`
- `data/reports/daily_research/html/<source>/`

Markdown 和 HTML 报告**可独立开关**（在「每日推送」Tab 的「每日研究设置」中配置）。

内容通常包括：
- 统计摘要
- 通过论文详情
- 未通过论文列表
- 深度分析结果
- 关键词趋势图
- Token 消耗统计

#### 趋势研究报告

路径：
- `data/reports/trend_research/markdown/<keyword_slug>/`
- `data/reports/trend_research/html/<keyword_slug>/`

同时生成：
- `*_metadata.json`

#### 关键词趋势报告

路径：
- `data/reports/keyword_trend/markdown/`
- `data/reports/keyword_trend/html/`

### 🔔 通知系统

支持六个渠道：
- Email
- 企业微信
- 钉钉
- Telegram
- Slack
- 通用 Webhook

通知开关分为两层：
1. 全局通知总开关
2. 各渠道独立开关

渠道只有在**配置已填写**且**对应 enabled=true** 时才会真正发送。

---

## 📁 项目结构

```text
arxiv-daily-researcher/
├── main.py                          # CLI 入口，按模式分发
├── .env.example                     # 环境变量模板
├── requirements.txt                 # Python 依赖
├── README.md
│
├── src/
│   ├── config.py                    # 全局配置加载
│   ├── modes/                       # 两种运行模式
│   │   ├── daily_research.py
│   │   └── trend_research.py
│   ├── agents/                      # LLM 分析相关 Agent
│   ├── sources/                     # ArXiv / OpenAlex / 搜索编排
│   ├── report/                      # daily / trend / keyword_trend 报告生成
│   ├── notifications/               # 多渠道通知
│   ├── parsers/                     # PDF 解析
│   ├── keyword_tracker/             # 关键词追踪与标准化
│   ├── utils/                       # 配置、日志、锁、Token、向导、WebDAV 等工具
│   │   ├── config_io.py
│   │   ├── updater.py
│   │   └── webdav_sync.py           # WebDAV 同步模块
│   └── webui/                       # Streamlit 配置面板
│       ├── config_panel.py
│       ├── i18n.py
│       └── tabs/
│           ├── run_manager.py       # 每日推送
│           ├── reports.py           # 报告查看
│           ├── trend_runner.py      # 趋势分析
│           ├── keywords.py
│           ├── search.py
│           ├── scoring.py
│           ├── notifications.py
│           ├── data_management.py   # 配置导出 + WebDAV 同步
│           ├── proxy.py             # 网络代理
│           ├── llm.py
│           └── advanced.py
│
├── configs/
│   ├── config.json                  # 主配置文件（JSONC）
│   └── templates/                   # 报告、通知、邮件模板
│
├── docker-compose.yml               # Docker Compose 编排文件
├── docker/
│   ├── Dockerfile
│   ├── Dockerfile.webui
│   └── entrypoint.sh
│
├── VERSION                          # 版本号（用于 Docker 更新检查）
├── scripts/                         # 运行脚本与 Makefile
├── assets/                          # README / WebUI 预览图片
├── data/                            # 运行数据（自动创建）
└── logs/                            # 系统日志与每次运行日志
```

---

## ❓ 常见问题

<details>
<summary><b>1. WebDAV 连接坚果云总是提示失败（403）怎么办？</b></summary>

坚果云 WebDAV 服务器**不支持 HTTP HEAD 方法**，而大多数 WebDAV 客户端库使用 HEAD 来检测资源是否存在。本项目已内置兼容处理（使用 PROPFIND 替代 HEAD 进行存在性检查）。

如果仍遇到连接问题，请检查：
- WebDAV URL 是否以 `https://dav.jianguoyun.com/dav/` 结尾
- 密码是否为坚果云的**应用专用密码**（在坚果云账户安全设置中生成，而非登录密码）
- 在 WebUI「数据管理」Tab 中点击「测试连接」确认凭据有效
</details>

<details>
<summary><b>2. 趋势分析如何选择合适的参数？</b></summary>

几个关键建议：
- **日期范围**：初次使用建议 90-180 天（`--date-from`），避免范围过大导致结果过多
- **分类过滤**：使用 `--categories` 限定到相关领域（如 `quant-ph cond-mat`），大幅提升精度
- **输出格式**：Markdown 和 HTML 均可独立开关，在 WebUI 趋势分析 Tab 中直接切换
- **Skill 选择**：默认 `comprehensive_analysis` 单次覆盖全部五个维度，适合多数场景；如需单独分析某一维度，可启用对应 Skill
- **max_results**：默认 500，如果结果很多但分析速度慢，可以降低到 200；反之可以提升到 1000
</details>

<details>
<summary><b>3. 任务提示"已在运行中"，但我怀疑是残留锁怎么办？</b></summary>

系统已支持多层保护：
- **死进程残留锁自动清理**：启动时检查 PID 是否存活，不存活则自动回收
- **超龄锁自动回收**：超过 `run_lock_max_age_hours`（默认 12 小时）的锁会被回收
- **手动清理**：在 WebUI「每日推送」Tab 的「当前运行状态」区，点击停止任务的「清理」按钮；或直接删除 `data/run/*.lock` 文件

> [!WARNING]
> 仅在不确定 PID 是否存活时才手动清理锁。如果进程确实在运行，删除锁可能导致重复运行。
</details>

<details>
<summary><b>4. Docker 中如何配置和使用本地 LLM（Ollama / vLLM / LocalAI）？</b></summary>

主研究容器默认使用 `network_mode: host`，因此可以直接访问宿主机上的本地 LLM 服务：

```env
CHEAP_LLM__API_KEY=ollama
CHEAP_LLM__BASE_URL=http://127.0.0.1:11434/v1
CHEAP_LLM__MODEL_NAME=qwen2.5:7b
```

如果使用桥接网络模式（WebUI 容器等），需要将 `127.0.0.1` 换成 `host.docker.internal`（Windows/Mac）或宿主机真实 IP（Linux）。

确保本地 LLM 服务已监听 `0.0.0.0` 而非 `127.0.0.1`，否则容器无法访问。
</details>

<details>
<summary><b>5. WebUI 的「立即运行」是如何与主容器协同的？</b></summary>

Docker 模式下采用**文件触发机制**，无需 Docker Socket：

1. 用户在 WebUI 点击「立即运行」
2. WebUI 容器写入触发文件到共享卷 `data/run/webui_run_trigger.flag`
3. 主容器的 `trigger_watcher` 每 5 秒轮询该文件
4. 检测到触发后，主容器启动 `python main.py --mode daily_research`
5. 真正的 Python PID 写入 `data/run/webui_triggered.pid`
6. 运行日志写入 `logs/manual_*.log`，WebUI 可实时查看

关键是两个容器必须挂载**相同的** `data/` 和 `logs/` 卷。
</details>

<details>
<summary><b>6. 如何配置网络代理？代理可以按服务粒度控制吗？</b></summary>

在 WebUI「网络代理」Tab 或 `configs/config.json` 的 `proxy` 块中配置：

- **全局开关**：`proxy.enabled`
- **代理地址**：`proxy.url`，支持 HTTP/SOCKS5（如 `http://127.0.0.1:7890`）
- **服务粒度控制**（`proxy.scope`）：可独立控制 ArXiv、OpenAlex、Semantic Scholar、LLM API、通知、检查更新是否走代理

Docker 注意：
- `network_mode: host` 模式下用 `127.0.0.1`
- 桥接模式下 Linux 需 `--add-host=host.docker.internal:host-gateway`
</details>

<details>
<summary><b>7. Markdown 和 HTML 报告有什么区别？可以只生成一种吗？</b></summary>

两者内容相同，格式不同：
- **Markdown**：适合 Git 版本管理、归档、纯文本编辑
- **HTML**：适合浏览器阅读、分享，含样式与 KaTeX 公式渲染

在 WebUI「每日推送」Tab 的「每日研究设置」中，可独立开关 Markdown 和 HTML 报告的生成。趋势分析报告也有独立的 Markdown/HTML 开关（在「趋势分析」Tab）。关闭不需要的格式可节省存储空间和生成时间。
</details>

<details>
<summary><b>8. 关键词追踪是如何工作的？可以关闭吗？</b></summary>

关键词追踪流程：
1. CHEAP_LLM 在评分阶段自动从论文标题、摘要中提取关键词
2. 提取的关键词写入 SQLite 数据库
3. AI 对原始关键词做批量语义归并（如 "quantum computing" 和 "quantum computation" 合并）
4. 定期生成关键词趋势报告（频率可在 WebUI 设置：每日/每周/每月/始终）

可以在 WebUI「高级」Tab 或 `config.json` 中将 `keyword_tracker.enabled` 设为 `false` 来关闭追踪。关闭后评分结果中仍会标注关键词，但不会存入数据库或生成趋势报告。
</details>

<details>
<summary><b>9. MinerU PDF 解析和 PyMuPDF 如何选择？MinerU Token 过期了怎么办？</b></summary>

| 场景                           | 推荐模式  |
| :----------------------------- | :-------- |
| 追求解析质量、处理复杂排版论文 | `mineru`  |
| 无外部依赖、离线环境、长期稳定 | `pymupdf` |

在 WebUI「API」Tab 或「高级」Tab 切换。

MinerU Token 有效期 3 个月，过期后：
- 系统会**自动降级**到 PyMuPDF，不会中断运行
- 同时发送错误告警通知（如果通知渠道已配置）
- 到 [mineru.net](https://mineru.net/apiManage/apiKey) 重新申请 Token 并更新配置即可
</details>

<details>
<summary><b>10. 如何利用 WebDAV 同步在多台设备间共享配置和报告？</b></summary>

WebDAV 同步支持三种模式（在 WebUI「数据管理」Tab 配置）：

| 模式           | 说明                                   |
| :------------- | :------------------------------------- |
| **手动**       | 在 WebUI 中点击「上传」或「下载」按钮  |
| **定时**       | 按 cron 表达式自动执行（如每天 23:00） |
| **报告后自动** | 每次每日研究报告生成后自动上传         |

同步范围可选：配置文件（config.json）、历史记录、关键词数据、报告文件。默认仅同步配置文件。

典型用法：主设备设置「报告后自动」上传，辅设备设置「手动」模式，按需下载恢复配置和数据。
</details>

---

## 📜 许可证

本项目采用 [AGPL-3.0](https://www.gnu.org/licenses/agpl-3.0.html) 许可证。

| 条款       | 说明                                     |
| :--------- | :--------------------------------------- |
| ✅ 使用     | 可自由使用、修改、分发                   |
| ✅ 商用     | 允许商业使用                             |
| 📋 源码公开 | 修改后的版本须公开源代码并使用相同许可证 |
| 🌐 网络使用 | 通过网络提供服务时也须公开源代码         |
| 📝 声明     | 需保留原始版权声明和许可证               |

---

## 💬 社区与反馈

项目持续活跃开发中。欢迎通过以下方式参与：

- **🐛 报告问题**：[GitHub Issues](https://github.com/yzr278892/arxiv-daily-researcher/issues) — 遇到 Bug 或有功能建议，欢迎提交 Issue
- **🔀 贡献代码**：Fork → 修改 → Pull Request，我们欢迎任何改进
- **⭐ Star**：如果这个项目对你有帮助，点亮 Star 是对我们最大的鼓励

---

## 🤝 API 使用说明

本项目遵循各 API 提供方的使用规范，确保合规调用：

| API                  | 合规措施                                                                |
| :------------------- | :---------------------------------------------------------------------- |
| **ArXiv**            | 使用官方 `arxiv` Python 库，内置 6 秒请求延迟                           |
| **OpenAlex**         | 请求头包含联系方式，建议配置 `OPENALEX_EMAIL` 进入礼貌池（Polite Pool） |
| **Semantic Scholar** | 请求头含 User-Agent，支持配置 API Key 获取更高速率                      |
| **MinerU**           | 遵守每日 2000 页优先级额度限制，超出后自动降至普通优先级                |

> [!NOTE]
> 所有外部 API 调用均配有指数退避自动重试机制，网络波动不会导致运行中断。

---

## 🙏 致谢

- 感谢 [Claude](https://www.anthropic.com/claude) 与 [Claude Code](https://claude.ai/code) 在本项目开发过程中的辅助
- 感谢 [ArXiv](https://arxiv.org/)、[OpenAlex](https://openalex.org/)、[Semantic Scholar](https://www.semanticscholar.org/) 提供开放学术数据
- 感谢 [MinerU](https://mineru.net/) 提供云端 PDF 解析能力

---

## 📝 更新日志

完整的版本变更历史请查看 **[CHANGELOG.md](CHANGELOG.md)**。

### 最新版本摘要

<table>
<tr><th>版本</th><th>日期</th><th>类型</th><th>亮点</th></tr>
<tr><td><b>v3.2</b></td><td>2026-04-26</td><td>✨ 增强 + 🐛 修复</td><td>网络代理（per-service 粒度）、WebDAV 数据同步（含坚果云兼容修复）、配置一键导出、Docker 更新通知、日常推送 Tab（原运行管理重组）、Markdown/HTML 报告独立开关、趋势分析双开关输出、运行日志刷新自动跳转、ArXiv 抓取优化与早停、每日深度分析可配置</td></tr>
<tr><td><b>v3.1</b></td><td>2026-04-15</td><td>✨ 增强 + 🐛 修复</td><td>运行管理 Tab、日志查看器升级、趋势分析 Tab、报告查看增强、ArXiv 超时守卫、运行锁超龄回收</td></tr>
<tr><td><b>v3.0</b></td><td>2026-03-09</td><td>✨ 重大更新</td><td>研究趋势模式、趋势分析 GitHub Actions 工作流、综合趋势分析、Token 追踪、配置向导自动触发、并发运行互斥锁、运行专用日志、Streamlit 配置面板（含报告查看）、关键词趋势 HTML 报告</td></tr>
</table>

[查看完整更新历史 →](CHANGELOG.md)

---

<div align="center">

如果这个项目对你有帮助，欢迎点一个 **Star** ⭐

[![Star History Chart](https://api.star-history.com/svg?repos=yzr278892/arxiv-daily-researcher&type=Date)](https://star-history.com/#yzr278892/arxiv-daily-researcher&Date)

[![Issues](https://img.shields.io/github/issues/yzr278892/arxiv-daily-researcher?style=flat-square&label=Issues)](https://github.com/yzr278892/arxiv-daily-researcher/issues)
[![Email](https://img.shields.io/badge/Email-联系作者-blue?style=flat-square)](mailto:yzr278892@gmail.com)

</div>
