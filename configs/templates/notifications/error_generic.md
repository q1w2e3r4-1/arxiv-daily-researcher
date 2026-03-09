# 通知模板 — 通用错误告警
#
# 可用变量（使用 {变量名} 引用）：
#   {timestamp}    — 发生时间
#   {error_type}   — 错误类型
#   {error_detail} — 错误详细描述
#   {suggestion}   — 建议的处理方式
#
# 当出现未分类的错误时发送此通知。
# 修改此文件即可自定义通用错误通知的样式和内容。

## ArXiv Daily Researcher

<font color="warning">**系统异常**</font> | {timestamp}

**错误详情**
> 类型: `{error_type}`
> {error_detail}

**处理建议**
> {suggestion}

<font color="comment">详细错误信息已记录到 logs/system.log。</font>
