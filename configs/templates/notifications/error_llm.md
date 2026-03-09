# 通知模板 — LLM API 错误告警
#
# 可用变量（使用 {变量名} 引用）：
#   {timestamp}    — 发生时间
#   {llm_type}     — LLM 类型（CHEAP_LLM / SMART_LLM）
#   {model_name}   — 模型名称
#   {error_detail} — 错误详细描述
#   {suggestion}   — 建议的处理方式
#
# 当 LLM API 调用出现严重错误时发送此通知（认证失败、余额不足等）。
# 修改此文件即可自定义 LLM 错误通知的样式和内容。

## ArXiv Daily Researcher

<font color="warning">**LLM API 异常**</font> | {timestamp}

**错误详情**
> 类型: `{llm_type}` | 模型: `{model_name}`
> {error_detail}

**处理建议**
> {suggestion}

<font color="comment">请检查 .env 中的 API Key 和余额配置。</font>
