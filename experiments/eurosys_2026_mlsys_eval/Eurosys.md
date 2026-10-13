# EuroSys 2026 — MLSys 领域论文摘要汇总

> 共筛选出 **46 篇** MLSys 相关论文，涵盖 LLM 推理服务、大模型训练、模型微调、GPU 优化、边缘推理、生成式 AI、ML for Systems 等方向。
> 数据来源：[https://2026.eurosys.org/papers.html](https://2026.eurosys.org/papers.html)

---

## 一、LLM 推理/服务系统（14篇）

### 1. AdaServe: Accelerating Multi-SLO LLM Serving with SLO-Customized Speculative Decoding

- **作者：** Zikun Li 等 (CMU, Princeton, EPFL)
- **链接：** [ACM](https://dl.acm.org/doi/10.1145/3767295.3769315) | [arXiv](https://arxiv.org/abs/2501.12162)
- **一句话摘要：** 通过 SLO 定制的推测解码，为不同延迟需求的 LLM 请求构建差异化投机树，在满足多样化服务质量目标的同时最大化系统吞吐，将 SLO 违规降低 4.3 倍。

### 2. FlexPipe: Adapting Dynamic LLM Serving Through Inflight Pipeline Refactoring in Fragmented Serverless Clusters

- **作者：** Yanying Lin 等 (UCAS, UCSD, 澳门大学)
- **链接：** [ACM](https://dl.acm.org/doi/10.1145/3767295.3769316) | [arXiv](https://arxiv.org/abs/2510.11938)
- **一句话摘要：** 在无服务器集群中运行时动态重构 LLM 推理流水线粒度，实现 8.5 倍资源效率提升和 38.3% 延迟降低。

### 3. Taming Latency-Memory Trade-Off in MoE-Based LLM Serving via Fine-Grained Expert Offloading (FineMoE)

- **作者：** Hanfei Yu 等 (Stevens, Rice, Waterloo, Rutgers)
- **链接：** [ACM](https://dl.acm.org/doi/10.1145/3767295.3769319) | [arXiv](https://arxiv.org/abs/2502.05370)
- **一句话摘要：** 利用 MoE 模型的细粒度专家选择模式和输入提示语义 hint，智能预取、缓存和卸载专家，在减少 47% 推理延迟的同时提升 39% 专家命中率。

### 4. TokenFlow: Responsive LLM Text Streaming Serving under Request Burst via Preemptive Scheduling

- **作者：** Junyi Chen 等 (上海交通大学)
- **链接：** [ACM](https://dl.acm.org/doi/10.1145/3767295.3769328) | [arXiv](https://arxiv.org/abs/2510.02758)
- **一句话摘要：** 通过基于 token 缓冲区占用率的抢占式调度和主动 KV Cache 管理，将有效吞吐提升 82.5% 并将 P99 TTFT 降低 80.2%。

### 5. AdaGen: Workload-Adaptive Cluster Scheduler for Latency-Optimal LLM Inference Serving

- **作者：** Sudipta Saha Shubha 等 (UVA, HPE Labs, UC Riverside)
- **链接：** [ACM](https://dl.acm.org/doi/10.1145/3767295.3769345)
- **一句话摘要：** 面向 LLM 推理的自适应集群调度器，通过在线学习和混合分区策略，在对延迟敏感的短查询和吞吐优先的长批处理请求之间实现联合优化，提升 30%+ 吞吐并降低 4 倍短请求 TTFT。

### 6. TailorLLM: Collaborative End-Cloud Inference of Large and Small Language Models Based on Low-Rank Adaptation

- **作者：** Zian Wang 等 (北京邮电大学)
- **链接：** [ACM](https://dl.acm.org/doi/10.1145/3767295.3769346)
- **一句话摘要：** 提出端云协同推理框架，通过低秩适配让端侧小模型与云端大模型协作，以接近小模型的成本达到大模型级别的推理质量。

### 7. KUNSERVE: Parameter-centric Memory Management for Efficient Memory Overloading Handling in LLM Serving

- **作者：** Rongxin Cheng 等 (上海交通大学)
- **链接：** [ACM](https://dl.acm.org/doi/10.1145/3767295.3769348) | [arXiv](https://arxiv.org/abs/2412.18169)
- **一句话摘要：** 首个采用以参数为中心的内存管理方法应对 LLM 服务过载的系统，通过选择性丢弃冗余副本参数瞬间释放 GPU 内存，将尾部 TTFT 降低最多 72.2 倍。

### 8. SkyWalker: A Locality-Aware Cross-Region Load Balancer for LLM Inference

- **作者：** Tian Xia 等 (UC Berkeley, ICSI, Rice)
- **链接：** [ACM](https://dl.acm.org/doi/10.1145/3767295.3769353)
- **一句话摘要：** 面向跨地域 LLM 推理的负载均衡器，结合前缀感知路由和选择性推送机制，在保持前缀共享收益的同时实现多区域负载均衡。

### 9. MFS: An Efficient Model Family Serving System for LLMs

- **作者：** Yunxuan Zhang 等 (HKUST, USTC, Inspur)
- **链接：** [ACM](https://dl.acm.org/doi/10.1145/3767295.3769355)
- **一句话摘要：** 利用模型家族的结构相似性，通过知识沉淀微调技术让最大模型内化小模型能力，构建统一的多层服务流水线，降低 56.1% 延迟和 47.8% GPU 内存。

### 10. SAS: Sparse Attention Synthesizer for Efficient Language Model Inference

- **作者：** Yuan Zhou 等 (Amazon)
- **链接：** [ACM](https://dl.acm.org/doi/10.1145/3767295.3769364)
- **一句话摘要：** 自动为 LLM 推理生成高性能稀疏注意力核，通过几何模式分析器优化 KV 缓存管理，在 GPU 上实现 2.68-2.80 倍 Token 生成加速，在 AWS Trainium 上最高 10.87 倍加速。

### 11. PiLLM: Resource-Efficient LLM Inference Using Workload Prediction

- **作者：** Yunqian Fan 等 (上海科技大学, SenseTime, 北航)
- **链接：** [ACM](https://dl.acm.org/doi/10.1145/3767295.3769393)
- **一句话摘要：** 通过轻量级预测器估算每条查询的最优推理长度或难度，在固定 token 预算下通过贪心批分配最大化推理精度。

### 12. High Throughput and Low Latency LLM Serving via Adaptive KV Caching (eLLM)

- **作者：** Wenyan Chen 等 (澳门大学, 中科院深圳先进院, NTU)
- **链接：** [ACM](https://dl.acm.org/doi/10.1145/3767295.3803570)
- **一句话摘要：** 通过自适应的细粒度 KV 缓存策略，选择性地缓存部分 token 并动态重算非缓存 token，实现 3.03 倍吞吐提升和 2.63 倍首 token 延迟降低。

### 13. PARD: Enhancing Goodput for Inference Pipeline via Proactive Request Dropping

- **作者：** Zhixin Zhao 等 (天津大学, UT Dallas)
- **链接：** [ACM](https://dl.acm.org/doi/10.1145/3767295.3803581) | [arXiv](https://arxiv.org/abs/2602.08747)
- **一句话摘要：** 提出主动式请求丢弃策略，利用运行时流水线信息及时、精准地选择应丢弃的请求，相比现有方案提升 16%-176% 的有效吞吐（goodput）。

### 14. Efficient Multimodal Serving via Module Multiplexing

- **作者：** Zicong Hong 等 (HKUST, 中山大学, MetaX)
- **链接：** [ACM](https://dl.acm.org/doi/10.1145/3767295.3769389)
- **一句话摘要：** 通过模块复用技术，在多模态模型服务中共享和复用不同模态的处理模块，提高资源利用效率。

---

## 二、LLM/大模型训练系统（10篇）

### 15. Handling Network Faults in Distributed AI Training: Failover is Now an Option (ReCCL)

- **作者：** Xin Zhe Khooi 等 (NUS, ByteDance)
- **链接：** [ACM](https://dl.acm.org/doi/10.1145/3767295.3769322)
- **一句话摘要：** 首个支持网络容错的集合通信库 ReCCL，在网络故障时无缝切换到备用路径，保持训练状态同步，显著节省大规模分布式 AI 训练的 GPU 小时数。

### 16. MegaScale-MoE: Large-Scale Communication-Efficient Training of Mixture-of-Experts Models in Production

- **作者：** Chao Jin 等 (北大, ByteDance Seed)
- **链接：** [ACM](https://dl.acm.org/doi/10.1145/3767295.3769325) | [arXiv](https://arxiv.org/abs/2505.11432)
- **一句话摘要：** ByteDance 生产的 MoE 训练系统，定制通信高效的并行策略并实现算子间/算子内计算通信重叠，训练 352B MoE 模型在 1440 GPU 上达到 1.41M tokens/s，比 Megatron-LM 提升 1.88 倍。

### 17. STAlloc: Enhancing Memory Efficiency in Large-Scale Model Training with Spatio-Temporal Planning

- **作者：** Zixiao Huang 等 (清华大学, Infinigence-AI)
- **链接：** [ACM](https://dl.acm.org/doi/10.1145/3767295.3769335) | [arXiv](https://arxiv.org/abs/2507.16274)
- **一句话摘要：** 利用训练负载的时空规律提前规划 GPU 内存分配，平均减少 85.1% 内存碎片，最高节省 56.3GB GPU 内存并提升 32.5% 吞吐。

### 18. Zeppelin: Balancing Variable-length Workloads in Data Parallel Large Model Training

- **作者：** Chang Chen 等 (北大, ETH Zurich, CUHK)
- **链接：** [ACM](https://dl.acm.org/doi/10.1145/3767295.3769369) | [arXiv](https://arxiv.org/abs/2509.21841)
- **一句话摘要：** 针对大模型训练中变长序列的负载不均问题，提出层次化序列分区、跨节点路由和序列布局重映射三项技术，平均实现 2.80 倍加速。

### 19. Efficient and Adaptable Overlapping for Computation and Communication via Signaling and Reordering (FlashOverlap)

- **作者：** Ke Hong 等 (清华, 北大, Infinigence-AI)
- **链接：** [ACM](https://dl.acm.org/doi/10.1145/3767295.3769370) | [arXiv](https://arxiv.org/abs/2504.19519)
- **一句话摘要：** 通过 GEMM 计算核在部分输出完成时发送信号触发通信的信号机制，实现 tile 级计算通信重叠，且不干扰原始 GEMM 性能，最高 1.65 倍加速。

### 20. Arena: Efficiently Training Large Models via Dynamic Scheduling and Adaptive Parallelism Co-Design

- **作者：** Chunyu Xue 等 (上海交通大学, Lenovo, Microsoft, 贵州大学, NUS)
- **链接：** [ACM](https://dl.acm.org/doi/10.1145/3767295.3803571) | [arXiv](https://arxiv.org/abs/2403.16125)
- **一句话摘要：** 协同设计作业间动态调度和作业内自适应并行，通过网格抽象统一空间，在异构集群上减少 49.3% 作业完成时间，提升 1.60 倍集群吞吐。

### 21. MegaScale-Data: Scaling DataLoader for Multisource Large Foundation Model Training

- **作者：** Juntao Zhao 等 (HKU, ByteDance)
- **链接：** [ACM](https://dl.acm.org/doi/10.1145/3767295.3803568) | [arXiv](https://arxiv.org/abs/2504.09844)
- **一句话摘要：** 面向多源大模型训练的工业级分布式数据加载架构，通过解耦数据预处理为角色专属 Actor，消除冗余数据访问，实现 4.5 倍训练吞吐提升和 13.5 倍 CPU 内存节省。

### 22. MegaScale-Omni: A Hyper-Scale, Workload-Resilient System for MultiModal LLM Training in Production

- **作者：** Chunyu Xue 等 (上海交通大学, ByteDance Seed)
- **链接：** [ACM](https://dl.acm.org/doi/10.1145/3767295.3803587)
- **一句话摘要：** ByteDance 面向多模态 LLM 训练的超大规模生产系统，支持动态模态混合和工作负载弹性，在多模态大模型训练中实现高性能和可恢复性。

### 23. HetAuto: Cross-Cluster Auto-Parallelism for Heterogeneous Distributed Training

- **作者：** Guicheng Qi 等 (HKU, Meituan)
- **链接：** [ACM](https://dl.acm.org/doi/10.1145/3767295.3803590)
- **一句话摘要：** 面向跨集群异构分布式训练的自动并行化系统，基于 MCTS 搜索和随机森林成本模型，在 4 个集群 736 设备上实现 1.57 倍训练吞吐提升。

### 24. Laminar: A Scalable Asynchronous RL Post-Training Framework

- **作者：** Guangming Sheng 等 (HKU, ByteDance)
- **链接：** [ACM](https://dl.acm.org/doi/10.1145/3767295.3803580) | [arXiv](https://arxiv.org/abs/2510.12633)
- **一句话摘要：** 通过全解耦架构实现轨迹级异步的 RL 后训练系统，消除全局权重同步瓶颈，在 1024 GPU 集群上实现 5.48 倍训练吞吐加速。

---

## 三、模型微调与适配（2篇）

### 25. Federated Fine-Tuning of Sparsely-Activated Large Language Models on Resource-Constrained Devices (FLUX)

- **作者：** Fahao Chen 等 (山东大学, 西安交通大学)
- **链接：** [ACM](https://dl.acm.org/doi/10.1145/3767295.3769329) | [arXiv](https://arxiv.org/abs/2508.19078)
- **一句话摘要：** 面向资源受限设备的 MoE-LLM 联邦微调系统，通过量化剖析估计专家激活、自适应层感知专家合并以及探索-利用策略分配专家角色，实现 4.75 倍收敛加速。

### 26. LoRAFusion: Efficient LoRA Fine-Tuning for LLMs

- **作者：** Zhanda Zhu 等 (UofT, Vector Institute, NVIDIA)
- **链接：** [ACM](https://dl.acm.org/doi/10.1145/3767295.3769331) | [arXiv](https://arxiv.org/abs/2510.00206)
- **一句话摘要：** 通过图分裂方法融合内存受限的算子，并设计自适应批处理算法调度多 LoRA 任务，相比 Megatron-LM 实现 1.96 倍端到端加速。

---

## 四、GPU/硬件加速与内存优化（6篇）

### 27. Multipath Collective Communication Beyond Scale-up Networks in GPU Clouds (MPCCS)

- **作者：** Yuchen Xu 等 (北京大学, Tencent)
- **链接：** [ACM](https://dl.acm.org/doi/10.1145/3767295.3769330)
- **一句话摘要：** 将扩缩网络（Scale-up）与扩展网络（Scale-out）结合进行多路径集合通信传输，通过双窗口协议和带宽自适应拆分，在通信微基准上实现 23%-54% 加速。

### 28. Untangling GPU Power Consumption: Job-Level Inference in Cloud Shared Settings

- **作者：** Pierre Jacquet 等 (ÉTS, Inria, OVHcloud, CNRS)
- **链接：** [ACM](https://dl.acm.org/doi/10.1145/3767295.3769333)
- **一句话摘要：** 提出在云共享 GPU 环境中估计作业级功耗的实用方法，证明 GPU 共享可改善小 AI 工作负载的能效，同时揭示 IaaS GPU 集群的严重利用不足。

### 29. Reducing the GPU Memory Bottleneck with Lossless Compression for ML (IBP)

- **作者：** Aditya Kamath 等 (UW, KAUST, Google)
- **链接：** [ACM](https://dl.acm.org/doi/10.1145/3767295.3803595)
- **一句话摘要：** 提出无损压缩算法 Invariant Bit Packing，识别并消除张量间的不变位，结合 GPU 优化的解压实现 74% 更快的 GNN 训练和 25% 更快的 LLM 推理。

### 30. Efficient Data Passing for Serverless Inference Workflows: A GPU-Centric Approach (GRouter)

- **作者：** Hao Wu 等 (HUST, CUHK-Shenzhen, TeleAI, HKUST)
- **链接：** [ACM](https://dl.acm.org/doi/10.1145/3767295.3769336)
- **一句话摘要：** 面向无服务器推理工作流的以 GPU 为中心的数据平面，聚合 NVLink、PCIe 和 NIC 带宽进行并行传输，降低 87% 数据传输延迟，提升 1.74 倍吞吐。

### 31. FlexiQ: Adaptive Mixed-Precision Quantization for Latency/Accuracy Trade-Offs in Deep Neural Networks

- **作者：** Jaemin Kim 等 (首尔大学, 汉阳大学, 延世大学)
- **链接：** [ACM](https://dl.acm.org/doi/10.1145/3767295.3769351) | [arXiv](https://arxiv.org/abs/2510.02822)
- **一句话摘要：** 自适应混合精度量化方案，根据特征通道的值范围选择低比特计算并实时调整比率，在定制 NPU 和 GPU 上实现精度与延迟的高效权衡。

### 32. Bridging the GPU Utilization Gap: Predictive Multi-Dimensional Resource Scheduling for AI Workloads

- **作者：** Yilei Lu 等 (清华, 东南大学, Alibaba)
- **链接：** [ACM](https://dl.acm.org/doi/10.1145/3767295.3803579)
- **一句话摘要：** 通过预测性多维资源调度，在 GPU 集群中更好地调度 AI 工作负载以弥合 GPU 利用率差距。

---

## 五、ML 训练数据与预处理（1篇）

### 33. MinatoLoader: Accelerating Machine Learning Training Through Efficient Data Preprocessing

- **作者：** Rahma Nouaji 等 (McGill, INESC TEC)
- **链接：** [ACM](https://dl.acm.org/doi/10.1145/3767295.3769376) | [arXiv](https://arxiv.org/abs/2509.10712)
- **一句话摘要：** 通用 PyTorch 数据加载器，通过样本感知调度优先处理快速样本、并行处理慢速样本来解决队头阻塞问题，将 GPU 利用率从 46% 提升至 90%，训练加速最高 7.5 倍。

---

## 六、深度学习编译与优化（3篇）

### 34. Maya: Optimizing Deep Learning Training Workloads using GPU Runtime Emulation

- **作者：** Srihas Yarlagadda 等 (Georgia Tech, NVIDIA)
- **链接：** [ACM](https://dl.acm.org/doi/10.1145/3767295.3769366) | [arXiv](https://arxiv.org/abs/2503.20191)
- **一句话摘要：** 通过透明的 GPU 运行时模拟拦截设备 API 调用，无需修改训练代码即可精确预测 DL 训练性能，预测误差 <5%，识别出的配置降低 56% 训练成本。

### 35. LLMFolder: Revisiting Constant Folding in Large Language Models

- **作者：** Gansen Hu 等 (上海交通大学)
- **链接：** [ACM](https://dl.acm.org/doi/10.1145/3767295.3769339)
- **一句话摘要：** 重新审视常量折叠在 LLM 中的应用，将其编译优化思想引入大语言模型以提升推理效率。

### 36. Automated End-to-End Model Serving with Cooperative Compilation and Scheduling

- **作者：** Yikang Zhang 等 (南京大学, 湖南大学)
- **链接：** [ACM](https://dl.acm.org/doi/10.1145/3767295.3769392)
- **一句话摘要：** 将编译优化与调度协同设计，自动实现端到端的模型服务，覆盖从模型编译到推理调度的全流程。

---

## 七、边缘/端侧 ML（3篇）

### 37. TZ-LLM: Protecting On-Device Large Language Models with Arm TrustZone

- **作者：** Xunjie Wang 等 (上海交通大学)
- **链接：** [ACM](https://dl.acm.org/doi/10.1145/3767295.3769334) | [arXiv](https://arxiv.org/abs/2511.13717)
- **一句话摘要：** 利用 Arm TrustZone 保护端侧 LLM 模型机密性，通过流水线恢复和协同驱动设计减少 TTFT 最高 90.9% 并提升 23.2% 解码速度。

### 38. Scaling LLM Test-Time Compute with Mobile NPU on Smartphones

- **作者：** Zixu Hao 等 (清华, USTC, Microsoft Research)
- **链接：** [ACM](https://dl.acm.org/doi/10.1145/3767295.3769382) | [arXiv](https://arxiv.org/abs/2509.23324)
- **一句话摘要：** 利用手机 NPU 未被充分利用的计算资源进行测试时计算扩展，通过硬件感知 tile 量化和 LUT 变换，让小模型在手机 NPU 上通过扩展测试时计算达到更大模型的精度。

### 39. Neuro-C: Neural Inference Shaped by Hardware Limits

- **作者：** Diletta Romano 等 (Uppsala, RISE, Polimi)
- **链接：** [ACM](https://dl.acm.org/doi/10.1145/3767295.3769380)
- **一句话摘要：** 专为超低功耗微控制器设计的神经网络架构，消除乘加运算并通过固定三元邻接矩阵编码连接性，推理延迟和程序内存降低高达 90%。

---

## 八、生成式 AI 系统（2篇）

### 40. FlashPS: Efficient Generative Image Editing with Mask-aware Caching and Scheduling

- **作者：** Xiaoxiao Jiang 等 (HKUST, Alibaba)
- **链接：** [ACM](https://dl.acm.org/doi/10.1145/3767295.3769379)
- **一句话摘要：** 通过掩码感知的缓存和调度策略，高效支持生成式图像编辑服务，在不影响图像质量的前提下显著提升服务性能。

### 41. Carbon-Aware Continuous Learning for Sustainable Real-Time Machine Learning Analytics

- **作者：** Gwanjong Park 等 (SKKU, POSTECH)
- **链接：** [ACM](https://dl.acm.org/doi/10.1145/3767295.3769361)
- **一句话摘要：** 面向可持续实时 ML 分析系统的碳感知持续学习框架，在模型持续更新过程中考虑碳排放因素进行调度优化。

---

## 九、LLM 安全与可信（1篇）

### 42. TrustWeave: Integrity Measurement and Attestation For Multi-Cloud LLMs

- **作者：** Jianchang Su 等 (UConn, 清华大学)
- **链接：** [ACM](https://dl.acm.org/doi/10.1145/3767295.3803586)
- **一句话摘要：** 为多云环境中的 LLM 服务提供运行时完整性度量和远程证明框架，通过持续运行时证明和容器级测量建立从硬件到应用的完整信任链。

---

## 十、ML for Systems（用机器学习优化系统，4篇）

### 43. Learn-to-Probe: Achieving Signal Distinguishability in Learning-based Congestion Control

- **作者：** Han Tian 等 (USTC, HKUST, Huawei)
- **链接：** [ACM](https://dl.acm.org/doi/10.1145/3767295.3769317)
- **一句话摘要：** 通过学习驱动的拥塞控制方法，优化探测报文的信号可区分性以提升网络拥塞控制决策质量。

### 44. Concord: Learning Network Configuration Contracts

- **作者：** Ryan Beckett 等 (Microsoft Research, UIUC)
- **链接：** [ACM](https://dl.acm.org/doi/10.1145/3767295.3769338)
- **一句话摘要：** 自动从现有网络配置中学习轻量级配置约束合约，检测配置错误前将其影响网络，在数百万行配置上精度超 90%。

### 45. Canopy: Property-Driven Learning for Congestion Control

- **作者：** Chenxi Yang 等 (UT Austin, Google DeepMind)
- **链接：** [ACM](https://dl.acm.org/doi/10.1145/3767295.3769362) | [arXiv](https://arxiv.org/abs/2412.10915)
- **一句话摘要：** 将形式化验证与强化学习结合在训练循环中，通过定量认证和抽象解释指导学习过程，使学习的拥塞控制算法同时具备适应性和最坏情况可靠性。

### 46. On-device Semantic Selection Made Low Latency and Memory Efficient with Monolithic Forwarding (PRISM)

- **作者：** Jiahao Zhou 等 (上海交通大学, Huawei)
- **链接：** [ACM](https://dl.acm.org/doi/10.1145/3767295.3803572) | [arXiv](https://arxiv.org/abs/2510.15620)
- **一句话摘要：** 提出整体转发（Monolithic Forwarding）范式，通过渐进式聚类剪枝和分层流式加载，在端侧跨编码器重排序任务中降低 89.2% 延迟和 91.3% 峰值内存。

---

> 📅 **EuroSys 2026** | 📍 Edinburgh, UK | 🗓 April 27–30, 2026
> 本文档由系统自动爬取整理，共收录 **46 篇** MLSys 方向论文。
