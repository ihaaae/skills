# progressive-learning eval

对比 `skills/progressive-learning` 有没有让教学变好：同一个场景，让模型带 skill 和不带 skill 各写一遍"下一条回复"，再比较两份回复。skill 的流程是先把一个知识点写成 topic 文档，再按文档上课。eval 只测写文档。skill 要求先写分层计划、按清单自查，通过后直接写文档，不等用户确认，所以第一轮就应该拿到文档（格式检查 `doc_in_first_turn`）。第一轮只给了计划、停下等确认的，自动回复"可以，就按这个计划写吧"，第二轮的回复才是文档，裁判评文档，计划另存为 `outputs/*.plan.md`。知识点太大的 D02 只跑一轮，看它有没有拦下来。上课的进度由 skill 自带的 `scripts/lesson.py` 控制，有单元测试，这里不测。本目录只放开发用的 eval，不会被安装。

## 怎么比

1. **两种条件**：两边拿到同样的上下文（工作区说明、专题规则、topic-graph skill、对话历史），唯一的区别是 skill 那边多了 progressive-learning 的 SKILL.md。测的是这个 skill 在其余条件都在的情况下，多带来了什么。
2. **格式检查**（脚本判定）：输出有没有按 skill 规定的模块和节奏写。第一轮有没有只给计划、不写文档；文档直接调用 skill 自带的 `scripts/check_topic.py`：模块顺序、每层一个例子配两道题、共 2～4 层、题号连续、答案只在文末、知识里有图或表。这一层只能说明 skill 有没有被照着做，不能说明教得好。baseline 没看过这些规定，格式分低是预料之中的。
3. **盲评**（模型判定）：裁判不看 skill，按 `eval/judge.md` 里站在学习者角度的 8 项标准，逐项比较两份回复：读得懂、只用学过的、准确、意义与全景、节奏（层与层是否逐步推进）、题目（能否照例子的思路解出、干扰项和解析是否对应具体的错误推理）、完成这一轮的任务、避开学习者以前指出的问题。每对回复按正反两种顺序各判一次，两次一致才算胜负，否则记平局。

写作模型默认 `opus`，裁判默认 `sonnet`，两者不同，避免模型给自己打分。

## 用例

- `cases/public.jsonl`：5 个合成场景，都在"网页打开慢时网络里发生了什么"这个小专题里：写 T1 三次握手的文档（D01）、知识点太大时不写而是提醒（D02）、阅读型知识点的文档（D03）、写 T2 ACK 与重传的文档（D04）、全景类知识点也写两层以上（D05）。每个用例都会在用户消息末尾自动加上"请先写成 topic 文档"的请求，两边条件拿到的请求相同。
- `cases/learn.jsonl`：真实用例，只记专题和节点 ID（如 `robot-learn` 的 `C12`）。内容在运行时从本地 Learn 仓库读取，不复制进本仓库：
  - 工作区说明 `AGENTS.md` 和专题的 `rules.md`；
  - 用 topic-graph 的 `graph.py preflight <ID>` 现场生成写文档时的上下文。其中"本节点已有内容"是课后写的摘要，带着答题结果和学习者的纠正，会把答案透露给被测模型，所以替换成"(尚无)"；
  - 节点正文里记下的学习者反馈（`措辞`、`易错点`、`课上插问`、`精确化` 这几段）交给裁判，作为"避开旧问题"一项的依据。

  真实用例有 3 个（`robot-learn` 的 C12、C4，`Hidng-DSP` 的 F1）。

## 运行

依赖：`claude`（Claude Code CLI，已登录）、`uv`（跑 graph.py）、Python 3.11+。在本目录下：

```bash
python3 eval/run.py                            # 只跑合成用例
python3 eval/run.py --learn-dir ~/Learn        # 加上 Learn 里的真实用例
python3 eval/run.py --only D04,L-C12 --reps 3  # 指定用例，每个跑 3 轮
python3 eval/run.py --learn-dir ~/Learn --dry-run   # 只把组装好的提示词写到 out/，不调用模型
```

换裁判时不必重新写作：`python3 eval/run.py --learn-dir ~/Learn --rejudge out/<上次> --judge-model sonnet` 会沿用上次 `outputs/` 里的回复，只重新评审。

结果在 `out/<时间>/`：`summary.md` 是汇总表，`outputs/` 是每份回复的原文，`results.jsonl` 有逐项的裁判理由，`errors.jsonl` 记出错的组（超时、接口报错等不算任何一方输）。

### 后端

- 默认用 `claude -p`：走 Claude Code 订阅，不另外计费，只占用量额度。用 `--safe-mode` 运行，本机装的 skill、CLAUDE.md、hook 不会混进 baseline。`claude -p` 只接受一条用户消息，所以多轮历史被拼成一段文字放进提示里，和真实对话略有差别。
- `--backend api` 改用 Claude API，按真实的多轮消息发送，按 token 计费：`uv run --with anthropic eval/run.py --backend api`。没有开 fallback，一旦换了模型作答就记为出错。

跑一轮全部 8 个用例，最多 30 次写作（7 个两轮的用例 × 两边 × 2，加 D02 两边各 1）和 16 次裁判。`summary.md` 末尾会给出按 API 标价折算的费用。

## 怎么读结果

- 用例少，几个用例的胜负就能让比例大幅摆动。先看逐个用例的表，再去 `outputs/` 读原文，不要只看总数。
- 改了 SKILL.md 之后重跑，对比前后两次的 `summary.md`，看哪些用例从输变赢、哪些反过来。
- 裁判本身也会错。建议先挑十来个用例，自己判一遍哪份更好，再和裁判的结论对照；一致率不高的话，先改 `eval/judge.md`，再用它的分数指导修改 skill。

## 以后可以加的

- 让另一个模型扮演学习者、按节点里记下的易错点作答，把整节课连续跑完，评的是整段对话，而不只是单独一轮。
