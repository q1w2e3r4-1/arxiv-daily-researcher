# 通知模板 — 网络错误告警
#
# 可用变量（使用 {变量名} 引用）：
#   {timestamp}    — 发生时间
#   {service}      — 出错的服务名称（ArXiv / OpenAlex / Semantic Scholar 等）
#   {error_detail} — 错误详细描述
#   {suggestion}   — 建议的处理方式
#
# 当外部服务连接出现严重错误时发送此通知。
# 修改此文件即可自定义网络错误通知的样式和内容。

## ArXiv Daily Researcher

<font color="warning">**服务连接异常**</font> | {timestamp}

**错误详情**
> 服务: `{service}`
> {error_detail}

**处理建议**
> {suggestion}

<font color="comment">系统会自动重试，如持续失败请检查网络连接或 API 配置。</font>
