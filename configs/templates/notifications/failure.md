# 通知模板 — 运行失败
#
# 可用变量（使用 {变量名} 引用）：
#   {status}           — 状态文本（SUCCESS / FAILED）
#   {timestamp}        — 运行时间戳
#   {total_fetched}    — 抓取论文总数
#   {total_qualified}  — 及格论文总数
#   {total_analyzed}   — 深度分析论文总数
#   {source_summary}   — 各数据源统计（已格式化）
#   {report_list}      — 报告路径列表（已格式化）
#   {top_papers}       — Top-N 论文列表（已格式化）
#   {error_message}    — 错误信息
#
# 修改此文件即可自定义失败通知的样式和内容。

## ArXiv Daily Researcher

<font color="warning">**运行失败**</font> | {timestamp}

**错误信息**
> <font color="warning">{error_message}</font>

**运行统计**
> 抓取 **{total_fetched}** 篇 | 及格 **{total_qualified}** 篇 | 深度分析 **{total_analyzed}** 篇

{source_summary}
