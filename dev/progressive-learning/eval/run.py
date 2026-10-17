#!/usr/bin/env python3
"""progressive-learning 的对比 eval：同一个场景，带 skill 和不带 skill 各写一遍下一轮回复，再比较。

用例都是写 topic 文档：skill 要求先写分层计划、自查通过后直接写文档，不等用户确认，所以第一轮就应该拿到文档。
第一轮只给了计划、停下来等确认的（旧版 skill 或不带 skill 的回复可能这样），自动回复一句"可以，就按这个计划写吧"，
第二轮的回复才是文档，裁判评的是文档。知识点太大的用例只跑一轮，看它有没有拦下来。
上课由 skill 自带的 lesson.py 控制进度，这里不测。

  python3 eval/run.py                              # 跑 cases/ 下所有用例（Learn 用例需要 --learn-dir）
  python3 eval/run.py --learn-dir ~/Learn          # 加上从 Learn 仓库现取内容的真实用例
  python3 eval/run.py --only D01,L-C12 --reps 2
  python3 eval/run.py --dry-run                    # 只组装提示词写到 out/，不调用模型
  python3 eval/run.py --rejudge out/<上次> --judge-model sonnet   # 沿用上次的回复，换裁判重新评审
  python3 eval/run.py --against /tmp/old-SKILL.md  # 新旧两版 skill 对比（baseline 一边用旧版）
  # 两边都会一并读入 SKILL.md 同目录的 modules.md、questions.md（有的话）；拷旧版时连它们一起拷
  uv run --with anthropic eval/run.py --backend api  # 改走 Claude API（按 token 计费）

两层评分，分开报告：
  1. 格式检查（脚本判定）：输出有没有照 skill 规定的模块和节奏写。只说明 skill 被遵守，不说明教得好。
  2. 盲评（模型判定）：裁判不看 skill，按 eval/judge.md 的学习者视角标准逐项比较两份输出，
     正反两种顺序各判一次，两次一致才算胜负，否则记平局。

默认后端是 `claude -p`（走 Claude Code 订阅，不需要 API key）。它不能直接传入多轮历史，
所以历史对话被拼成一段文字放进提示里；--backend api 则按真实的多轮消息发送。
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import random
import re
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent            # dev/progressive-learning/eval
DEV = HERE.parent                                 # dev/progressive-learning
REPO = DEV.parent.parent                          # 仓库根
SKILL = REPO / "skills" / "progressive-learning" / "SKILL.md"
TOPIC_GRAPH_SKILL = REPO / "skills" / "topic-graph" / "SKILL.md"
WRITING_SKILL = REPO / "skills" / "writing-for-learners" / "SKILL.md"   # progressive-learning 让 agent 写文档前读它
GRAPH_PY = REPO / "skills" / "topic-graph" / "scripts" / "graph.py"
CHECK_TOPIC_PY = SKILL.parent / "scripts" / "check_topic.py"
CASES_DIR = DEV / "cases"
FIXTURES = CASES_DIR / "fixtures"

API_MODELS = {"opus": "claude-opus-5-5", "sonnet": "claude-sonnet-5-5", "haiku": "claude-haiku-5-5"}
CONDITIONS = ("skill", "baseline")

# 每个阶段：这一轮应该达到什么（给裁判的结果描述），以及格式检查。
STAGES = {
    "document": {
        "expect": "学习者要学一个新知识点，并要求先把整节课写成一份 topic 文档：讲清这节课通往什么目标、"
                  "核心原理及其动机，配图或表；之后是逐层加深的例子和题目，每道题都能只靠前面讲过的内容"
                  "和学习者已有的知识解出来；答案和解析放在文末，学习者从头读时不会先看到答案。",
        "checks": ["topic_doc"],
        "two_turn": True,
    },
    "reading_document": {
        "expect": "这个知识点要求学习者去读一段指定的材料，学习者要求先写成 topic 文档：说明这节课的定位，"
                  "布置具体的阅读任务（读哪篇哪几节、预计用时）和两三个带着读的引导问题，"
                  "收拢材料要建立的主张，再逐层用例子和题目考这些主张及其应用；不要把材料内容自己讲一遍代替阅读。",
        "checks": ["topic_doc:reading"],
        "two_turn": True,
    },
    "too_big": {
        "expect": "学习者要求把一个知识点写成 topic 文档，但这个知识点明显不是 25 分钟能学完的："
                  "不要勉强写出文档，而是告诉学习者它太大在哪里、可以怎样拆。",
        "checks": ["no_h3:例子一", "no_h3:问题一"],
    },
}

# 每个用例都在最后一条用户消息后面加上这段请求。第一轮只给了计划时，用 APPROVE 回复。
DOC_REQUEST = ("请先把这节课写成一份完整的 topic 文档（含全部题目，答案集中放在文末），写好后我们再按文档上课。"
               "本环境不能写文件，直接把文档作为回复输出。")
APPROVE = "可以，就按这个计划写吧。"

BASELINE_SYSTEM = """你是一个耐心的学习助手，帮助用户学习。下面附上用户的工作区说明和本专题的规则，以及管理学习进度用的 topic-graph skill。\
本环境里你不能调用工具：需要的命令输出会直接写在用户消息里，要写进文件的内容直接写在回复里。只写出你的下一条回复。"""

SKILL_SYSTEM = """你是一个耐心的学习助手，帮助用户学习。下面附上用户的工作区说明和本专题的规则，以及管理学习进度用的 topic-graph skill，\
和讲课用的 progressive-learning skill。教学时遵循 progressive-learning skill。\
本环境里你不能调用工具：需要的命令输出会直接写在用户消息里，要写进文件的内容直接写在回复里。只写出你的下一条回复。"""


# ---------------------------------------------------------------- 用例

def load_cases(paths: list[Path], learn_dir: Path | None) -> list[dict]:
    cases = []
    for path in paths:
        for n, line in enumerate(path.read_text().splitlines(), 1):
            if not line.strip():
                continue
            case = json.loads(line)
            case["_file"] = f"{path.name}:{n}"
            if case.get("source") == "learn":
                if learn_dir is None:
                    continue
                case = materialize_learn_case(case, learn_dir)
            case["turns"] = [resolve_turn(t) for t in case["turns"]]
            last = case["turns"][-1]
            case["turns"][-1] = {**last, "content": last["content"] + "\n\n" + DOC_REQUEST}
            for key in ("context", "learner"):
                if f"{key}_ref" in case:
                    case[key] = (FIXTURES / case.pop(f"{key}_ref")).read_text().strip()
            stage = STAGES[case["stage"]]
            case.setdefault("expect", stage["expect"])
            case.setdefault("checks", stage["checks"])
            case.setdefault("two_turn", stage.get("two_turn", False))
            case.setdefault("watch", [])
            case.setdefault("learner", "")
            case.setdefault("context", "")
            case["_hash"] = hashlib.sha256(
                json.dumps({k: case[k] for k in ("context", "learner", "turns", "watch")},
                           ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:12]
            cases.append(case)
    return cases


def resolve_turn(turn: dict) -> dict:
    if "ref" in turn:
        return {"role": turn["role"], "content": (FIXTURES / turn["ref"]).read_text().strip()}
    return turn


FEEDBACK_RE = re.compile(r"^\**(措辞|易错点|课上插问|精确化)")


def materialize_learn_case(case: dict, learn_dir: Path) -> dict:
    """从 Learn 仓库现取内容：工作区说明、专题规则、preflight 输出，以及节点里记下的学习者反馈。

    preflight 里"本节点已有内容"一节是课后写的摘要（含答题结果和学习者的纠正），
    会把答案透露给被测模型，所以替换掉，只保留节点标题。
    """
    topic = learn_dir / case["topic"]
    node_id = case["node"]
    node_file = next(topic.glob(f"nodes/*/{node_id}.md"))
    out = subprocess.run(["uv", "run", "--quiet", str(GRAPH_PY), "preflight", node_id],
                         cwd=topic, capture_output=True, text=True, timeout=120, check=False)
    if out.returncode != 0:
        raise SystemExit(f"{case['id']}: preflight 失败\n{out.stdout}\n{out.stderr}")
    preflight = out.stdout.split("—— 本节点已有内容 ——")[0].rstrip() + "\n\n—— 本节点已有内容 ——\n(尚无)\n"
    preflight = "\n".join(l for l in preflight.splitlines() if "已是 ✅" not in l)
    preflight = re.sub(r"^(✓ \S+ 可以讲  )\[\S+\]", r"\1[🔓]", preflight, count=1, flags=re.MULTILINE)

    body = node_file.read_text()
    watch = [para.strip() for para in re.split(r"\n\s*\n", body) if FEEDBACK_RE.match(para.strip())]
    workspace = (learn_dir / "AGENTS.md").read_text()
    rules = (topic / "rules.md").read_text() if (topic / "rules.md").exists() else ""
    case = dict(case)
    case["context"] = f"# 工作区说明（AGENTS.md）\n\n{workspace}\n\n# 本专题规则（{case['topic']}/rules.md）\n\n{rules}"
    case["learner"] = workspace.split("## 学习者偏好", 1)[-1].strip()
    case["watch"] = case.get("watch", []) + watch
    case["turns"] = [{"role": "user", "content":
                      f"开始学 {node_id}。\n\n[graph.py preflight {node_id} 的输出]\n{preflight}"}]
    return case


# ---------------------------------------------------------------- 格式检查

def h3_titles(text: str) -> list[str]:
    return [m.group(1).strip() for m in re.finditer(r"^###\s+(.+)$", text, re.MULTILINE)]


def load_check_topic():
    """skill 自带的文档结构检查脚本，eval 直接复用它。"""
    spec = importlib.util.spec_from_file_location("check_topic", CHECK_TOPIC_PY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


check_topic = load_check_topic()


def run_check(name: str, text: str) -> bool:
    heads = h3_titles(text)
    kind, _, arg = name.partition(":")
    if kind == "topic_doc":
        return not check_topic.check(text, reading=arg == "reading")
    if kind == "h3":
        return any(h.startswith(arg) for h in heads)
    if kind == "no_h3":
        return not any(h.startswith(arg) for h in heads)
    raise ValueError(f"未知检查 {name}")


# ---------------------------------------------------------------- 模型调用

def flatten(turns: list[dict]) -> str:
    """claude -p 只接受一条用户消息：把历史拼成文字，最后一条用户消息单独放。"""
    *history, last = turns
    if not history:
        return last["content"]
    parts = ["以下是到目前为止的对话记录。请以助手的身份，只写出对最后一条用户消息的下一条回复。", "<对话记录>"]
    for t in history:
        parts.append(("[用户]" if t["role"] == "user" else "[助手]") + "\n" + t["content"])
    parts += ["</对话记录>", "[用户最新消息]\n" + last["content"]]
    return "\n\n".join(parts)


class ClaudeCLI:
    """`claude -p`：safe mode 关掉本机的 skill、CLAUDE.md、hook 和插件，免得本机装的 skill 混进 baseline。"""

    def __init__(self, effort: str | None):
        self.effort = effort
        self.cwd = tempfile.mkdtemp(prefix="pl-eval-")

    def call(self, model: str, system: str, turns: list[dict], schema: dict | None = None) -> dict:
        sp = Path(self.cwd) / f"system-{hashlib.sha256(system.encode()).hexdigest()[:16]}.md"
        if not sp.exists():
            sp.write_text(system)
        cmd = ["claude", "-p", "--safe-mode", "--tools", "", "--no-session-persistence",
               "--system-prompt-file", str(sp), "--model", model, "--output-format", "json"]
        if self.effort:
            cmd += ["--effort", self.effort]
        if schema:
            cmd += ["--json-schema", json.dumps(schema)]
        t0 = time.time()
        proc = subprocess.run(cmd, input=flatten(turns), capture_output=True, text=True,
                              cwd=self.cwd, timeout=900, check=False)
        try:
            data = json.loads(proc.stdout)
        except json.JSONDecodeError:
            raise RuntimeError(f"claude -p 没有返回 JSON（exit {proc.returncode}）：{proc.stderr[-800:] or proc.stdout[-800:]}")
        if data.get("is_error") or data.get("subtype") != "success":
            raise RuntimeError(f"claude -p 出错：{data.get('subtype')} {data.get('api_error_status')} {data.get('result', '')[:300]}")
        served = list((data.get("modelUsage") or {}).keys())
        return {"text": data.get("result") or "", "json": data.get("structured_output"),
                "served": served, "cost_usd": data.get("total_cost_usd"),
                "seconds": round(time.time() - t0, 1), "stop_reason": data.get("stop_reason")}


class ClaudeAPI:
    """Anthropic Messages API：真实的多轮消息。需要 `anthropic` 包和凭据（ANTHROPIC_API_KEY 或 ant auth login）。

    有意不开 server-side fallbacks：fallback 会换模型作答，eval 就不知道分数属于哪个模型了。
    遇到 refusal 记为错误。
    """

    def __init__(self, effort: str | None):
        import anthropic
        self.anthropic = anthropic
        self.client = anthropic.Anthropic(max_retries=4)
        self.effort = effort

    def call(self, model: str, system: str, turns: list[dict], schema: dict | None = None) -> dict:
        model_id = API_MODELS.get(model, model)
        kwargs = {"model": model_id, "max_tokens": 16000, "system": system,
                  "messages": [{"role": t["role"], "content": t["content"]} for t in turns]}
        output_config = {}
        if self.effort:
            output_config["effort"] = self.effort
        if schema:
            output_config["format"] = {"type": "json_schema", "schema": schema}
        if output_config:
            kwargs["output_config"] = output_config
        t0 = time.time()
        resp = self.client.messages.create(**kwargs)
        if resp.stop_reason in ("refusal", "max_tokens"):
            raise RuntimeError(f"stop_reason={resp.stop_reason}")
        if not resp.model.startswith(model_id):
            raise RuntimeError(f"请求 {model_id}，实际由 {resp.model} 作答")
        text = "".join(b.text for b in resp.content if b.type == "text")
        return {"text": text, "json": json.loads(text) if schema else None, "served": [resp.model],
                "cost_usd": None, "usage": resp.usage.to_dict(), "seconds": round(time.time() - t0, 1),
                "stop_reason": resp.stop_reason}


# ---------------------------------------------------------------- 写作与评审

SKILL_FILES = {"skill": SKILL, "baseline": None}   # --skill / --against 会改这里


SKILL_REFERENCES = ["modules.md", "questions.md"]   # SKILL.md 让 agent 写文档前读完的参考文档
TOPIC_GRAPH_REFERENCES = ["teaching.md", "files.md", "nodes.md", "building.md", "diagnosis.md", "upkeep.md"]


def skill_text(skill_file: Path, references: list[str] = SKILL_REFERENCES) -> str:
    """SKILL.md 加上同目录的参考文档。"""
    parts = [skill_file.read_text()]
    for name in references:
        ref = skill_file.parent / name
        if ref.exists():
            parts.append(f"# {name}\n\n{ref.read_text()}")
    return "\n\n".join(parts)


def system_prompt(case: dict, condition: str) -> str:
    skill_file = SKILL_FILES[condition]
    parts = [SKILL_SYSTEM if skill_file else BASELINE_SYSTEM]
    if case["context"]:
        parts.append(case["context"])
    parts.append("# topic-graph skill\n\n" + skill_text(TOPIC_GRAPH_SKILL, TOPIC_GRAPH_REFERENCES))
    if skill_file:
        parts.append("# progressive-learning skill\n\n" + skill_text(skill_file))
        parts.append("# writing-for-learners skill\n\n" + WRITING_SKILL.read_text())
    return "\n\n---\n\n".join(parts)


JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "criteria": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "winner": {"type": "string", "enum": ["A", "B", "tie", "na"]},
                    "reason": {"type": "string"},
                },
                "required": ["id", "winner", "reason"],
                "additionalProperties": False,
            },
        },
        "overall": {"type": "string", "enum": ["A", "B", "tie"]},
        "overall_reason": {"type": "string"},
    },
    "required": ["criteria", "overall", "overall_reason"],
    "additionalProperties": False,
}

CRITERIA = ["readable", "taught_only", "accurate", "meaning", "pacing", "questions", "task", "watch"]


def judge_prompt(case: dict, a: str, b: str) -> str:
    history = flatten(case["turns"]) if len(case["turns"]) > 1 else case["turns"][0]["content"]
    watch = "\n".join(f"- {w}" for w in case["watch"]) or "（无）"
    return f"""## 学习者
{case['learner'] or '一位聪明、但没有这个领域背景的成年学习者。'}

## 这一轮之前的对话（被评审的回复要接在它后面）
<对话>
{history}
</对话>

## 这一轮应该达到的效果
{case['expect']}

## 这位学习者以前在类似课上指出过的问题（criterion watch 用）
{watch}

## 回复 A
<回复A>
{a}
</回复A>

## 回复 B
<回复B>
{b}
</回复B>
"""


def judge(backend, model: str, case: dict, outputs: dict, rng: random.Random) -> dict:
    """正反两种顺序各判一次；同一项两次一致才算胜负，否则记平局。"""
    system = (HERE / "judge.md").read_text()
    first_skill_is_a = rng.random() < 0.5
    rounds = []
    for skill_is_a in (first_skill_is_a, not first_skill_is_a):
        a, b = (outputs["skill"], outputs["baseline"]) if skill_is_a else (outputs["baseline"], outputs["skill"])
        r = backend.call(model, system, [{"role": "user", "content": judge_prompt(case, a, b)}], JUDGE_SCHEMA)
        verdict = r["json"] or {}

        def who(w, skill_is_a=skill_is_a):
            return {"A": "skill" if skill_is_a else "baseline",
                    "B": "baseline" if skill_is_a else "skill"}.get(w, w)

        rounds.append({"skill_is_a": skill_is_a, "served": r["served"], "cost_usd": r["cost_usd"],
                       "criteria": {c["id"]: {"winner": who(c["winner"]), "reason": c["reason"]}
                                    for c in verdict.get("criteria", [])},
                       "overall": who(verdict.get("overall")), "overall_reason": verdict.get("overall_reason")})
    merged = {}
    for cid in CRITERIA + ["overall"]:
        if cid == "overall":
            w1, w2 = rounds[0]["overall"], rounds[1]["overall"]
        else:
            w1 = rounds[0]["criteria"].get(cid, {}).get("winner")
            w2 = rounds[1]["criteria"].get(cid, {}).get("winner")
        if w1 is None or w2 is None:
            merged[cid] = "missing"
        elif w1 == w2:
            merged[cid] = w1
        elif "na" in (w1, w2):
            merged[cid] = "na"
        else:
            merged[cid] = "tie"
    return {"merged": merged, "rounds": rounds}


def write(backend, args, case: dict, cond: str) -> tuple[str, str | None, dict]:
    """写出被评的回复。第一轮只给了计划时，回复 APPROVE 再拿文档。返回 (文档, 计划, 写作信息)。"""
    system = system_prompt(case, cond)
    r = backend.call(args.model, system, case["turns"])
    info = {"served": r["served"], "cost_usd": r["cost_usd"], "seconds": r["seconds"]}
    if not case["two_turn"] or not run_check("no_h3:例子一", r["text"]):
        return r["text"], None, info
    turns = case["turns"] + [{"role": "assistant", "content": r["text"]}, {"role": "user", "content": APPROVE}]
    r2 = backend.call(args.model, system, turns)
    info = {"served": sorted(set(info["served"] + r2["served"])),
            "cost_usd": (info["cost_usd"] or 0) + (r2["cost_usd"] or 0) if info["cost_usd"] is not None else None,
            "seconds": round(info["seconds"] + r2["seconds"], 1)}
    return r2["text"], r["text"], info


def checks_for(case: dict, doc: str, plan: str | None) -> dict:
    checks = {c: run_check(c, doc) for c in case["checks"]}
    if case["two_turn"]:   # 新版 skill 自查计划后直接写文档，第一轮停下等确认算没做到
        checks["doc_in_first_turn"] = plan is None
    return checks


def run_one(backend, args, case: dict, rep: int, out_dir: Path) -> dict:
    row = {"id": case["id"], "stage": case["stage"], "rep": rep, "case_hash": case["_hash"],
           "writer_model": args.model, "judge_model": args.judge_model, "backend": args.backend}
    outputs = {}
    prev = args.prev_rows.get((case["id"], rep)) if args.rejudge else None
    if prev:  # 只重新评审：沿用上次写好的回复和写作信息
        row["writer_model"], row["backend"] = prev["writer_model"], prev["backend"]
    for cond in CONDITIONS:
        name = f"{case['id']}__{cond}__r{rep}"
        if prev:
            doc = (args.rejudge / "outputs" / f"{name}.md").read_text()
            plan_file = args.rejudge / "outputs" / f"{name}.plan.md"
            plan = plan_file.read_text() if plan_file.exists() else None
            info = prev[cond]
        else:
            doc, plan, info = write(backend, args, case, cond)
        outputs[cond] = doc
        row[cond] = {**info, "chars": len(doc), "checks": checks_for(case, doc, plan)}
        (out_dir / "outputs" / f"{name}.md").write_text(doc)
        if plan is not None:
            (out_dir / "outputs" / f"{name}.plan.md").write_text(plan)
    rng = random.Random(f"{case['id']}:{rep}")
    row["judge"] = judge(backend, args.judge_model, case, outputs, rng)
    return row


# ---------------------------------------------------------------- 汇总

def tally(values):
    return {k: sum(1 for v in values if v == k) for k in ("skill", "baseline", "tie", "na", "missing")}


def write_summary(rows: list[dict], errors: list[dict], out_dir: Path, args) -> str:
    writer = ", ".join(sorted({r["writer_model"] for r in rows})) or args.model
    sides = f"skill 一边用 `{args.skill}`，baseline 一边" + (f"用 `{args.against}`" if args.against else "不带 skill")
    rejudged = f"（沿用 `{args.rejudge}` 的回复）" if args.rejudge else ""
    lines = [f"# progressive-learning eval：{out_dir.name}", "",
             (f"写作 `{writer}`{rejudged}，裁判 `{args.judge_model}`，后端 `{args.backend}`，"
              f"{len({r['id'] for r in rows})} 个用例 × {args.reps} 轮，{len(rows)} 组成功，{len(errors)} 组出错。"), sides + "。", ""]

    overall = tally([r["judge"]["merged"]["overall"] for r in rows])
    lines += ["## 盲评总体偏好", "",
              (f"skill 胜 {overall['skill']}，baseline 胜 {overall['baseline']}，平局 {overall['tie']}"
               "（正反顺序判断不一致也记平局）。"), ""]
    lines += ["## 盲评分项", "", "| 标准 | skill | baseline | 平局 | 不适用 |", "|---|---|---|---|---|"]
    for cid in CRITERIA:
        t = tally([r["judge"]["merged"][cid] for r in rows])
        lines.append(f"| {cid} | {t['skill']} | {t['baseline']} | {t['tie']} | {t['na'] + t['missing']} |")

    lines += ["", "## 格式检查（是否照 skill 的模块与节奏写；不代表教得好）", "",
              "| 条件 | 全部通过的输出 | 单项通过率 |", "|---|---|---|"]
    for cond in CONDITIONS:
        checks = [r[cond]["checks"] for r in rows]
        full = sum(all(c.values()) for c in checks)
        items = [v for c in checks for v in c.values()]
        rate = f"{sum(items)}/{len(items)}" if items else "-"
        lines.append(f"| {cond} | {full}/{len(checks)} | {rate} |")

    lines += ["", "## 逐个用例", "", "| 用例 | 阶段 | 轮 | 总体 | 格式 skill | 格式 baseline | 分项（skill/baseline/平） |",
              "|---|---|---|---|---|---|---|"]
    for r in sorted(rows, key=lambda r: (r["id"], r["rep"])):
        m = r["judge"]["merged"]
        t = tally([m[c] for c in CRITERIA])
        fmt = {c: f"{sum(r[c]['checks'].values())}/{len(r[c]['checks'])}" for c in CONDITIONS}
        lines.append(f"| {r['id']} | {r['stage']} | {r['rep']} | {m['overall']} | {fmt['skill']} | {fmt['baseline']} "
                     f"| {t['skill']}/{t['baseline']}/{t['tie']} |")

    cost = [x for r in rows for x in [r["skill"]["cost_usd"], r["baseline"]["cost_usd"]]
            + [rd["cost_usd"] for rd in r["judge"]["rounds"]] if x is not None]
    if cost:
        lines += ["", f"按 API 标价折算的费用约 ${sum(cost):.2f}（走订阅时不另外计费，只占用量额度）。"]
    served = sorted({m for r in rows for c in CONDITIONS for m in r[c]["served"]})
    lines += [f"实际作答的模型：{', '.join(served)}。"]
    if errors:
        lines += ["", "## 出错（未计入上面的统计）", ""] + [f"- {e['id']} r{e['rep']}：{e['error']}" for e in errors]
    lines += ["", "用例少时，几个用例的胜负就能让比例大幅摆动；看逐个用例和 outputs/ 里的原文，比只看总数可靠。"]
    text = "\n".join(lines) + "\n"
    (out_dir / "summary.md").write_text(text)
    return text


# ---------------------------------------------------------------- 入口

def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--cases", nargs="*", type=Path, default=sorted(CASES_DIR.glob("*.jsonl")))
    p.add_argument("--learn-dir", type=Path, help="本地 Learn 仓库；不给就跳过 source=learn 的用例")
    p.add_argument("--only", help="逗号分隔的用例 ID")
    p.add_argument("--reps", type=int, default=1)
    p.add_argument("--model", default="opus", help="写作模型（claude -p 的别名，或 API 模型 ID）")
    p.add_argument("--judge-model", default="sonnet", help="裁判模型；默认和写作模型不同，避免自己给自己打分")
    p.add_argument("--effort", help="low|medium|high|xhigh|max，不给就用默认值")
    p.add_argument("--backend", choices=["cli", "api"], default="cli")
    p.add_argument("--jobs", type=int, default=3, help="并发数；订阅有用量上限，不宜太大")
    p.add_argument("--out", type=Path, help="输出目录，默认 out/<时间>")
    p.add_argument("--dry-run", action="store_true", help="只写出组装好的提示词，不调用模型")
    p.add_argument("--skill", type=Path, default=SKILL, help="skill 一边用的 SKILL.md，默认是仓库里的当前版本")
    p.add_argument("--against", type=Path, help="baseline 一边改用这个 SKILL.md（比较两个版本），不给就是不带 skill")
    p.add_argument("--rejudge", type=Path, help="上次的输出目录：不重新写作，只用 --judge-model 重新评审那些回复")
    args = p.parse_args()

    SKILL_FILES["skill"], SKILL_FILES["baseline"] = args.skill, args.against
    cases = load_cases(args.cases, args.learn_dir.expanduser() if args.learn_dir else None)
    if args.only:
        wanted = set(args.only.split(","))
        cases = [c for c in cases if c["id"] in wanted]
    if not cases:
        print("没有可跑的用例（Learn 用例需要 --learn-dir）。", file=sys.stderr)
        return 1

    out_dir = args.out or DEV / "out" / datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    (out_dir / "outputs").mkdir(parents=True, exist_ok=True)

    if args.dry_run:
        pdir = out_dir / "prompts"
        pdir.mkdir(exist_ok=True)
        for c in cases:
            for cond in CONDITIONS:
                (pdir / f"{c['id']}__{cond}.md").write_text(
                    f"<!-- system -->\n{system_prompt(c, cond)}\n\n<!-- user -->\n{flatten(c['turns'])}\n")
            (pdir / f"{c['id']}__judge.md").write_text(judge_prompt(c, "（skill 的输出）", "（baseline 的输出）"))
        print(f"{len(cases)} 个用例的提示词写到 {pdir}")
        return 0

    backend = ClaudeCLI(args.effort) if args.backend == "cli" else ClaudeAPI(args.effort)
    jobs = [(c, rep) for c in cases for rep in range(1, args.reps + 1)]
    args.prev_rows = {}
    if args.rejudge:
        prev = [json.loads(line) for line in (args.rejudge / "results.jsonl").read_text().splitlines() if line]
        args.prev_rows = {(r["id"], r["rep"]): r for r in prev}
        stale = [r["id"] for r in prev if r["id"] in {c["id"] for c in cases}
                 and r["case_hash"] != next(c["_hash"] for c in cases if c["id"] == r["id"])]
        if stale:
            print(f"注意：这些用例在上次运行后改过，旧回复对应的是旧场景：{', '.join(sorted(set(stale)))}", file=sys.stderr)
        jobs = [(c, rep) for c in cases for rep in sorted({r for (i, r) in args.prev_rows if i == c["id"]})]
        args.reps = max((rep for _, rep in jobs), default=1)
    rows, errors = [], []
    with ThreadPoolExecutor(max_workers=args.jobs) as pool, (out_dir / "results.jsonl").open("w") as fout:
        futures = {pool.submit(run_one, backend, args, c, rep, out_dir): (c, rep) for c, rep in jobs}
        for fut in as_completed(futures):
            c, rep = futures[fut]
            try:
                row = fut.result()
            except Exception as e:  # noqa: BLE001  基础设施错误单独记，不当成模型输了
                errors.append({"id": c["id"], "rep": rep, "error": f"{type(e).__name__}: {e}"})
                print(f"✗ {c['id']} r{rep}: {e}", file=sys.stderr)
                continue
            rows.append(row)
            fout.write(json.dumps(row, ensure_ascii=False) + "\n")
            fout.flush()
            print(f"✓ {c['id']} r{rep}: 总体 {row['judge']['merged']['overall']}", file=sys.stderr)
    (out_dir / "errors.jsonl").write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in errors))
    print(write_summary(rows, errors, out_dir, args))
    return 0 if rows else 1


if __name__ == "__main__":
    sys.exit(main())
