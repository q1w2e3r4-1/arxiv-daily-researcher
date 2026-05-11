# EuroSys 2026 MLSys 评测汇报（138篇正式版）

## 1. 说明

- 本报告基于 `data/experiments/eurosys_2026_mlsys_eval/smoke/` 下 138 篇论文的真实落盘结果重新汇总。
- 本报告**没有**使用此前遗留的 5 篇 smoke `summary.md/html` 作为统计来源；所有指标均从 `labels.csv`、`metrics.csv`、`model_outputs/*/judgments.jsonl`、`invalid_responses.jsonl` 重新计算。
- 本报告反映的是“上次实际跑完的那轮 138 篇评测”的结果。后续对 prompt 的修订不在本报告统计范围内。

## 2. 数据集与标注来源

- 论文来源：EuroSys 2026 accepted papers，抓取总数 138 篇
- 缺失摘要：0 篇
- Ground truth 正类：42 篇
- Ground truth 负类：96 篇
- `Eurosys.md` 原始正类条目：46 篇
- 从 `ML for Systems` 分类中排除的条目：4 篇

Ground truth 说明：本次标注并不是人工逐篇精标，而是从 `Eurosys.md` 冻结出来的标签，因此本身存在噪声。尤其是 AI agent systems、NPU / edge / on-device、以及部分 AI training / deployment systems，可能被偏保守地标成负类。后文列出的“高置信 ground-truth 复查候选”可以视为可接受的标签误差来源。

作者注：ground-truth是deepseek-flash标的，本身正确率可能还没有这几个模型高，所以不用过分关注那几个被误判的论文，有些光看标题就是就是标准的MLsys。这样看的话下面4个模型的准确率都会同步提高一些（因为这几个标准错误用例它们都投的一致答案）

## 3. 单模型结果

| 模型 | TP | TN | FP | FN | Accuracy | Precision | Recall | F1 | Pass Rate | Valid JSON | Avg Latency(s) | Total Latency(min) | Invalid | Fallback | Total Tokens |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| glm-5.1 | 42 | 84 | 12 | 0 | 0.9130 | 0.7778 | 1.0000 | 0.8750 | 0.3913 | 1.0000 | 30.71 | 70.63 | 0 | 0 | 176970 |
| minimax-m2.7 | 38 | 86 | 10 | 4 | 0.8986 | 0.7917 | 0.9048 | 0.8444 | 0.3478 | 1.0000 | 37.94 | 87.27 | 8 | 8 | 161536 |
| qwen3.5-27b | 41 | 78 | 18 | 1 | 0.8623 | 0.6949 | 0.9762 | 0.8119 | 0.4275 | 1.0000 | 7.01 | 16.12 | 0 | 0 | 121403 |
| deepseek-v3.2 | 41 | 81 | 15 | 1 | 0.8841 | 0.7321 | 0.9762 | 0.8367 | 0.4058 | 1.0000 | 11.02 | 25.34 | 0 | 0 | 117043 |

观察：

- `glm-5.1` 是本轮最强单模型，Accuracy=0.9130，F1=0.8750，且 FN=0。
- `minimax-m2.7` 的 FP 最少（10），但 FN 较多（4），整体更保守。
- `qwen3.5-27b` 与 `deepseek-v3.2` Recall 很高，但 FP 偏多。
- 4 个模型最终 `valid_json_rate` 都是 1.0；其中 `minimax-m2.7` 存在 8 次 invalid/fallback，但因为做了 fallback 落盘，所以最终 judgment 仍完整。

## 4. 委员会结果（基于上次评测结果后处理汇总）

| 方法 | TP | TN | FP | FN | Accuracy | Precision | Recall | F1 | Pass Rate |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 等权 4 模型委员会 | 41 | 84 | 12 | 1 | 0.9058 | 0.7736 | 0.9762 | 0.8632 | 0.3841 |
| 按 Accuracy 加权委员会 | 41 | 84 | 12 | 1 | 0.9058 | 0.7736 | 0.9762 | 0.8632 | 0.3841 |

委员会规则：

- 等权委员会：4 个模型分数取平均；若成功模型中正票多于反票则判正，少于则判负，平票时看平均分是否 >= 6。
- 加权委员会：用单模型 Accuracy 归一化后作为权重，对分数与投票做加权。
- 本轮数据上，等权与加权两种委员会的最终预测结果完全一致。

结论：委员会比 `qwen3.5-27b`、`deepseek-v3.2`、`minimax-m2.7` 更稳，但**没有超过最强单模型 `glm-5.1`**。不过，委员会的真正价值在于：它更容易暴露出“模型高度一致但与标答冲突”的样本，便于发现 ground truth 问题。

## 5. 模型一致性

| 正票数 | 论文数 | 含义 |
|---:|---:|---|
| 0 | 77 | 4 个模型一致判负 |
| 1 | 5 | 1 正 3 负 |
| 2 | 3 | 2 正 2 负 |
| 3 | 6 | 3 正 1 负 |
| 4 | 47 | 4 个模型一致判正 |

这份一致性分布可以用来区分：

- `0/4` 或 `4/4`：高置信样本；
- `3/1` 或 `1/3`：边界样本；
- `2/2`：最值得人工复核的冲突样本。

## 6. 高置信 ground-truth 复查候选

下面这些样本当前 gold=负类，但 4 个模型全部或几乎全部给出正类，且分数明显高于 6 分，属于“模型高度一致、很可能是标答偏保守”的案例。由于本次 ground truth 本身来自较弱模型与 `Eurosys.md` 规则冻结，这类误标是可接受的，也应该在汇报时明确说明。

| paper_id | 标题 | 投票 | 集成分数 | 当前 gold |
|---|---|---:|---:|---|
| eurosys2026_131 | viNPU: Optimizing Vision Transformer Inference on Mobile NPUs | 4/0 | 10.75 | 负类 |
| eurosys2026_084 | On-device Semantic Selection Made Low Latency and Memory Efficient with Monolithic Forwarding | 4/0 | 10.00 | 负类 |
| eurosys2026_125 | Efficient ML Model Updates for Deeply Embedded Microcontrollers | 4/0 | 10.00 | 负类 |
| eurosys2026_134 | AIMS: Cost-Efficient LLM-Based Agent Deployment in Hybrid Cloud-Edge Environments | 4/0 | 9.50 | 负类 |
| eurosys2026_115 | HARP: Orchestrating Automated Parallel Training on Heterogeneous GPU Clusters | 4/0 | 8.25 | 负类 |
| eurosys2026_135 | Suika: Efficient and High-quality Re-scheduling of 3D-parallelized LLM Training Jobs in Shared Clusters | 4/0 | 8.25 | 负类 |
| eurosys2026_123 | PointShuffler: Accelerating Point Cloud Neural Networks on General-Purpose GPUs | 4/0 | 7.50 | 负类 |
| eurosys2026_100 | Enabling Packet Spraying over Commodity RNICs with In-Network Support | 4/0 | 7.25 | 负类 |
| eurosys2026_124 | TAO: Tolerance-Aware Optimistic Verification for Floating-Point Neural Networks | 4/0 | 7.25 | 负类 |
| eurosys2026_117 | SwiftFL: Enabling Speculative Training for On-Device Federated Deep Learning | 3/1 | 8.25 | 负类 |

这批论文中，较典型的可复查方向包括：

- NPU / mobile / on-device inference
- edge / hybrid cloud-edge AI deployment
- LLM training orchestration / rescheduling / cluster execution
- AI agent deployment or LLM-friendly systems interfaces

## 7. 产物清单（本次新增，已保存到实验目录）

- `experiments/eurosys_2026_mlsys_eval/eurosys_2026_eval_138_model_metrics.csv`：单模型指标总表
- `experiments/eurosys_2026_mlsys_eval/eurosys_2026_eval_138_committee_metrics.csv`：委员会指标总表
- `experiments/eurosys_2026_mlsys_eval/eurosys_2026_eval_138_per_paper_predictions.csv`：138 篇逐篇预测分数表
- `experiments/eurosys_2026_mlsys_eval/eurosys_2026_eval_138_ground_truth_review_candidates.csv`：ground-truth 复查候选表
- `experiments/eurosys_2026_mlsys_eval/eurosys_2026_eval_138_agreement_breakdown.csv`：模型一致性分布表
- `experiments/eurosys_2026_mlsys_eval/eurosys_2026_eval_138_report.md`：本 Markdown 汇报文件

## 8. 总结

- 如果只选一个模型作为当前生产候选，`glm-5.1` 是本轮最优。
- 如果更看重“筛出可能漏标/误标的论文”，4 模型委员会很有价值。
- 当前评测结果已经足够支持：将 4 模型委员会接入主流程进行 daily screening，同时在汇报中注明 ground truth 不是人工金标准，存在少量系统性误标。
- 事后我们根据这轮评测结果对 prompt 进行了修订，虽然没有额外跑评测，但应该结果会更加精准一点。

