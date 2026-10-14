#!/usr/bin/env python3
"""topic-graph 的对比 eval：同一个场景，用两个版本的 skill 各跑一遍 agent 会话，再比较。

和 progressive-learning 的 eval 不同，这里测的是 agent 的行为：每组都把一个小专题复制到临时目录，
让 `claude -p` 带 Bash/Read/Edit/Write 真的去跑 graph.py、改文件。默认比较的是当前版本（new）
和 git 里的旧版本（old，默认 main），用来回答"这段删掉以后，行为有没有变差、开销有没有变小"。

  python3 eval/run.py                                  # 当前工作区版本 vs main
  python3 eval/run.py --against 74cca28                # 和某个提交里的版本比
  python3 eval/run.py --against /path/to/topic-graph   # 和一个目录比（含 SKILL.md）
  python3 eval/run.py --only G03,G09 --reps 3
  python3 eval/run.py --dry-run                        # 只准备专题目录和提示词，不调用模型
  python3 eval/run.py --rejudge out/<上次> --judge-model sonnet   # 沿用上次的会话记录，只重新评审

三类结果，分开报告：
  1. 行为检查（脚本判定）：会话结束时的文件状态和运行过的命令，例如"没通过复测就不能是 mastered"。
  2. 开销：费用、token、工具调用次数、读了 skill 的哪些参考文件。精简版本应当在这里占优。
  3. 盲评（模型判定）：裁判不看 skill，按 eval/judge.md 比较两份会话记录（回复 + 命令 + 文件改动），
     正反两种顺序各判一次，两次一致才算胜负，否则记平局。

用例的多轮对话是写好的：不管助手说了什么，下一轮用户消息都照用例发。
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import random
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

HERE = Path(__file__).resolve().parent            # dev/topic-graph/eval
DEV = HERE.parent                                 # dev/topic-graph
REPO = DEV.parent.parent                          # 仓库根
SKILL_DIR = REPO / "skills" / "topic-graph"
CASES_DIR = DEV / "cases"
FIXTURES = CASES_DIR / "fixtures"
DEFAULT_TOPIC = "net-basics"

CONDITIONS = ("new", "old")
AGENT_TOOLS = "Bash,Read,Edit,Write,Glob,Grep"
DATE_RE = re.compile(r"\{\{D-(\d+)\}\}")
STATUS_RE = re.compile(r'^status:\s*"?(\w+)"?', re.MULTILINE)

SYSTEM = """你在学习者的学习工作区里当学习助手，可以运行命令、读写文件。学习者就是和你对话的用户。

本工作区装了 topic-graph skill，目录是 `{skill_dir}`（下文的 `<skill-dir>`）。它的 SKILL.md 附在下面；
SKILL.md 提到的同目录参考文件，需要时用 Read 去读。图谱脚本：`uv run {skill_dir}/scripts/graph.py <命令>`。

本环境没有讲课用的其他 skill。这次会话里不必真的上一整节课：学习者要你做什么，就只做那一步，然后停下等他。

{workspace}

---

# topic-graph skill（SKILL.md）

{skill}
"""


# ---------------------------------------------------------------- 用例与 skill 版本

def load_cases(paths: list[Path]) -> list[dict]:
    cases = []
    for path in paths:
        for n, line in enumerate(path.read_text().splitlines(), 1):
            if not line.strip():
                continue
            case = json.loads(line)
            case["_file"] = f"{path.name}:{n}"
            case.setdefault("topic", DEFAULT_TOPIC)
            case["_hash"] = hashlib.sha256(json.dumps(
                {k: case.get(k) for k in ("turns", "expect", "age_days", "reset", "empty", "topic")},
                ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:12]
            cases.append(case)
    return cases


def resolve_skill(spec: str, tmp: Path) -> Path:
    """目录、SKILL.md 文件，或 git ref（取那个提交里的 skills/topic-graph）。"""
    p = Path(spec).expanduser()
    if p.is_file():
        return p.parent.resolve()
    if p.is_dir():
        return p.resolve()
    dest = tmp / f"skill-{re.sub(r'[^A-Za-z0-9_.-]', '_', spec)}"
    dest.mkdir(parents=True, exist_ok=True)
    archive = subprocess.run(["git", "-C", str(REPO), "archive", spec, "skills/topic-graph"],
                             capture_output=True, check=False)
    if archive.returncode != 0:
        raise SystemExit(f"找不到 skill 版本 {spec!r}：不是目录、文件，也不是 git ref\n{archive.stderr.decode()}")
    subprocess.run(["tar", "-x", "-C", str(dest)], input=archive.stdout, check=True)
    return dest / "skills" / "topic-graph"


# ---------------------------------------------------------------- 专题目录

def materialize(case: dict, skill_dir: Path, ws: Path) -> Path:
    """在 ws 下准备好这个用例的专题目录，返回它（agent 的工作目录）。"""
    topic = ws / case["topic"]
    if case.get("empty"):
        topic.mkdir(parents=True)
        return topic
    shutil.copytree(FIXTURES / case["topic"], topic)
    today, shift = dt.date.today(), int(case.get("age_days", 0))
    for f in topic.rglob("*"):
        if f.is_file():
            text = f.read_text()
            new = DATE_RE.sub(lambda m: (today - dt.timedelta(days=int(m.group(1)) + shift)).isoformat(), text)
            if case.get("reset") and f.parent.parent.name == "nodes" and f.name != "_group.md":
                new = STATUS_RE.sub('status: "new"', new)
                new = re.sub(r"^verified:.*\n", "", new, flags=re.MULTILINE)
                new = new.split("\n---\n", 1)[0] + "\n---\n"   # 没学过的节点没有正文
            if new != text:
                f.write_text(new)
    if case.get("reset"):
        (topic / "log.jsonl").write_text("")
        (topic / "debts.md").write_text("# 待还\n")
    graph(skill_dir, topic, "sync")
    return topic


def graph(skill_dir: Path, topic: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["uv", "run", "--quiet", str(skill_dir / "scripts" / "graph.py"), *args],
                          cwd=topic, capture_output=True, text=True, timeout=120, check=False)


def statuses(topic: Path) -> dict[str, dict]:
    out = {}
    for f in topic.glob("nodes/*/*.md"):
        if f.name == "_group.md":
            continue
        text = f.read_text()
        head, _, body = text.partition("\n---\n") if text.startswith("---\n") else ("", "", text)
        field = lambda k: (re.search(rf'^{k}:\s*"?([^"\n]*)"?', head, re.MULTILINE) or [None, ""])[1]
        out[f.stem] = {"status": field("status"), "verified": field("verified"), "caveat": field("caveat"),
                       "body": body.strip()}
    return out


# ---------------------------------------------------------------- 行为检查

def run_check(name: str, start: Path, end: Path, commands: list[str], skill_dir: Path) -> bool:
    """start/end 是会话前后的专题目录快照；commands 是 agent 跑过的 Bash 命令。"""
    kind, _, arg = name.partition(":")
    s0, s1 = statuses(start), statuses(end)
    if kind == "graph_check":
        return (end / "topic.yaml").exists() and graph(skill_dir, end, "check").returncode == 0
    if kind == "ran":
        return ran(arg, commands)
    if kind == "not_ran":
        return not ran(arg, commands)
    if kind == "status_unchanged":
        return {k: v["status"] for k, v in s0.items()} == {k: v["status"] for k, v in s1.items() if k in s0}
    if kind == "status":
        nid, want = arg.split("=")
        return s1.get(nid, {}).get("status") == want
    if kind == "verified_today":
        return s1.get(arg, {}).get("verified", "")[:10] == dt.date.today().isoformat()
    if kind == "caveat":
        return bool(s1.get(arg, {}).get("caveat"))
    if kind == "body_changed":
        return bool(s1.get(arg, {}).get("body")) and s1[arg]["body"] != s0.get(arg, {}).get("body")
    if kind == "changed":
        a, b = start / arg, end / arg
        return b.exists() and (not a.exists() or a.read_text() != b.read_text())
    if kind == "unchanged":
        a, b = start / arg, end / arg
        return a.exists() == b.exists() and (not a.exists() or a.read_text() == b.read_text())
    if kind == "file":
        return (end / arg).exists()
    if kind == "no_file":
        return not (end / arg).exists()
    if kind.startswith("new_nodes>="):
        return len(set(s1) - set(s0)) >= int(kind.split(">=")[1])
    if kind == "nodes_between":
        lo, hi = map(int, arg.split("-"))
        return lo <= len(s1) <= hi
    raise ValueError(f"未知检查 {name}")


def ran(spec: str, commands: list[str]) -> bool:
    """spec 形如 "graph.py next"：某一段命令里出现了 graph.py（或 mise run graph、或代替它的 shell 变量），
    且子命令是 next。中间夹着 --root 之类的选项也算。"""
    sub = spec.split()[-1]
    for c in commands:
        for seg in re.split(r"&&|\|\||;|\|", c):
            words = seg.split()
            # 也认 `S=…/graph.py && uv run $S next` 这种把脚本路径放进变量的写法
            if any("graph.py" in w or w.startswith("$") for w in words) or "mise run graph" in seg:
                if sub in words:
                    return True
    return False


def checks_for(case: dict, snaps: list[Path], commands: list[list[str]], skill_dir: Path) -> dict:
    """检查默认针对最后一轮之后的状态；`@N:` 前缀表示第 N 轮之后。命令按截至那一轮累计。"""
    out = {}
    for name in case["checks"]:
        m = re.match(r"@(\d+):(.*)", name)
        turn, inner = (int(m.group(1)), m.group(2)) if m else (len(snaps) - 1, name)
        cmds = [c for t in commands[:turn] for c in t]
        out[name] = run_check(inner, snaps[0], snaps[turn], cmds, skill_dir)
    return out


# ---------------------------------------------------------------- agent 会话

def stream_events(stdout: str) -> list[dict]:
    events = []
    for line in stdout.splitlines():
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events


class Agent:
    """`claude -p` 的多轮 agent 会话。safe mode 关掉本机的 skill、CLAUDE.md/AGENTS.md、hook 和插件。"""

    def __init__(self, model: str, effort: str | None, system_file: Path, skill_dir: Path, cwd: Path):
        self.model, self.effort, self.system_file = model, effort, system_file
        self.skill_dir, self.cwd = skill_dir, cwd
        self.session = str(uuid.uuid4())
        self.turns = 0

    def send(self, message: str) -> dict:
        cmd = ["claude", "-p", "--safe-mode", "--model", self.model, "--output-format", "stream-json",
               "--verbose", "--tools", AGENT_TOOLS, "--allowedTools", AGENT_TOOLS,
               "--permission-mode", "dontAsk", "--add-dir", str(self.skill_dir),
               "--append-system-prompt-file", str(self.system_file)]
        cmd += ["--resume", self.session] if self.turns else ["--session-id", self.session]
        if self.effort:
            cmd += ["--effort", self.effort]
        t0 = time.time()
        proc = subprocess.run(cmd, input=message, capture_output=True, text=True, cwd=self.cwd,
                              timeout=1800, check=False)
        self.turns += 1
        events = stream_events(proc.stdout)
        result = next((e for e in reversed(events) if e.get("type") == "result"), None)
        if result is None:
            raise RuntimeError(f"claude -p 没有返回结果（exit {proc.returncode}）：{proc.stderr[-800:]}")
        if result.get("is_error") or result.get("subtype") != "success":
            raise RuntimeError(f"claude -p 出错：{result.get('subtype')} {str(result.get('result', ''))[:300]}")
        tools = [b for e in events if e.get("type") == "assistant"
                 for b in (e.get("message") or {}).get("content", []) if b.get("type") == "tool_use"]
        usage = result.get("usage") or {}
        return {
            "reply": result.get("result") or "",
            "tools": [{"name": b["name"], "input": b.get("input", {})} for b in tools],
            "cost_usd": result.get("total_cost_usd"),
            "input_tokens": sum(usage.get(k) or 0 for k in
                                ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")),
            "output_tokens": usage.get("output_tokens") or 0,
            "num_turns": result.get("num_turns"),
            "served": sorted((result.get("modelUsage") or {}).keys()),
            "seconds": round(time.time() - t0, 1),
        }


def bash_commands(turn: dict) -> list[str]:
    return [t["input"].get("command", "") for t in turn["tools"] if t["name"] == "Bash"]


def skill_reads(turns: list[dict], skill_dir: Path) -> list[str]:
    """agent 读了 skill 目录下的哪些 .md（Read 工具，或 Bash 里 cat/sed/head 之类）。"""
    names = set()
    pattern = re.compile(re.escape(str(skill_dir)) + r"/([\w-]+\.md)")
    for turn in turns:
        for t in turn["tools"]:
            text = t["input"].get("file_path", "") if t["name"] == "Read" else t["input"].get("command", "")
            if t["name"] in ("Read", "Bash"):
                names |= {m for m in pattern.findall(text) if m != "SKILL.md"}
    return sorted(names)


def diff(start: Path, end: Path) -> str:
    out = subprocess.run(["diff", "-ruN", "-x", "STATE.md", str(start), str(end)],
                         capture_output=True, text=True, check=False).stdout
    out = out.replace(str(start), "a").replace(str(end), "b")
    return out if len(out) <= 12000 else out[:12000] + "\n…（diff 太长，已截断）"


def render_record(case: dict, turns: list[dict], file_diff: str) -> str:
    """给裁判看的会话记录。"""
    parts = []
    for i, (msg, t) in enumerate(zip(case["turns"], turns), 1):
        cmds = "\n".join(f"$ {c}" for c in bash_commands(t)) or "（无）"
        parts.append(f"### 第 {i} 轮\n\n[学习者]\n{msg}\n\n[助手运行的命令]\n{cmds}\n\n[助手的回复]\n{t['reply']}")
    parts.append(f"### 会话结束时的文件改动（diff，不含生成的 STATE.md）\n\n```diff\n{file_diff or '（无改动）'}\n```")
    return "\n\n".join(parts)


def run_condition(args, case: dict, cond: str, rep: int, out_dir: Path) -> tuple[str, dict]:
    skill_dir = args.skill_dirs[cond]
    tmp = Path(tempfile.mkdtemp(prefix=f"tg-eval-{case['id']}-{cond}-"))
    ws = tmp / "ws"
    topic = materialize(case, skill_dir, ws)
    system_file = tmp / "system.md"
    system_file.write_text(system_prompt(skill_dir))
    snaps = [tmp / "snap0"]
    shutil.copytree(topic, snaps[0])
    agent = Agent(args.model, args.effort, system_file, skill_dir, topic)
    turns = []
    for i, msg in enumerate(case["turns"], 1):
        turns.append(agent.send(msg))
        snaps.append(tmp / f"snap{i}")
        shutil.copytree(topic, snaps[-1])
    record = render_record(case, turns, diff(snaps[0], snaps[-1]))
    record = record.replace(str(skill_dir), "<skill-dir>").replace(str(topic), "<topic>")
    name = f"{case['id']}__{cond}__r{rep}"
    (out_dir / "outputs" / f"{name}.md").write_text(record)
    (out_dir / "outputs" / f"{name}.turns.json").write_text(json.dumps(turns, ensure_ascii=False, indent=1))
    info = {
        "checks": checks_for(case, snaps, [bash_commands(t) for t in turns], skill_dir),
        "skill_reads": skill_reads(turns, skill_dir),
        "cost_usd": sum(t["cost_usd"] or 0 for t in turns) if all(t["cost_usd"] is not None for t in turns) else None,
        "input_tokens": sum(t["input_tokens"] for t in turns),
        "output_tokens": sum(t["output_tokens"] for t in turns),
        "tool_calls": sum(len(t["tools"]) for t in turns),
        "seconds": round(sum(t["seconds"] for t in turns), 1),
        "served": sorted({m for t in turns for m in t["served"]}),
    }
    if not args.keep:
        shutil.rmtree(tmp, ignore_errors=True)
    return record, info


def system_prompt(skill_dir: Path) -> str:
    return SYSTEM.format(skill_dir=skill_dir, workspace=(FIXTURES / "workspace.md").read_text().strip(),
                         skill=(skill_dir / "SKILL.md").read_text())


# ---------------------------------------------------------------- 盲评

JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "criteria": {"type": "array", "items": {
            "type": "object",
            "properties": {"id": {"type": "string"}, "winner": {"type": "string", "enum": ["A", "B", "tie", "na"]},
                           "reason": {"type": "string"}},
            "required": ["id", "winner", "reason"], "additionalProperties": False}},
        "overall": {"type": "string", "enum": ["A", "B", "tie"]},
        "overall_reason": {"type": "string"},
    },
    "required": ["criteria", "overall", "overall_reason"],
    "additionalProperties": False,
}

CRITERIA = ["frontier", "taught_only", "honest_record", "meaning", "learner_choice", "concise", "task"]


def judge_prompt(case: dict, a: str, b: str) -> str:
    learner = (FIXTURES / "workspace.md").read_text().split("## 学习者偏好", 1)[-1].strip()
    start = ("一个空目录，还没有专题。" if case.get("empty") else
             f"专题 `{case['topic']}`，开始时的状态（graph.py 生成的概览）：\n\n{case['_state']}")
    return f"""## 学习者
{learner}

## 会话开始时
{start}

## 这次会话应该达到的效果
{case['expect']}

## 记录 A
<记录A>
{a}
</记录A>

## 记录 B
<记录B>
{b}
</记录B>
"""


def call_judge(model: str, effort: str | None, prompt: str) -> dict:
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
        f.write((HERE / "judge.md").read_text())
    cmd = ["claude", "-p", "--safe-mode", "--tools", "", "--no-session-persistence",
           "--session-id", str(uuid.uuid4()), "--system-prompt-file", f.name, "--model", model, "--output-format", "json",
           "--json-schema", json.dumps(JUDGE_SCHEMA)]
    if effort:
        cmd += ["--effort", effort]
    proc = subprocess.run(cmd, input=prompt, capture_output=True, text=True,
                          cwd=tempfile.gettempdir(), timeout=900, check=False)
    Path(f.name).unlink(missing_ok=True)
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        raise RuntimeError(f"裁判没有返回 JSON（exit {proc.returncode}）：{proc.stderr[-800:] or proc.stdout[-800:]}")
    if data.get("is_error") or data.get("subtype") != "success":
        raise RuntimeError(f"裁判出错：{data.get('subtype')} {str(data.get('result', ''))[:300]}")
    return {"json": data.get("structured_output") or {}, "cost_usd": data.get("total_cost_usd"),
            "served": sorted((data.get("modelUsage") or {}).keys())}


def judge(args, case: dict, records: dict, rng: random.Random) -> dict:
    """正反两种顺序各判一次；同一项两次一致才算胜负，否则记平局。"""
    first_new_is_a = rng.random() < 0.5
    rounds = []
    for new_is_a in (first_new_is_a, not first_new_is_a):
        a, b = (records["new"], records["old"]) if new_is_a else (records["old"], records["new"])
        r = call_judge(args.judge_model, args.effort, judge_prompt(case, a, b))
        v = r["json"]

        def who(w, new_is_a=new_is_a):
            return {"A": "new" if new_is_a else "old", "B": "old" if new_is_a else "new"}.get(w, w)

        rounds.append({"new_is_a": new_is_a, "served": r["served"], "cost_usd": r["cost_usd"],
                       "criteria": {c["id"]: {"winner": who(c["winner"]), "reason": c["reason"]}
                                    for c in v.get("criteria", [])},
                       "overall": who(v.get("overall")), "overall_reason": v.get("overall_reason")})
    merged = {}
    for cid in CRITERIA + ["overall"]:
        w1, w2 = ((rounds[0]["overall"], rounds[1]["overall"]) if cid == "overall" else
                  (rounds[0]["criteria"].get(cid, {}).get("winner"), rounds[1]["criteria"].get(cid, {}).get("winner")))
        merged[cid] = ("missing" if w1 is None or w2 is None else w1 if w1 == w2
                       else "na" if "na" in (w1, w2) else "tie")
    return {"merged": merged, "rounds": rounds}


def run_one(args, case: dict, rep: int, out_dir: Path) -> dict:
    row = {"id": case["id"], "rep": rep, "case_hash": case["_hash"], "model": args.model,
           "judge_model": args.judge_model, "versions": {c: str(args.versions[c]) for c in CONDITIONS}}
    records = {}
    prev = args.prev_rows.get((case["id"], rep))
    for cond in CONDITIONS:
        if prev:
            records[cond] = (args.rejudge / "outputs" / f"{case['id']}__{cond}__r{rep}.md").read_text()
            row[cond] = prev[cond]
            row["model"], row["versions"] = prev["model"], prev["versions"]
        else:
            records[cond], row[cond] = run_condition(args, case, cond, rep, out_dir)
    row["judge"] = judge(args, case, records, random.Random(f"{case['id']}:{rep}"))
    return row


# ---------------------------------------------------------------- 汇总

def tally(values):
    return {k: sum(1 for v in values if v == k) for k in ("new", "old", "tie", "na", "missing")}


def mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def write_summary(rows: list[dict], errors: list[dict], out_dir: Path, args) -> str:
    lines = [f"# topic-graph eval：{out_dir.name}", "",
             (f"new = `{args.versions['new']}`，old = `{args.versions['old']}`。agent `{args.model}`，"
              f"裁判 `{args.judge_model}`。{len({r['id'] for r in rows})} 个用例 × {args.reps} 轮，"
              f"{len(rows)} 组成功，{len(errors)} 组出错。"), ""]

    lines += ["## 行为检查（脚本判定）", "", "| 版本 | 全部通过的会话 | 单项通过率 |", "|---|---|---|"]
    for cond in CONDITIONS:
        checks = [r[cond]["checks"] for r in rows]
        items = [v for c in checks for v in c.values()]
        lines.append(f"| {cond} | {sum(all(c.values()) for c in checks)}/{len(checks)} | "
                     f"{sum(items)}/{len(items) if items else '-'} |")

    lines += ["", "## 开销（每次会话的平均值）", "",
              "| 版本 | 费用 $ | 输入 token | 输出 token | 工具调用 | 秒 |", "|---|---|---|---|---|---|"]
    for cond in CONDITIONS:
        m = {k: mean([r[cond][k] for r in rows]) for k in ("cost_usd", "input_tokens", "output_tokens",
                                                             "tool_calls", "seconds")}
        fmt = lambda v, p=0: "-" if v is None else f"{v:,.{p}f}"
        lines.append(f"| {cond} | {fmt(m['cost_usd'], 3)} | {fmt(m['input_tokens'])} | {fmt(m['output_tokens'])} "
                     f"| {fmt(m['tool_calls'], 1)} | {fmt(m['seconds'])} |")
    lines += ["", "读过的参考文件（会话数）：" + "；".join(
        f"{cond}：" + (", ".join(f"{n} ×{sum(n in r[cond]['skill_reads'] for r in rows)}"
                                 for n in sorted({n for r in rows for n in r[cond]['skill_reads']})) or "无")
        for cond in CONDITIONS)]

    overall = tally([r["judge"]["merged"]["overall"] for r in rows])
    lines += ["", "## 盲评", "",
              f"总体：new 胜 {overall['new']}，old 胜 {overall['old']}，平局 {overall['tie']}（正反顺序不一致也记平局）。", "",
              "| 标准 | new | old | 平局 | 不适用 |", "|---|---|---|---|---|"]
    for cid in CRITERIA:
        t = tally([r["judge"]["merged"][cid] for r in rows])
        lines.append(f"| {cid} | {t['new']} | {t['old']} | {t['tie']} | {t['na'] + t['missing']} |")

    lines += ["", "## 逐个用例", "", "| 用例 | 轮 | 总体 | 检查 new | 检查 old | 未通过的检查 |", "|---|---|---|---|---|---|"]
    for r in sorted(rows, key=lambda r: (r["id"], r["rep"])):
        fails = "；".join(f"{c}: " + ", ".join(k for k, v in r[c]["checks"].items() if not v)
                         for c in CONDITIONS if not all(r[c]["checks"].values()))
        lines.append(f"| {r['id']} | {r['rep']} | {r['judge']['merged']['overall']} | "
                     + " | ".join(f"{sum(r[c]['checks'].values())}/{len(r[c]['checks'])}" for c in CONDITIONS)
                     + f" | {fails or '-'} |")
    if errors:
        lines += ["", "## 出错（未计入上面的统计）", ""] + [f"- {e['id']} r{e['rep']}：{e['error']}" for e in errors]
    lines += ["", "用例少，几组的胜负就能让比例大幅摆动；看逐个用例和 outputs/ 里的会话记录，比只看总数可靠。"]
    text = "\n".join(lines) + "\n"
    (out_dir / "summary.md").write_text(text)
    return text


# ---------------------------------------------------------------- 入口

def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--cases", nargs="*", type=Path, default=sorted(CASES_DIR.glob("*.jsonl")))
    p.add_argument("--only", help="逗号分隔的用例 ID")
    p.add_argument("--reps", type=int, default=1)
    p.add_argument("--model", default="opus", help="agent 用的模型（claude -p 的别名或模型 ID）")
    p.add_argument("--judge-model", default="sonnet", help="裁判模型；默认和 agent 不同，避免自己给自己打分")
    p.add_argument("--effort", help="low|medium|high|xhigh|max，不给就用默认值")
    p.add_argument("--jobs", type=int, default=2, help="并发的用例数；订阅有用量上限，不宜太大")
    p.add_argument("--out", type=Path, help="输出目录，默认 out/<时间>")
    p.add_argument("--skill", default=str(SKILL_DIR), help="new 一边的 skill：目录、SKILL.md 或 git ref；默认工作区版本")
    p.add_argument("--against", default="main", help="old 一边的 skill：目录、SKILL.md 或 git ref；默认 main")
    p.add_argument("--dry-run", action="store_true", help="只准备专题目录和提示词写到 out/，不调用模型")
    p.add_argument("--keep", action="store_true", help="保留每组的临时目录（调试用）")
    p.add_argument("--rejudge", type=Path, help="上次的输出目录：不重新跑 agent，只重新评审那些会话记录")
    args = p.parse_args()

    cases = load_cases(args.cases)
    if args.only:
        wanted = set(args.only.split(","))
        cases = [c for c in cases if c["id"] in wanted]
    if not cases:
        print("没有可跑的用例。", file=sys.stderr)
        return 1

    tmp = Path(tempfile.mkdtemp(prefix="tg-eval-skills-"))
    args.versions = {"new": args.skill, "old": args.against}
    args.skill_dirs = {}
    for c, v in args.versions.items():   # 两边都复制到随机命名的目录，路径里不留版本线索（裁判是盲评）
        dest = Path(tempfile.mkdtemp(prefix="sk-", dir=tmp)) / "topic-graph"
        shutil.copytree(resolve_skill(v, tmp), dest, ignore=shutil.ignore_patterns("tests", "__pycache__"))
        args.skill_dirs[c] = dest
    for case in cases:   # 给裁判看的开局状态
        if not case.get("empty"):
            ws = Path(tempfile.mkdtemp(prefix="tg-eval-state-"))
            topic = materialize(case, args.skill_dirs["new"], ws)
            case["_state"] = (topic / "STATE.md").read_text().strip()
            shutil.rmtree(ws, ignore_errors=True)

    out_dir = args.out or DEV / "out" / dt.datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    (out_dir / "outputs").mkdir(parents=True, exist_ok=True)

    if args.dry_run:
        pdir = out_dir / "prompts"
        pdir.mkdir(exist_ok=True)
        for cond in CONDITIONS:
            (pdir / f"system__{cond}.md").write_text(system_prompt(args.skill_dirs[cond]))
        for c in cases:
            ws = out_dir / "topics" / c["id"]
            materialize(c, args.skill_dirs["new"], ws)
            (pdir / f"{c['id']}__judge.md").write_text(judge_prompt(c, "（new 的会话记录）", "（old 的会话记录）"))
        print(f"{len(cases)} 个用例：提示词在 {pdir}，开局专题目录在 {out_dir / 'topics'}")
        return 0

    args.prev_rows = {}
    jobs = [(c, rep) for c in cases for rep in range(1, args.reps + 1)]
    if args.rejudge:
        prev = [json.loads(l) for l in (args.rejudge / "results.jsonl").read_text().splitlines() if l]
        args.prev_rows = {(r["id"], r["rep"]): r for r in prev}
        stale = sorted({r["id"] for r in prev for c in cases if c["id"] == r["id"] and r["case_hash"] != c["_hash"]})
        if stale:
            print(f"注意：这些用例在上次运行后改过，旧记录对应的是旧场景：{', '.join(stale)}", file=sys.stderr)
        jobs = [(c, rep) for c in cases for (i, rep) in sorted(args.prev_rows) if i == c["id"]]
        args.reps = max((rep for _, rep in jobs), default=1)

    rows, errors = [], []
    with ThreadPoolExecutor(max_workers=args.jobs) as pool, (out_dir / "results.jsonl").open("w") as fout:
        futures = {pool.submit(run_one, args, c, rep, out_dir): (c, rep) for c, rep in jobs}
        for fut in as_completed(futures):
            c, rep = futures[fut]
            try:
                row = fut.result()
            except Exception as e:  # noqa: BLE001  基础设施错误单独记，不当成哪一边输了
                errors.append({"id": c["id"], "rep": rep, "error": f"{type(e).__name__}: {e}"})
                print(f"✗ {c['id']} r{rep}: {e}", file=sys.stderr)
                continue
            rows.append(row)
            fout.write(json.dumps(row, ensure_ascii=False) + "\n")
            fout.flush()
            print(f"✓ {c['id']} r{rep}: 总体 {row['judge']['merged']['overall']}", file=sys.stderr)
    (out_dir / "errors.jsonl").write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in errors))
    shutil.rmtree(tmp, ignore_errors=True)
    print(write_summary(rows, errors, out_dir, args))
    return 0 if rows else 1


if __name__ == "__main__":
    sys.exit(main())
