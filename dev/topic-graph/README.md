# topic-graph eval

回答一个问题：**topic-graph 的某段内容删掉或改写以后，agent 的行为有没有变差，开销有没有变小？** 所以它比较的是同一个 skill 的两个版本，不是"带 skill / 不带 skill"：默认 new = 工作区里的 `skills/topic-graph`，old = `main` 分支里的版本。本目录只放开发用的 eval，不会被安装。

和 progressive-learning 的 eval 不同，这里测的是 agent 的行为。topic-graph 要做的事大多是跑 `graph.py`、改专题文件，只看一条文字回复测不出来。所以每组都把一个小专题复制到临时目录，让 `claude -p` 带着 Bash/Read/Edit/Write 真的跑一遍会话。

## 怎么比

1. **同样的开局**：两边拿到同样的工作区说明（`cases/fixtures/workspace.md`）和同样的专题目录，唯一的区别是 skill 的版本。系统提示里附上 SKILL.md；参考文件（`files.md`、`nodes.md` 等）放在 skill 目录里，agent 要用时自己去读，和真实安装时一样。
2. **行为检查**（脚本判定）：看会话结束时的文件状态和运行过的命令。例如没通过复测的节点不能是 mastered、记完进度要 sync、建新专题时第一轮先问目标而不是直接建图、图谱 `check` 通过。
3. **开销**：费用、输入/输出 token、工具调用次数、用时，以及读过哪些参考文件。精简的版本应当在这里占优，而且不能在 2 和 4 上变差。
4. **盲评**（模型判定）：裁判不看 skill，按 `eval/judge.md` 的 7 项标准比较两份会话记录（每轮回复、运行的命令、文件的 diff）：只推荐能学的、只用学过的、记录诚实、意义与全景、尊重学习者、简洁、完成任务。每对按正反两种顺序各判一次，一致才算胜负，否则记平局。

agent 默认 `opus`，裁判默认 `sonnet`。

## 用例

`cases/public.jsonl`，10 个，都在 `cases/fixtures/net-basics/` 这个小专题上（"网页打开慢时网络里发生了什么"）。开局状态：N0 到了复习时间、T2 已讲未复测、T3/T4/D1 可学、T5 锁着且是目标终点、`debts.md` 里有一条待复测的误解。

| 用例 | 场景 | 主要考 skill 的哪部分 |
|---|---|---|
| G01 | 问下一步学什么 | B、`next` 的排序、复习 |
| G02 | 要学锁着的 T5 | 核心规则 1、2 |
| G03 | 课没过完，记录进度 | D.4、F、Writing node summaries |
| G04 | 课全过了，记录进度 | D.4、G |
| G05 | 图谱外的实际问题 | E |
| G06 | 课上冒出图谱里没有的概念 | D.3 |
| G07 | 学习者发现旧节点讲得过头 | F（caveat） |
| G08 | 隔了很久回来（日期整体推后 12 天） | I、J |
| G09 | 从零建一个新专题（两轮） | A |
| G10 | 诊断已有基础（所有节点重置为 new） | C |

用例字段：`turns`（依次发出的用户消息，不管助手说什么都照发）、`expect`（给裁判的预期效果）、`checks`（行为检查，见 `eval/run.py` 的 `run_check`；`@N:` 前缀表示第 N 轮之后检查）、可选的 `age_days`（日期整体推后）、`reset`（所有节点重置为 new）、`empty` + `topic`（空目录）。fixture 里的日期写成 `{{D-30}}`（30 天前），运行时换成真实日期，所以复习和 retro 的判断不会随时间漂移。

## 运行

依赖：`claude`（Claude Code CLI，已登录）、`uv`、`git`、Python 3.11+。在本目录下：

```bash
python3 eval/run.py                               # 工作区版本 vs main
python3 eval/run.py --against 74cca28             # 和某个提交里的版本比
python3 eval/run.py --skill /tmp/trimmed --against main   # 两个任意版本
python3 eval/run.py --only G03,G09 --reps 3
python3 eval/run.py --dry-run                     # 只写出提示词和开局专题目录，不调用模型
python3 eval/run.py --rejudge out/<上次> --judge-model opus   # 沿用会话记录，换裁判重评
```

结果在 `out/<时间>/`：`summary.md` 是汇总，`outputs/*.md` 是给裁判看的会话记录，`outputs/*.turns.json` 有每轮的工具调用和 token，`results.jsonl` 有逐项检查和裁判理由，`errors.jsonl` 记出错的组（超时、接口报错不算任何一方输）。

每组是一次真实的 agent 会话，10 个用例 × 2 个版本，加上裁判，一次完整运行要几十次模型调用。改一段内容时，先用 `--only` 跑和它相关的用例。

## 用它精简 skill

1. 先跑一次当前版本对自己（`--against` 指向当前提交），看同一版本两次之间的波动有多大。
2. 删或改一段，跑 new vs 旧版本。行为检查不降、盲评不输、开销下降，就保留这次删改。
3. 看 summary 里"读过的参考文件"：某个文件从来没人读，要么内容不需要，要么 SKILL.md 里的指引不够清楚；某个文件每次都读，就考虑把它放回 SKILL.md。
