# 通知模板 — MinerU 错误告警
#
# 可用变量（使用 {变量名} 引用）：
#   {timestamp}    — 发生时间
#   {error_code}   — MinerU 错误码
#   {error_detail} — 错误详细描述
#   {suggestion}   — 建议的处理方式
#
# 当 MinerU API 出现不可恢复错误时发送此通知（Token 过期、额度耗尽等）。
# 可重试的临时错误（服务暂时不可用等）不会触发通知。
# 修改此文件即可自定义 MinerU 错误通知的样式和内容。

## ArXiv Daily Researcher

<font color="warning">**MinerU 服务异常**</font> | {timestamp}

**错误详情**
> 错误码: `{error_code}`
> {error_detail}

**处理建议**
> {suggestion}

<font color="comment">本次运行已自动降级为 PyMuPDF 本地解析，不影响核心功能。</font>
