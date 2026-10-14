# 工作区说明（AGENTS.md）

这里是学习者的学习工作区，每个专题一个目录；含 `topic.yaml` 的目录是用 topic-graph 管理的专题（例如 `net-basics/`）。

## 每次会话

1. 读专题的 `rules.md` 和 `goals.md`。
2. `graph.py check`，再 `graph.py next`：推荐下一个节点，说明理由和它通往哪个目标，由我选择。
3. 教之前先 `preflight <ID>`，再上课。
4. 状态只用 `graph.py set / add / retire` 改；每个节点教完，先把实际教过的内容写进节点正文，再 `set`。会话结束前 `graph.py sync`。

## 学习者偏好

- 写了几年后端，会用 HTTP 库和 socket API，但没系统学过网络原理。
- 讲解用中文；协议里的概念直接用英文词（packet、SYN、ACK、sequence number），首次出现附一句中文解释。
- 想知道每节课有什么用、为什么这样设计，不只要结论。
- 不读教材原文；题目要用到的事实必须课上讲过或写在题干里。
