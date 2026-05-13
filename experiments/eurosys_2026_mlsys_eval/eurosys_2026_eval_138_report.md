# EuroSys 2026 MLSys 评测汇报（138篇正式版）

## 1. 说明

- 本报告基于 `/home/lhy/workspace/arxiv-daily-researcher/data/experiments/eurosys_2026_mlsys_eval/smoke` 下 138 篇论文的真实落盘结果重新汇总。
- 本报告**没有**使用此前遗留的 5 篇 smoke `summary.md/html` 作为统计来源；所有指标均从 `labels.csv`、`metrics.csv`、`model_outputs/*/judgments.jsonl`、`invalid_responses.jsonl` 重新计算。
- 本报告中的委员会结果已经切换到当前生产逻辑：**先对 3 个 cheap 模型均分；若初筛均分落入 [5, 7]，再额外加入 1 次 glm-5.1 复核并重新取平均；fallback 失败按 5 分计入平均；最终平均分 >= 6 即通过**。
- 本报告反映的是这轮 138 篇评测在新委员会规则下的后处理结果；单模型原始 judgments 未被改写。

## 2. 数据集与标注来源

- 论文来源：EuroSys 2026 accepted papers，抓取总数 138 篇
- 缺失摘要：0 篇
- Ground truth 正类：42 篇
- Ground truth 负类：96 篇
- `Eurosys.md` 原始正类条目：46 篇
- 从 `ML for Systems` 分类中排除的条目：4 篇

Ground truth 说明：本次标注并不是人工逐篇精标，而是从 `Eurosys.md` 冻结出来的标签，因此本身存在噪声。尤其是 AI agent systems、NPU / edge / on-device、以及部分 AI training / deployment systems，可能被偏保守地标成负类。后文列出的复查候选可以视为可接受的标签误差来源。

## 3. 单模型结果

| 模型 | TP | TN | FP | FN | Accuracy | Precision | Recall | F1 | Pass Rate | Valid JSON | Avg Latency(s) | Total Latency(min) | Invalid | Fallback | Total Tokens |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| glm-5.1 | 42 | 84 | 12 | 0 | 0.9130 | 0.7778 | 1.0000 | 0.8750 | 0.3913 | 1.0000 | 30.71 | 70.63 | 0 | 0 | 176970 |
| minimax-m2.7 | 38 | 86 | 10 | 4 | 0.8986 | 0.7917 | 0.9048 | 0.8444 | 0.3478 | 1.0000 | 37.94 | 87.27 | 8 | 8 | 161536 |
| qwen3.5-27b | 41 | 78 | 18 | 1 | 0.8623 | 0.6949 | 0.9762 | 0.8119 | 0.4275 | 1.0000 | 7.01 | 16.12 | 0 | 0 | 121403 |
| deepseek-v3.2 | 41 | 81 | 15 | 1 | 0.8841 | 0.7321 | 0.9762 | 0.8367 | 0.4058 | 1.0000 | 11.02 | 25.34 | 0 | 0 | 117043 |

观察：

- `glm-5.1` 是本轮最强单模型，Accuracy=0.9130，F1=0.8750。
- `minimax-m2.7` 虽然更保守，但出现过 8 次 429 / invalid，最终都以 fallback=5 落盘。
- `qwen3.5-27b` 与 `deepseek-v3.2` Recall 很高，但 FP 偏多。

## 4. 委员会结果（基于上次评测结果后处理汇总）

| 方法 | TP | TN | FP | FN | Accuracy | Precision | Recall | F1 | Pass Rate |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 分阶段委员会（3 cheap + 边界 glm 复核） | 41 | 84 | 12 | 1 | 0.9058 | 0.7736 | 0.9762 | 0.8632 | 0.3841 |

委员会规则：

- 先由 `minimax-m2.7`、`qwen3.5-27b`、`deepseek-v3.2` 产生第一阶段最终分数，并计算初筛均分。
- 若初筛均分落入 `[5, 7]`，则额外加入一次 `glm-5.1` 复核，并对参与本次判定的分数重新取平均。
- 若最终平均分 >= 6，则委员会判为正类；否则判为负类。
- 若某个模型连续重试后仍失败，则该模型记为 fallback=5，并继续计入最终平均分。
- 单模型的 `pass/fail` 只保留为诊断信息，不再参与最终通过判定。
- 本轮数据里实际触发 `glm-5.1` 复核的论文数：13。

结论：委员会比部分单模型更稳，但**仍没有超过最强单模型 `glm-5.1`**。不过，委员会的真正价值在于：它更容易暴露出“模型高度一致但与标答冲突”的样本，便于发现 ground truth 问题。

## 5. 模型一致性（诊断）

| 支持通过 / 参与模型数 | 论文数 | 含义 |
|---:|---:|---|
| 0/3 | 78 | 0 个模型支持通过，3 个模型支持不通过（共 3 个参与最终判定） |
| 1/3 | 2 | 1 个模型支持通过，2 个模型支持不通过（共 3 个参与最终判定） |
| 1/4 | 2 | 1 个模型支持通过，3 个模型支持不通过（共 4 个参与最终判定） |
| 2/3 | 2 | 2 个模型支持通过，1 个模型支持不通过（共 3 个参与最终判定） |
| 2/4 | 3 | 2 个模型支持通过，2 个模型支持不通过（共 4 个参与最终判定） |
| 3/3 | 43 | 3 个模型支持通过，0 个模型支持不通过（共 3 个参与最终判定） |
| 3/4 | 4 | 3 个模型支持通过，1 个模型支持不通过（共 4 个参与最终判定） |
| 4/4 | 4 | 4 个模型支持通过，0 个模型支持不通过（共 4 个参与最终判定） |

这里的分母表示最终参与平均分判定的模型数：大多数论文只有 3 个 cheap 模型参与；只有边界样本才会升级为 4 个模型共同判定。

这份一致性分布可以用来区分：

- `0/3`、`3/3`、`0/4` 或 `4/4`：高置信样本；
- `1/3`、`2/3`、`1/4` 或 `3/4`：边界样本；
- `2/4`：最值得人工复核的对半分歧样本。

## 6. 分数分布（基于委员会平均分）

- 正类平均分均值 / 中位数：8.030 / 8.000
- 负类平均分均值 / 中位数：2.879 / 2.000
- 正类中平均分 < 6 的论文数：1
- 负类中平均分 >= 6 的论文数：12
- 平均分 >= 6 且仅 1 个模型支持通过的案例数：0
- 平均分 >= 6 且仅 2 个模型支持通过的案例数：2

这说明在本轮 138 篇数据上，`平均分 >= 6` 的规则没有出现“只有极少数模型支持但平均分仍被抬过线”的异常模式。

## 7. ground-truth 复查候选

下面这些样本当前与平均分委员会结果冲突，且不少案例带有明显的 agent / NPU / edge / training systems 信号，值得优先复查。

| paper_id | 标题 | 支持模型数 | 平均分 | 当前 gold | 候选类型 |
|---|---|---:|---:|---|---|
| eurosys2026_131 | viNPU: Optimizing Vision Transformer Inference on Mobile NPUs | 3 | 10.33 | 负类 | committee_false_positive |
| eurosys2026_084 | On-device Semantic Selection Made Low Latency and Memory Efficient with Monolithic Forwarding | 3 | 9.67 | 负类 | committee_false_positive |
| eurosys2026_125 | Efficient ML Model Updates for Deeply Embedded Microcontrollers | 3 | 9.67 | 负类 | committee_false_positive |
| eurosys2026_134 | AIMS: Cost-Efficient LLM-Based Agent Deployment in Hybrid Cloud-Edge Environments | 3 | 9.33 | 负类 | committee_false_positive |
| eurosys2026_115 | HARP: Orchestrating Automated Parallel Training on Heterogeneous GPU Clusters | 3 | 8.00 | 负类 | committee_false_positive |
| eurosys2026_135 | Suika: Efficient and High-quality Re-scheduling of 3D-parallelized LLM Training Jobs in Shared Clusters | 3 | 8.00 | 负类 | committee_false_positive |
| eurosys2026_117 | SwiftFL: Enabling Speculative Training for On-Device Federated Deep Learning | 2 | 7.67 | 负类 | committee_false_positive |
| eurosys2026_124 | TAO: Tolerance-Aware Optimistic Verification for Floating-Point Neural Networks | 3 | 7.67 | 负类 | committee_false_positive |
| eurosys2026_118 | Crimson: Collaborative Parameter Updates for Efficient Pipeline Training of Large Language Models | 3 | 7.50 | 负类 | committee_false_positive |
| eurosys2026_123 | PointShuffler: Accelerating Point Cloud Neural Networks on General-Purpose GPUs | 3 | 7.33 | 负类 | committee_false_positive |
| eurosys2026_100 | Enabling Packet Spraying over Commodity RNICs with In-Network Support | 4 | 7.25 | 负类 | committee_false_positive |
| eurosys2026_088 | From Imperative to Declarative: Towards LLM-friendly OS Interfaces for Boosted Computer-Use Agents | 3 | 6.00 | 负类 | committee_false_positive |

## 8. 产物清单（已保存到实验目录）

- `experiments/eurosys_2026_mlsys_eval/eurosys_2026_eval_138_model_metrics.csv`：单模型指标总表
- `experiments/eurosys_2026_mlsys_eval/eurosys_2026_eval_138_committee_metrics.csv`：委员会指标总表
- `experiments/eurosys_2026_mlsys_eval/eurosys_2026_eval_138_per_paper_predictions.csv`：逐篇预测分数表
- `experiments/eurosys_2026_mlsys_eval/eurosys_2026_eval_138_ground_truth_review_candidates.csv`：ground-truth 复查候选表
- `experiments/eurosys_2026_mlsys_eval/eurosys_2026_eval_138_agreement_breakdown.csv`：模型一致性分布表
- `experiments/eurosys_2026_mlsys_eval/eurosys_2026_eval_138_score_distribution_stats.json`：分数分布统计
- `experiments/eurosys_2026_mlsys_eval/eurosys_2026_eval_138_score_distribution_notes.md`：分数分布备注
- `experiments/eurosys_2026_mlsys_eval/eurosys_2026_eval_138_summary.json`：结构化汇总
- `experiments/eurosys_2026_mlsys_eval/eurosys_2026_eval_138_report.md`：本 Markdown 汇报文件

## 9. 总结

- 如果只选一个模型作为当前生产候选，`glm-5.1` 依然是本轮最优。
- 如果更看重“筛出可能漏标 / 误标的论文”，当前这套分阶段委员会依然很有价值。
- 当前评测结果已经足够支持：将这套 cheap-first、borderline 再交给 `glm-5.1` 复核的委员会规则接入主流程进行 daily screening，同时在汇报中注明 ground truth 不是人工金标准，存在少量系统性误标。
