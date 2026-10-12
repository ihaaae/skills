# progressive-learning eval

对比 `skills/progressive-learning` 有没有让教学变好：同一个场景，让模型带 skill 和不带 skill 各写一遍"下一条回复"，再比较两份回复。本目录只放开发用的 eval，不会被安装。

## 怎么比

1. **两种条件**：两边拿到同样的上下文（工作区说明、专题规则、topic-graph skill、对话历史），唯一的区别是 skill 那边多了 progressive-learning 的 SKILL.md。测的是这个 skill 在其余条件都在的情况下，多带来了什么。
2. **格式检查**（脚本判定）：输出有没有按 skill 规定的模块和节奏写，比如开课那一轮有没有 `### 定位`、`### 知识` 和图，有没有提前出题。这一层只能说明 skill 有没有被照着做，不能说明教得好。baseline 没看过这些规定，格式分低是预料之中的。
3. **盲评**（模型判定）：裁判不看 skill，按 `eval/judge.md` 里站在学习者角度的 7 项标准，逐项比较两份回复：读得懂、只用学过的、准确、意义与全景、节奏、完成这一轮的任务、避开学习者以前指出的问题。每对回复按正反两种顺序各判一次，两次一致才算胜负，否则记平局。

写作模型默认 `opus`，裁判默认 `sonnet`，两者不同，避免模型给自己打分。

## 用例

- `cases/public.jsonl`：10 个合成场景，用"TCP 三次握手"这个小主题，覆盖一节课里的各个环节：开课、讲例子、出题、答错后的反馈、复测失败不升级、两题都对后升级、发现缺前置知识、阅读节点、只问一个事实不想上课、没有图谱时先确认范围。前面几轮的助手回复写在 `cases/fixtures/`。
- `cases/learn.jsonl`：真实用例，只记专题和节点 ID（如 `robot-learn` 的 `C12`）。内容在运行时从本地 Learn 仓库读取，不复制进本仓库：
  - 工作区说明 `AGENTS.md` 和专题的 `rules.md`；
  - 用 topic-graph 的 `graph.py preflight <ID>` 现场生成开课时的上下文。其中"本节点已有内容"是课后写的摘要，带着答题结果和学习者的纠正，会把答案透露给被测模型，所以替换成"(尚无)"；
  - 节点正文里记下的学习者反馈（`措辞`、`易错点`、`课上插问`、`精确化` 这几段）交给裁判，作为"避开旧问题"一项的依据。

  现在真实用例只覆盖开课那一轮，因为 Learn 里没有保存完整的对话记录。

## 运行

依赖：`claude`（Claude Code CLI，已登录）、`uv`（跑 graph.py）、Python 3.11+。在本目录下：

```bash
python3 eval/run.py                            # 只跑合成用例
python3 eval/run.py --learn-dir ~/Learn        # 加上 Learn 里的真实用例
python3 eval/run.py --only P05,L-C12 --reps 3  # 指定用例，每个跑 3 轮
python3 eval/run.py --learn-dir ~/Learn --dry-run   # 只把组装好的提示词写到 out/，不调用模型
```

结果在 `out/<时间>/`：`summary.md` 是汇总表，`outputs/` 是每份回复的原文，`results.jsonl` 有逐项的裁判理由，`errors.jsonl` 记出错的组（超时、接口报错等不算任何一方输）。

### 后端

- 默认用 `claude -p`：走 Claude Code 订阅，不另外计费，只占用量额度。用 `--safe-mode` 运行，本机装的 skill、CLAUDE.md、hook 不会混进 baseline。`claude -p` 只接受一条用户消息，所以多轮历史被拼成一段文字放进提示里，和真实对话略有差别。
- `--backend api` 改用 Claude API，按真实的多轮消息发送，按 token 计费：`uv run --with anthropic eval/run.py --backend api`。没有开 fallback，一旦换了模型作答就记为出错。

跑一轮全部 18 个用例，大约是 36 次写作加 36 次裁判。`summary.md` 末尾会给出按 API 标价折算的费用。

## 怎么读结果

- 用例少，几个用例的胜负就能让比例大幅摆动。先看逐个用例的表，再去 `outputs/` 读原文，不要只看总数。
- 改了 SKILL.md 之后重跑，对比前后两次的 `summary.md`，看哪些用例从输变赢、哪些反过来。
- 裁判本身也会错。建议先挑十来个用例，自己判一遍哪份更好，再和裁判的结论对照；一致率不高的话，先改 `eval/judge.md`，再用它的分数指导修改 skill。

## 以后可以加的

- 让另一个模型扮演学习者、按节点里记下的易错点作答，把整节课连续跑完，评的是整段对话，而不只是单独一轮。
- 以后上课时保存对话记录，就能把真实的中间几轮（答错、插问）也做成用例。
