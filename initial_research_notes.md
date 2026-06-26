# AAAI Project: 初始调研笔记

日期：2026-06-18

## 1. 当前目录情况

- `begining_stage/` 目前是空目录，没有代码或数据文件。
- 目前唯一的项目材料是上一层的 [`paper_design_final.docx`](/home/yx21e.fsu/AAAI_project/paper_design_final.docx)。

## 2. 你这段设想里，最需要先捋顺的逻辑

### 2.1 推荐的结构

- `刺激` 进入多个专门模块。
- 每个模块都给出：
  - 一个候选理解/候选决策
  - 一个重要性分数
  - 可选的理由/解释
- 中枢（更准确地说是 `workspace/controller`）做一次竞争选择。
- 胜出的内容被广播回所有模块，作为下一步共同输入。
- `timestamp` 就是一次“竞争 -> 选择 -> 广播”的循环。

### 2.2 现在有点不顺的地方

- “中枢”和“agent”最好不要混成一层。
  - `agent` 是产生候选的专门模块。
  - `中枢` 是做选择与广播的共享工作空间/控制器。
- “output出来一个东西”最好明确成结构化消息，而不是自然语言散句。
  - 例如：`{proposal, score, rationale, action_hint}`。
- “不一定运动”这点很重要。
  - 中枢选中的内容可以是情感判断、感官判断、语言报告。
  - 只有映射到运动通道时，才真正变成动作。
- “评分系统”不是必须，但如果要做，建议把它和模块自评分分开。
  - 模块自评：表示显著性/重要性。
  - 中枢评分：表示最终仲裁。

### 2.3 一句话版

这个系统更像是：多个专门模块同时发言，中央工作空间只允许一个内容“点火”并广播，动作只是其中一种可能的下游输出。

## 3. ablation study 和 dissociation 是不是一回事

不是。

- `ablation` 是方法：切掉某个模块/通道/机制，看系统怎么变。
- `dissociation` 是现象：两个本来应该一起出现的功能分裂了。

更准确地说：

- ablation 可以帮助你制造或验证 dissociation。
- 但 “做了 ablation” 不等于 “发现了 dissociation”。
- 真正有信息量的是：
  - 一阶任务还在，但二阶报告没了；
  - 或一个模块坏了，另一个模块还保留功能；
  - 或报告和行为出现稳定脱钩。

所以论文里建议写成：

- `ablation` 是因果操纵；
- `dissociation` 是被观察到的功能解离；
- 你们要找的是“在可解释多智能体架构里，哪些经典解离标志会出现，以及它们依赖哪一个组件”。

## 4. 近期相关工作，最值得抓的几条

- VanRullen & Kanai, 2021: `Deep Learning and the Global Workspace Theory`
  - 早期把 GWT 翻译成深度学习路线图。
- Goyal et al., 2022: `Coordination among neural modules through a shared global workspace`
  - 共享 workspace / bottleneck / 模块协调。
- Dossa et al., 2024: `Design and evaluation of a global workspace agent embodied in a realistic multimodal environment`
  - 具身、多模态、现实环境里的 GWT agent。
- Phua, 2025: `Can We Test Consciousness Theories on AI? Ablations, Markers, and Robustness`
  - 最接近你们的方向：MiniGrid、消融、元认知标记、blindsight 类比、PCI 负结果。
- Ye et al., 2025: `CogniPair`
  - GNWT-based multi-agent digital twins，偏社会模拟/配对任务。
- Shang, 2026: `Theater of Mind for LLMs`
  - LLM 里的事件驱动 GWA / GWT 架构。
- 2026 preprint: `Evaluating Global Workspace Markers in Contemporary LLM Systems`
  - 更像“指标框架”，可以拿来做你们系统的 marker 对照表。

### 4.1 这些工作大体怎么做

- 先定义一个架构机制：workspace、broadcast、capacity bottleneck、self-model、metacognitive head 等。
- 再定义可测的功能标志：task accuracy、report accuracy、confidence calibration、Type-2 AUROC、access/no-report marker、noise robustness。
- 然后做消融：关掉 workspace、限制容量、关掉 self-model、切断报告通道、注入噪声。
- 重点不是“这个系统有没有意识”，而是“某个现象标志是否依赖某个架构机制”。

### 4.2 对我们最重要的启发

- 第一版不需要覆盖所有经典解离现象。
- 更稳的路线是先做两个：
  - `blindsight-like`: 行为还能避障/选对，但语言报告或置信度不匹配。
  - `self/other attribution`: 动作-反馈一致时能学会“这是我造成的”，延迟/错配/伪造反馈后归因崩掉。
- 这两个现象都能在 2D grid world 里程序化生成，不依赖难找的人类神经数据。

## 5. 能用上的数据与环境

### 5.1 先做 2D 可控环境

- [`MiniGrid`](https://minigrid.farama.org/)
  - 轻量、可定制、适合部分可观测和稀疏奖励。
  - 适合你们现在这个“小人、基地、矿区、障碍物”的原型。
- [`BabyAI`](https://github.com/mila-iqia/babyai)
  - 本来就是 grounded language / instruction following 平台。
  - 很适合把“中枢输出”做成语言或指令。
- [`Minari`](https://minari.farama.org/)
  - 官方 offline RL 数据接口。
  - 里面已经有 MiniGrid / BabyAI 相关数据集入口。

### 5.2 如果要做具身视听

- [`SoundSpaces`](https://soundspaces.org/)
  - 3D audio-visual navigation 的标准平台。
- [`SoundSpaces 2.0`](https://vision.cs.utexas.edu/projects/soundspaces2/)
  - 更强的视觉-声学仿真，能接 Habitat / Matterport3D / Replica。

### 5.3 如果要做跨模态语言/视觉

- [`GRID corpus`](https://zenodo.org/records/3625687)
  - 经典 audiovisual speech corpus。
- [`LRS3-TED`](https://arxiv.org/abs/1809.00496)
  - 大规模视听语音数据。
- [`LRW`](https://www.robots.ox.ac.uk/~vgg/data/lip_reading/lrw1.html)
  - word-level lip reading。
- [`AVSpeech`](https://looking-to-listen.github.io/avspeech/)
  - 很大，适合做鲁棒多模态。

### 5.4 如果要做人类对照或类比

- `CB database`（change blindness）
  - 变化盲视相关刺激/数据线索；是否能直接下载和复用还需要后续核对。
- `speed dating dataset`
  - CogniPair 用到的社会模拟基准之一。
- `intentional binding / sense of agency` 相关公开数据
  - 更适合做自我/行动归因的类比，而不是主训练集。

### 5.5 数据选择建议

- 主实验数据：自己在 MiniGrid/BabyAI 风格环境里程序化生成。
- 对照数据：用 Minari 轨迹或自己保存 expert/random policy 轨迹。
- 真实多模态数据：GRID/LRS3/LRW/AVSpeech 只放在后续扩展，尤其是 McGurk/cross-modal integration。
- 人类心理学数据：作为动机和 sanity check，不建议作为第一版训练数据。

## 6. 我建议的第一版实验切口

1. 先把 2D 任务跑通。
2. 先只做两个核心现象：
   - `blindsight` 类：能做但低二阶自知。
   - `self/other attribution` 类：动作-反馈一致性破坏后，自我边界塌掉。
3. 日志里记录：
   - 每个模块输出
   - 每次 importance score
   - 每次 winner
   - 每次 broadcast 内容
   - 每步动作与环境回馈
4. 再往外扩：
   - change/inattentional blindness
   - split-brain / confabulation
   - cross-modal integration

## 7. 现在到底该不该去找 data

应该，但要先把 `data` 讲清楚。

- 如果 2D 环境别人负责，那你现在要找的不是环境本身的数据，而是：
  - 轨迹格式
  - 事件日志
  - 干预标签
  - 评测标注
- 对这个项目最有用的数据，通常分三层：
  1. `主实验轨迹`：系统自己在任务里的运行日志。
  2. `对照轨迹`：expert / random / ablated policy 的轨迹。
  3. `外部参考数据`：真实多模态或人类心理学数据，只做扩展和类比。
- 现阶段最稳的做法是先把“需要记录什么”定下来，再去找对应来源。
  - 不然会出现：数据找了一堆，但和你要测的 dissociation marker 对不上。

### 7.1 你现在最应该优先找的

- 能直接支持 `blindsight-like` 的：
  - 行为结果
  - 置信度/二阶报告
  - 任务成功率
- 能直接支持 `self/other attribution` 的：
  - 动作-反馈配对日志
  - 延迟/错配/伪造反馈标签
  - 自我归因或代理归因标注
- 能直接支持 `confabulation` 的：
  - 行为失败事件
  - 事后解释文本
  - 解释是否与真实原因一致的标注

## 7. 一个比较稳的表述方式

- 不要说“我们做出了有意识的系统”。
- 更稳的说法是：
  - “我们做了一个可解释的 multi-agent global workspace 实验台”
  - “我们测试经典解离现象是否在该架构中出现”
  - “我们分析这些标志依赖哪些模块和广播机制”
