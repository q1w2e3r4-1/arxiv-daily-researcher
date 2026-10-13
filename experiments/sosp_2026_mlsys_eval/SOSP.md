# SOSP 2026 — AI infra 筛选一致性评测

记录日期：2026-10-13。论文来源：[SOSP 2026 官方录用名单](https://sigops.org/s/conferences/sosp/2026/accepted.html)与[会议日程](https://sigops.org/s/conferences/sosp/2026/schedule.html)，共 62 篇。

## 结论

DeepSeek 在本批已有明确标签的论文上，与 Luna 粗筛的入选／排除判断完全一致：**57/57（100%）**。用户随后确认两篇边界论文应排除；更新 v1.9 后，这两篇各测三次均被排除，六篇正向对照均保留。

比较基准是 Luna 粗筛及用户后续人工范围修正。此结果衡量样本上的分类一致性，不是以完整人工 ground truth 计算的准确率，也不证明所有随机运行都相同。

## 第一轮：v1.8 全名单盲评

使用 API 模型别名 `deepseek-reasoner` 和 MLSys prompt v1.8，入选阈值为 6。62 篇均具备原文摘要；输入只有标题、摘要及会议来源，不包含 Luna 的分类、理由或分数。复用项目正式 `AnalysisAgent` 评分代码，62 篇均调用成功。

| Luna 原分类 | 篇数 | DeepSeek 入选 | DeepSeek 排除 | 比较结论 |
|---|---:|---:|---:|---|
| 明确入选 | 10 | 10 | 0 | 10/10 一致 |
| 明确排除 | 47 | 0 | 47 | 47/47 一致 |
| 待定 | 5 | 2 | 3 | 未计入明确项一致率 |
| 合计 | 62 | 12 | 50 | 明确项 57/57 一致 |

47 篇原排除论文中，39 篇最初仅按标题排除；补齐摘要后，DeepSeek 对这 39 篇仍全部排除。此次没有出现明确排除论文被误收，或明确入选论文被漏收的分类分歧。

## 人工反馈与 v1.9 范围修正

用户认为 LMTracer 和 Amazon Bedrock WLM 均应排除。排除依据是主要贡献所处的层次：

- **LMTracer**：主要贡献是 profiling／观测工具；工具低开销及发现问题后人工修复产生的收益，不属于当前优先筛选的直接模型执行优化。
- **Bedrock WLM**：主要贡献为平台准入、跨区域路由、配额协调与编排；根据已有摘要及用户提供的第一页，对模型或推理执行引擎的直接优化不明确。

同时放宽摘要证据要求：描述相关性能评测即可，不要求摘要报告具体提升数字或显式比较收益。Bedrock 的排除原因不是缺少收益数字。

v1.9 优先模型计算、算子、解码、KV/HBM 管理、设备执行、训练通信、权重传输及与执行机制耦合的调度。服务与执行引擎联合设计仍可入选；不能按 scheduling、routing 或 serving 关键词统一排除。

## 第二轮：v1.9 边界与对照重测

重测 13 篇，全部成功。LMTracer 和 Bedrock 各额外重复两次，**合计 17 次评分，0 次失败**；同样使用 `deepseek-reasoner`，不向模型提供旧分类或分数。

| 关键边界论文 | v1.8 结果 | v1.9 三次分数 | v1.9 结果 |
|---|---|---|---|
| LMTracer | 入选，7 分 | 3、4、2 | 三次均排除 |
| Amazon Bedrock WLM | 入选，7 分 | 3、3、3 | 三次均排除 |

其余重测项目：

| 项目组 | 论文 | v1.9 结果 |
|---|---|---|
| 正向对照，6 篇 | Janus、SANDHI、StreamEP、MeldKernel、MeshRT、Wavel | 全部入选 |
| 排除对照，2 篇 | Ave；Scalable Context Orchestration for Serving LLMs Over Voice | 全部排除 |
| 原待定，3 篇 | CrystalLLM、Morphable Kernels、LLM-42 | 全部排除；尚无最终人工标签 |

LLM-42 本轮被排除的理由是摘要没有描述性能评测；模型已明确区分“未描述评测”与“未给提升数字”，不是因缺少数值本身排除。

## 当前保留的 10 篇明确相关论文

这 10 篇在 v1.8 全名单评测中均被 DeepSeek 入选；其中上述六篇还通过了 v1.9 对照重测。

| 论文简称 | 方向 |
|---|---|
| Anchor | GPU 故障恢复与内存复用 |
| ACDC（Batched in Back） | 离线 LLM 推理服务 |
| Beyond Utilization | 推理服务 GPU 能耗与资源共置 |
| Janus | 服务／执行引擎联合设计与多模型共置 |
| SANDHI | 模型组件合并与显存优化 |
| StreamEP | MoE 解码中的异步通信 |
| MeldKernel（Taming Dynamism on GPUs） | 跨 SM 融合与动态 GPU 执行 |
| MeshRT | Wafer-scale 推理运行时 |
| TensorHub | LLM RL 训练中的权重传输 |
| Wavel | Wafer-scale 模型执行编译 |

## 覆盖范围与版本追溯

- v1.9 没有重跑全部 62 篇或此前 213 篇；不声称新版已在全量样本上验证完全一致。
- 重复测试只覆盖 LMTracer 和 Bedrock。LMTracer 分数有变化，入选／排除结果保持一致。
- CrystalLLM、Morphable Kernels、LLM-42 仍需人工确认，不能将其模型判定算作与人工一致。
- 此次范围发生变化，不能把 v1.8 与 v1.9 的入选数差异直接解释成模型能力变化。
- 默认模板：[mlsys_screening_prompt.json](../../configs/templates/reports/mlsys_screening_prompt.json)。v1.8 模板可追溯至 `b70b079`，v1.9 更新提交为 `e2040bf`。

冻结模板 SHA256：

| Prompt | SHA256 |
|---|---|
| v1.8 | `d7959f40fd9685bbdf9b60d74e0610fa203e1d22d6b2fd66c376f976a2bcb61c` |
| v1.9 | `c3b20767000692342053118dff0af7d50fab2a16050aeb238db72e9447ed85c0` |

本文件保存评测摘要、边界决定和覆盖限制。完整摘要、原始模型响应、SQLite、网页快照及 PDF 作为本地实验数据保留，不纳入 Git。
