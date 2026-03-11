## 架构交叉评审：Accuracy First

### 结论

整体上，当前架构已经从“路由很散、主要靠 LLM 硬猜”的状态，进入了“状态模型开始成型，但还没有完全打通”的阶段。

如果把“准确率”定义为：

- 正确病历落到正确患者
- 内容结构化正确
- 医生不需要事后追错

那么当前的核心问题已经不是“模型够不够强”，而是患者上下文是否能在多轮里被稳定、结构化、权威地延续。

### 当前做得对的部分

#### 1. 已具备 accuracy-first 所需的核心状态

系统已经存在这些关键状态：

- `current_patient_*`
- `candidate_patient_*`
- `patient_not_found_name`
- `pending_record_id`

这说明架构方向是对的：系统不再只是每轮重新猜 `patient_name`，而是开始把患者连续性建模成显式状态。

#### 2. add_record 默认走 pending draft

普通 `add_record` 先生成草稿、再确认保存，这是当前最重要的准确率保护层。

在医疗记录场景里，真正的准确率保障不是“路由永远 100% 正确”，而是“即使错了，也不要直接写库”。

#### 3. fast router 比之前更保守

当前 fast router 已经开始对 `_SUPPLEMENT_RE`、tail command、pending draft continuation 增加 guard。

这符合 accuracy-first 原则：

- 宁可漏掉交给 LLM
- 也不要误判后直接走错执行路径

#### 4. `DoctorTurnContext` 的分层思路正确

当前已经明确区分：

- authoritative workflow state
- advisory memory / knowledge / recent history

这在医疗场景里非常重要。患者绑定、pending draft 这类状态必须是 authoritative；memory summary、knowledge snippet 只能是 advisory。

### 当前最大的架构问题

#### 1. 患者连续性状态还没有成为唯一权威来源

问题不是“没有状态”，而是这些状态还没有在所有层里被一致消费：

- router 用一部分
- add_record handler 用一部分
- LLM prompt 只注入 `current_patient_context`
- 某些场景仍然回退到 history 扫描或 LLM 自己抽名字

这会导致系统明明已经知道得比 LLM 多，但没有把这些结构化状态完整用于路由和执行。

#### 2. 当前主要风险不是 LLM 不准，而是状态传播不一致

剩余失败大多不是模型不懂临床内容，而是：

- 查到患者了但没 pin 到 session
- update 成功了但没设 current patient
- mixed-intent 里任务意图生效了，但患者主体没保留下来
- query not found 之后后续 turn 仍然靠 LLM/history 去猜

所以问题已经从“模型能力”转移到“系统状态一致性”。

#### 3. `DoctorTurnContext` 还不是整个 doctor agent 的统一入口

虽然已经有 per-turn context assembly，但当前主路由仍然大量直接读 session，而不是全程围绕 assembled context 工作。

这意味着当前架构是“目标方向正确，但尚未 fully converged”。

### 交叉评审后的综合判断

#### 1. 从患者安全角度

当前架构最大的优点是普通 add_record 已经有 draft-confirm 保护。

最大的风险是患者上下文跨轮不稳定，导致正确内容可能挂到错误或未知患者。

#### 2. 从路由角度

`fast_router -> LLM router` 这个双层设计仍然是正确的。

accuracy-first 下，不应该退回成纯 LLM。应该保留：

- 显式工作流短语 -> deterministic
- 模糊语义 -> LLM

#### 3. 从上下文角度

系统已经具备所需状态模型的雏形，但还没有完全收口。

真正需要的是让下面这些状态成为所有层共用的统一语义：

- `current_patient`
- `candidate_patient`
- `patient_not_found`
- `pending_record`

#### 4. 从 LLM 角度

当前 LLM 不是主问题。

LLM 只拿到较轻量的当前患者上下文，说明它仍然在承担一部分本应由结构化状态承担的工作。

#### 5. 从架构成熟度角度

当前不能简单说“架构设计错了”。

更准确的判断是：

- 架构方向是对的
- 关键状态已经开始出现
- 但仍处于半收敛状态
- 下一步最重要的不是重写，而是统一状态语义和消费方式

### 高层建议

#### 1. 保持 draft-first 写入模型

这是准确率底线，不要动。

#### 2. 保持 deterministic + LLM 双层路由

不要为了“简洁”回到单 LLM。

#### 3. 把患者连续性状态当成系统主干

优先级应当是：

1. 当前 turn 明示患者
2. pending draft patient
3. resolved current patient
4. candidate patient
5. patient not found state
6. history / LLM recovery

而不是让 LLM 继续承担患者恢复主责。

#### 4. 让 `DoctorTurnContext` 真正成为统一入口

现在它更像一个新架构原型，还不是整个 doctor agent 的核心骨架。

后续应该逐步把 router、executor、LLM dispatch 都收敛到这套上下文模型上。

### 最终判断

当前架构已经具备 accuracy-first 的正确基础，但还没有完全把“患者状态连续性”做成统一、权威、可复用的系统主线。

所以接下来最重要的不是换更强的 LLM，也不是大改路由层，而是把现有的患者上下文状态模型真正打通。

一句话总结：

当前影响准确率的首要问题，不是模型不够强，而是患者上下文虽然存在，但还没有在所有关键路径里被一致地当成真相来源。
