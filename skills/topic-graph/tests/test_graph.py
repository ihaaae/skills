import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parent.parent / "scripts" / "graph.py"
spec = importlib.util.spec_from_file_location("graph", SCRIPT)
graph = importlib.util.module_from_spec(spec)
sys.modules["graph"] = graph
spec.loader.exec_module(graph)


def node(root, nid, title, prereqs=(), status="new", body="x"):
    d = root / "nodes" / nid[0]
    d.mkdir(parents=True, exist_ok=True)
    (d / "_group.md").write_text(f'---\ntitle: "{nid[0]} 组"\n---\n')
    (d / f"{nid}.md").write_text(
        f'---\nid: "{nid}"\ntitle: "{title}"\nprereqs: {json.dumps(list(prereqs))}\n'
        f'status: "{status}"\nupdated: 2026-01-01\n---\n{body}\n'
    )


@pytest.fixture
def topic(tmp_path):
    (tmp_path / "topic.yaml").write_text(
        'title: t\ntrack:\n  main: ["A"]\ngoal:\n  - id: G\n    title: g\n    targets: ["A3"]\n'
    )
    node(tmp_path, "A1", "a1", status="mastered")
    node(tmp_path, "A2", "a2", ["A1"])
    node(tmp_path, "A3", "a3", ["A2"])
    node(tmp_path, "B1", "b1", ["A1"])
    return tmp_path


def run(topic, *args):
    return subprocess.run([sys.executable, str(SCRIPT), "--root", str(topic), *args],
                          capture_output=True, text=True, check=False)


def test_frontier_and_derived(topic):
    g = graph.load(topic)
    assert set(g.frontier()) == {"A2", "B1"}
    assert g.derived("A3") == "locked"


def test_next_prefers_main_goal_path(topic):
    rows = graph.rank(graph.load(topic))
    assert [r["id"] for r in rows] == ["A2", "B1"]


def test_taught_with_ready_prereqs_is_retest_first(topic):
    node(topic, "B1", "b1", ["A1"], status="taught")
    rows = graph.rank(graph.load(topic))
    assert rows[0]["id"] == "B1" and rows[0]["kind"] == "retest"


def test_check_rejects_mastered_with_unmastered_prereq(topic):
    node(topic, "A3", "a3", ["A2"], status="mastered")
    r = run(topic, "check")
    assert r.returncode == 1 and "A3" in r.stdout


def test_cycle_detected(topic):
    node(topic, "A1", "a1", ["A3"])
    assert run(topic, "check").returncode == 1


def test_set_refuses_locked_mastery_and_updates(topic):
    assert run(topic, "set", "A3", "mastered").returncode == 1
    assert run(topic, "set", "A2", "mastered").returncode == 0
    assert 'status: "mastered"' in (topic / "nodes/A/A2.md").read_text()
    assert (topic / "log.jsonl").exists()


def test_preflight_refuses_locked(topic):
    assert run(topic, "preflight", "A3").returncode == 1
    assert run(topic, "preflight", "A2").returncode == 0


def test_add_rolls_back_on_unknown_prereq_and_creates_ok(topic):
    assert run(topic, "add", "A9", "--title", "x", "--prereq", "Z1").returncode != 0
    assert not (topic / "nodes/A/A9.md").exists()
    assert run(topic, "add", "A4", "--title", "x", "--prereq", "A3").returncode == 0


def test_add_into_fresh_topic_without_nodes_dir(tmp_path):
    (tmp_path / "topic.yaml").write_text('title: t\ntrack:\n  main: ["A"]\n')
    assert run(tmp_path, "add", "A1", "--title", "x", "--group-title", "A 组").returncode == 0
    assert (tmp_path / "nodes/A/A1.md").exists()


def test_retire_blocked_when_depended_on(topic):
    assert run(topic, "retire", "A2", "--into", "A1").returncode != 0


def test_forward_ref_warning_skips_boundary_lines_and_recorded_debts(topic):
    node(topic, "A1", "a1", status="mastered", body="用到 A3 的结论；`B1` 层、验收 B1-3 不算。\n未讲：B1。")
    out = run(topic, "check").stdout
    assert "A1: 摘要提到 A3" in out and "摘要提到 B1" not in out
    (topic / "debts.md").write_text("- **A1 → A3**：先当给定事实用。\n")
    assert "摘要提到" not in run(topic, "check").stdout


def test_goal_routes_chain_to_target(topic):
    g = graph.load(topic)
    routes = g.goal_routes("A1")
    assert [(goal["id"], chain) for goal, chain in routes] == [("G", ["A1", "A2", "A3"])]
    assert g.goal_routes("B1") == []


def test_preflight_prints_route_and_question(topic):
    (topic / "topic.yaml").write_text(
        'title: t\ntrack:\n  main: ["A"]\ngoal:\n  - id: G\n    title: g\n    targets: ["A3"]\n'
        '    question: "why?"\n'
    )
    out = run(topic, "preflight", "A2").stdout
    assert "A2 → A3" in out
    assert "终点要能回答：why?" in out


def test_set_mastered_writes_verified(topic):
    assert run(topic, "set", "A2", "mastered").returncode == 0
    g = graph.load(topic)
    assert g.nodes["A2"].verified == graph.dt.date.today().isoformat()
    run(topic, "set", "A2", "taught")
    assert "verified" not in (topic / "nodes/A/A2.md").read_text()


def test_review_due_old_mastered_with_dependents(topic):
    g = graph.load(topic)  # A1 mastered, updated 2026-01-01, A2/B1 depend on it
    due = g.review_due(graph.dt.date(2026, 2, 1))
    assert [r[0] for r in due] == ["A1"]
    assert g.review_due(graph.dt.date(2026, 1, 5)) == []


def test_retro_reasons(topic):
    log = [{"ts": "2026-01-01T10:00:00", "id": "A1", "from": "taught", "to": "mastered"},
           {"ts": "2026-01-02T10:00:00", "id": "A1", "from": "mastered", "to": "taught"},
           {"ts": "2026-01-02T11:00:00", "id": "A1", "from": "mastered", "to": "new"}]
    (topic / "log.jsonl").write_text("\n".join(json.dumps(e) for e in log) + "\n")
    g = graph.load(topic)
    why = g.retro_reasons(graph.dt.date(2026, 1, 20))
    assert any("18 天" in w for w in why)
    assert any("降级" in w for w in why)
    (topic / "retro.md").write_text("# retro\n\n## 2026-01-03\n- ok\n")
    g = graph.load(topic)
    assert g.retro_reasons(graph.dt.date(2026, 1, 4)) == []
