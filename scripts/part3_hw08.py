"""HW8 Part 3 - failure tests against the real Kafka broker (docker compose must be up; stop any hand-started agents).

For each failure the SAME test runs twice: 'before' (the protection switched off with an environment variable) and
'after' (the protection on). The driver starts the agents itself (fast mode, deterministic text, no model), sends
the messages, kills a Writer where the test needs it, then reads the topics to count what really happened.

   python scripts/part3_hw08.py duplicate        (I   duplicate delivery   -> idempotency)
   python scripts/part3_hw08.py kill             (II  consumer killed mid-work -> commit offset after success)
   python scripts/part3_hw08.py poison           (III poison message -> bounded retries + dead-letter topic)
   python scripts/part3_hw08.py ordering         (IV  two partitions, two Writers -> key by entity)
   python scripts/part3_hw08.py all              (all four; --variant before|after runs only one side)
Logs of every agent: reports/hw08/raw/part3_logs/<test>_<variant>/*.log   Evidence: reports/hw08/raw/part3_<test>.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "code"))

from kafka_agents.scenarios import order_violations, ordering_messages  # noqa: E402
from kafka_agents.settings import (DEAD_LETTER_TOPIC, DRAFTS_TOPIC, FINAL_TOPIC, INBOX_TOPIC, PLANNER_GROUP,  # noqa: E402
                                   REVIEWER_GROUP, TASKS_TOPIC, WRITER_GROUP)
from kafka_api.config import BOOTSTRAP_SERVERS, VERIFY_SEED  # noqa: E402

KAFKA_CONTAINER = "data260-hw8-kafka-s9619"
RAW = REPO / "reports" / "hw08" / "raw"
BANNER = "Sharan Lourduraj | SID4 9619 | DATA 260 HW8 Part 3 (failure tests, real Kafka)"
AGENT_DIR = REPO / "code" / "kafka_agents"


def say(text: str) -> None:
    print(f"{time.strftime('%H:%M:%S')} [DRIVER] {text}", flush=True)


def short(line: str, width: int = 230) -> str:
    return line if len(line) <= width else line[:width] + " ..."


# ----------------------------------------------------------------------------------------- agent processes
class Agent:
    def __init__(self, label: str, script: str, logdir: Path, env: Dict[str, str], args: Optional[List[str]] = None) -> None:
        self.label = label
        self.path = logdir / f"{label}.log"
        logdir.mkdir(parents=True, exist_ok=True)
        full = {**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8", "HW8_AGENT_MODE": "fast", **env}
        self.fh = open(self.path, "w", encoding="utf-8")
        self.proc = subprocess.Popen([sys.executable, "-u", str(AGENT_DIR / script), *(args or [])], stdout=self.fh,
                                     stderr=subprocess.STDOUT, env=full, cwd=str(REPO))

    def text(self) -> str:
        try:
            self.fh.flush()
        except ValueError:  # the file was closed when the process was killed
            pass
        return self.path.read_text(encoding="utf-8", errors="replace")

    def lines(self, *needles: str) -> List[str]:
        return [ln for ln in self.text().splitlines() if all(n in ln for n in needles)]

    def alive(self) -> bool:
        return self.proc.poll() is None

    def kill(self) -> None:  # abrupt, no clean shutdown: like kill -9
        if self.alive():
            self.proc.kill()
            self.proc.wait()
        self.fh.close()


async def wait_until(check, timeout: float, every: float = 0.5) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        if check():
            return True
        await asyncio.sleep(every)
    return check()


def assigned_partitions(agent: Agent) -> Optional[List[int]]:
    found = re.findall(r"partitions assigned: .*partitions=\[([0-9, ]*)\]", agent.text())
    if not found:
        return None
    return [int(x) for x in found[-1].replace(" ", "").split(",") if x]


# ----------------------------------------------------------------------------------------- Kafka helpers
def reset_groups() -> None:
    """Start every test from a clean point: each agent group is moved to the end of its topic.
    Agents that were killed stay in their group until the broker's session timeout (~10 s) expires, so a group
    that is still 'Stable' is retried for up to 90 s before giving up."""
    for group, topic in ((PLANNER_GROUP, INBOX_TOPIC), (WRITER_GROUP, TASKS_TOPIC), (REVIEWER_GROUP, DRAFTS_TOPIC)):
        deadline = time.time() + 90
        waited = False
        while True:
            res = subprocess.run(
                ["docker", "exec", KAFKA_CONTAINER, "/opt/kafka/bin/kafka-consumer-groups.sh", "--bootstrap-server",
                 "localhost:19092", "--group", group, "--topic", topic, "--reset-offsets", "--to-latest", "--execute"],
                capture_output=True, text=True, timeout=90)
            out = res.stdout + res.stderr
            if res.returncode == 0 and "Error" not in out:
                break
            if "inactive" in out and time.time() < deadline:
                if not waited:
                    say(f"group {group} still has members (a killed agent leaves after its session timeout); waiting")
                    waited = True
                time.sleep(4)
                continue
            raise SystemExit(f"could not reset group {group}: {out.strip()[:400]}\n"
                             f"Stop any agents you started by hand (Ctrl+C in their terminals) and run again.")
    say("agent consumer groups moved to the end of their topics (clean start)")


async def producer():
    from aiokafka import AIOKafkaProducer
    p = AIOKafkaProducer(bootstrap_servers=BOOTSTRAP_SERVERS)
    await p.start()
    return p


async def send(p: Any, topic: str, obj: Dict[str, Any], key: Optional[str] = None) -> Any:
    return await p.send_and_wait(topic, json.dumps(obj, separators=(",", ":")).encode(),
                                 key=key.encode() if key else None)


async def behind(consumer: Any, parts: List[Any], end: Dict[Any, int]) -> bool:
    for tp in parts:
        if await consumer.position(tp) < end[tp]:
            return True
    return False


async def read_topic(topic: str) -> List[Dict[str, Any]]:
    """Everything on the topic right now (fresh consumer, read from the beginning to the current end)."""
    from aiokafka import AIOKafkaConsumer
    c = AIOKafkaConsumer(topic, bootstrap_servers=BOOTSTRAP_SERVERS, group_id=f"s9619-driver-{uuid.uuid4().hex[:8]}",
                         auto_offset_reset="earliest", enable_auto_commit=False)
    await c.start()
    out: List[Dict[str, Any]] = []
    try:
        for _ in range(100):
            if c.assignment():
                break
            await asyncio.sleep(0.3)
        parts = list(c.assignment())
        end = await c.end_offsets(parts)
        deadline = time.time() + 30
        while time.time() < deadline and await behind(c, parts, end):
            for tp, msgs in (await c.getmany(timeout_ms=1000)).items():
                for m in msgs:
                    try:
                        body = json.loads(m.value.decode())
                    except ValueError:
                        body = {"raw": m.value.decode("utf-8", "replace")}
                    out.append({"partition": m.partition, "offset": m.offset, "key": m.key.decode() if m.key else None,
                                "timestamp": m.timestamp, "body": body})
    finally:
        await c.stop()
    return out


def mine(records: List[Dict[str, Any]], cids: set) -> List[Dict[str, Any]]:
    return [r for r in records if r["body"].get("correlation_id") in cids
            or r["body"].get("original") and any(c in r["body"]["original"] for c in cids)]


def start_agents(logdir: Path, env: Dict[str, str], writers: List[str], writer_env: Optional[Dict[str, str]] = None,
                 reviewer: bool = True) -> Dict[str, Agent]:
    agents = {"PLANNER": Agent("PLANNER", "planner.py", logdir, env)}
    for w in writers:
        agents[f"WRITER-{w}"] = Agent(f"WRITER-{w}", "writer.py", logdir, {**env, **(writer_env or {})}, ["--instance", w])
    if reviewer:
        agents["REVIEWER"] = Agent("REVIEWER", "reviewer.py", logdir, env)
    return agents


async def wait_ready(agents: Dict[str, Agent], timeout: float = 90) -> bool:
    ok = await wait_until(lambda: all(a.alive() and assigned_partitions(a) for a in agents.values()), timeout)
    for a in agents.values():
        if not a.alive():
            say(f"{a.label} stopped at start-up:\n{a.text()[-600:]}")
    if ok and len([a for a in agents.values() if a.label.startswith("WRITER")]) > 1:  # two Writers share the partitions
        ok = await wait_until(lambda: all(len(assigned_partitions(a) or []) == 1 for a in agents.values()
                                          if a.label.startswith("WRITER")), 60)
    return ok


def stop_all(agents: Dict[str, Agent]) -> None:
    for a in agents.values():
        a.kill()


def show(agent: Agent, label: str, *needles: str, limit: int = 6) -> List[str]:
    lines = agent.lines(*needles)[:limit]
    for ln in lines:
        say(f"  {label}| {short(ln)}")
    return lines


# ----------------------------------------------------------------------------------------- the four tests
async def test_duplicate(variant: str, logdir: Path) -> Dict[str, Any]:
    idem = "1" if variant == "after" else "0"
    say(f"I. DUPLICATE DELIVERY / {variant} (HW8_IDEMPOTENT={idem})")
    agents = start_agents(logdir, {"HW8_IDEMPOTENT": idem}, ["A"])
    p = await producer()
    try:
        if not await wait_ready(agents):
            return {"error": "agents did not start"}
        cid = str(uuid.uuid4())
        q = {"correlation_id": cid, "question": "What should I do with recalled frozen berries I already bought?",
             "entity_key": "dup-test"}
        await send(p, INBOX_TOPIC, q)
        say(f"sent the question, correlation_id={cid}")
        done = await wait_until(lambda: len(agents["REVIEWER"].lines("sent topic=s9619_final", cid)) >= 1, 60)
        await asyncio.sleep(1)
        await send(p, INBOX_TOPIC, q)
        say("REPLAYED the very same message (same correlation_id), as a broker redelivery would")
        await wait_until(lambda: len(agents["REVIEWER"].lines("sent topic=s9619_final", cid)) >= 2, 20)
        await asyncio.sleep(3)
        counts = {t: len(mine(await read_topic(t), {cid})) for t in (INBOX_TOPIC, TASKS_TOPIC, DRAFTS_TOPIC, FINAL_TOPIC)}
        say(f"messages with this correlation_id: {counts}")
        dup_lines = [ln for a in agents.values() for ln in a.lines("DUPLICATE", cid)]
        for ln in dup_lines[:3]:
            say(f"  log| {short(ln)}")
        if variant == "before":
            for ln in agents["WRITER-A"].lines("sent topic=s9619_drafts", cid)[:2]:
                say(f"  log| {short(ln)}")
        extra = counts[DRAFTS_TOPIC] + counts[FINAL_TOPIC] - 2
        ok = (counts[DRAFTS_TOPIC] == 1 and counts[FINAL_TOPIC] == 1 and bool(dup_lines)) if variant == "after" \
            else (counts[DRAFTS_TOPIC] >= 2 and counts[FINAL_TOPIC] >= 2)
        return {"correlation_id": cid, "first_answer_arrived": done, "counts": counts, "extra_side_effects": extra,
                "duplicate_log_lines": len(dup_lines), "as_expected": ok}
    finally:
        await p.stop()
        stop_all(agents)


async def test_kill(variant: str, logdir: Path) -> Dict[str, Any]:
    mode = "after" if variant == "after" else "before"
    say(f"II. CONSUMER KILLED MID-PROCESSING / {variant} (HW8_COMMIT_MODE={mode})")
    env = {"HW8_COMMIT_MODE": mode}
    agents = start_agents(logdir, env, ["A"], writer_env={"HW8_WRITE_DELAY_S": "10"})
    p = await producer()
    second = None
    try:
        if not await wait_ready(agents):
            return {"error": "agents did not start"}
        cid = str(uuid.uuid4())
        await send(p, INBOX_TOPIC, {"correlation_id": cid, "question": "What should I do with recalled spinach?",
                                    "entity_key": "kill-test"})
        say(f"sent the question, correlation_id={cid}")
        writer = agents["WRITER-A"]
        if not await wait_until(lambda: writer.lines("processing correlation_id=" + cid), 60):
            return {"error": "the Writer never received the task"}
        await asyncio.sleep(1.5)
        writer.kill()
        say("KILLED WRITER-A while it was still working on the task (no clean shutdown)")
        before_kill = len(mine(await read_topic(DRAFTS_TOPIC), {cid}))
        say(f"drafts for this correlation_id right after the kill: {before_kill}")
        second = Agent("WRITER-A_restarted", "writer.py", logdir, {**env, "HW8_AGENT_MODE": "fast",
                                                                    "HW8_WRITE_DELAY_S": "1"}, ["--instance", "A"])
        say("restarted the Writer (same group); the broker hands it the dead Writer's partition after the session "
            "timeout")
        wait = 90 if variant == "after" else 45
        got = await wait_until(lambda: second.lines("sent topic=s9619_drafts", cid), wait, every=1)
        await asyncio.sleep(2)
        drafts = len(mine(await read_topic(DRAFTS_TOPIC), {cid}))
        final = len(mine(await read_topic(FINAL_TOPIC), {cid}))
        say(f"after the restart: drafts={drafts} final={final}")
        for ln in writer.lines("received", cid)[:1] + second.lines("received", cid)[:1] + second.lines("sent topic", cid)[:1] \
                + writer.lines("committed BEFORE")[:1] + second.lines("offset committed")[:1]:
            say(f"  log| {short(ln)}")
        recovered = got and drafts == 1
        ok = recovered if variant == "after" else (not got and drafts == 0)
        return {"correlation_id": cid, "drafts_after_kill": before_kill, "restarted_writer_finished_it": bool(got),
                "drafts_after_restart": drafts, "final_after_restart": final,
                "outcome": "redelivered and completed after the restart" if recovered else "message lost",
                "as_expected": ok}
    finally:
        await p.stop()
        stop_all(agents)
        if second:
            second.kill()


async def test_poison(variant: str, logdir: Path) -> Dict[str, Any]:
    limit = "3" if variant == "after" else "0"
    say(f"III. POISON MESSAGE / {variant} (HW8_MAX_ATTEMPTS={limit}{' = retry forever' if limit == '0' else ''})")
    agents = start_agents(logdir, {"HW8_MAX_ATTEMPTS": limit, "HW8_RETRY_BACKOFF_S": "0.5"}, ["A"], reviewer=False)
    p = await producer()
    try:
        if not await wait_ready(agents):
            return {"error": "agents did not start"}
        bad, g1, g2 = (str(uuid.uuid4()) for _ in range(3))
        good_plan = {"steps": ["Identify the product", "Say what to do", "Point to the official notice"]}
        await send(p, TASKS_TOPIC, {"correlation_id": bad, "stage": "plan", "question": "poison",
                                    "plan": "THIS IS NOT A LIST OF STEPS", "entity_key": "poison-test"}, key="poison-test")
        await send(p, TASKS_TOPIC, {"correlation_id": g1, "stage": "plan", "question": "good message 1",
                                    "plan": good_plan, "entity_key": "poison-test"}, key="poison-test")
        await send(p, TASKS_TOPIC, {"correlation_id": g2, "stage": "plan", "question": "good message 2",
                                    "plan": good_plan, "entity_key": "poison-test"}, key="poison-test")
        say(f"sent 1 bad message (plan is not a list, correlation_id={bad}) followed by 2 good ones")
        writer = agents["WRITER-A"]
        if variant == "after":
            await wait_until(lambda: len(writer.lines("sent topic=s9619_drafts")) >= 2, 40)
        else:
            await wait_until(lambda: len(writer.lines("failed correlation_id=" + bad)) >= 20, 40)
            await asyncio.sleep(5)
        attempts = len(writer.lines("failed correlation_id=" + bad))
        dead = mine(await read_topic(DEAD_LETTER_TOPIC), {bad})
        drafts = mine(await read_topic(DRAFTS_TOPIC), {g1, g2})
        say(f"bad message: {attempts} failed attempts logged, dead-letter copies={len(dead)}; "
            f"good messages that reached drafts={len(drafts)} of 2")
        show(writer, "log", "failed correlation_id=" + bad, limit=3)
        show(writer, "log", "gave up", limit=1)
        show(writer, "log", "next message is not blocked", limit=1)
        show(writer, "log", "sent topic=s9619_drafts", limit=2)
        ok = (attempts == 3 and len(dead) == 1 and len(drafts) == 2) if variant == "after" \
            else (attempts >= 10 and len(dead) == 0 and len(drafts) == 0)
        return {"bad_correlation_id": bad, "failed_attempts_logged": attempts, "dead_letter_copies": len(dead),
                "dead_letter_error": dead[0]["body"].get("error") if dead else None,
                "good_messages_processed": len(drafts), "as_expected": ok}
    finally:
        await p.stop()
        stop_all(agents)


async def test_ordering(variant: str, logdir: Path) -> Dict[str, Any]:
    key_mode = "entity" if variant == "after" else "none"
    say(f"IV. ORDERING, 2 partitions + 2 Writers / {variant} (HW8_TASK_KEY={key_mode}; 20 messages from "
        f"VERIFY_SEED={VERIFY_SEED})")
    agents = start_agents(logdir, {"HW8_TASK_KEY": key_mode}, ["A", "B"], writer_env={"HW8_JITTER_S": "0.6"},
                          reviewer=False)
    p = await producer()
    try:
        if not await wait_ready(agents, 120):
            return {"error": "agents did not start / two Writers did not each get one partition"}
        say("WRITER-A partitions=%s WRITER-B partitions=%s" % (assigned_partitions(agents["WRITER-A"]),
                                                              assigned_partitions(agents["WRITER-B"])))
        msgs = ordering_messages(20, VERIFY_SEED, tag=variant + "-" + uuid.uuid4().hex[:6])
        cids = {m["correlation_id"] for m in msgs}
        for m in msgs:  # the client sends them in seq order; the Planner forwards each to s9619_tasks
            await send(p, INBOX_TOPIC, {k: m[k] for k in ("correlation_id", "question", "entity_key", "seq")})
        say("sent 20 related messages (several per recall notice) in seq order through the Planner")
        drafts: List[Dict[str, Any]] = []

        async def collect() -> bool:
            nonlocal drafts
            drafts = mine(await read_topic(DRAFTS_TOPIC), cids)
            return len(drafts) >= 20
        for _ in range(40):
            if await collect():
                break
            await asyncio.sleep(3)
        tasks = mine(await read_topic(TASKS_TOPIC), cids)
        by_entity: Dict[str, set] = {}
        for t in tasks:
            by_entity.setdefault(t["body"]["entity_key"], set()).add(t["partition"])
        order = order_violations([d["body"] for d in drafts])
        writers: Dict[str, int] = {}
        for d in drafts:
            writers[d["body"]["writer"]] = writers.get(d["body"]["writer"], 0) + 1
        say(f"processed={len(drafts)}/20  tasks per partition={ {p_: sum(1 for t in tasks if t['partition'] == p_) for p_ in (0, 1)} }"
            f"  drafts per Writer={writers}")
        for entity, parts in sorted(by_entity.items()):
            e = order["entities"].get(entity, {})
            say(f"  {entity:16} partitions={sorted(parts)}  finished order of seq={e.get('finished_order')} "
                f"out-of-order pairs={e.get('out_of_order_pairs')}")
        say(f"TOTAL out-of-order pairs for the same entity: {order['total_out_of_order_pairs']}")
        split = [e for e, ps in by_entity.items() if len(ps) > 1]
        ok = (order["total_out_of_order_pairs"] == 0 and not split and len(drafts) == 20) if variant == "after" \
            else (order["total_out_of_order_pairs"] > 0 and len(drafts) == 20)
        return {"messages": msgs, "processed": len(drafts), "partitions_per_entity": {k: sorted(v) for k, v in by_entity.items()},
                "entities_split_over_partitions": split, "drafts_per_writer": writers, "ordering": order,
                "task_partition_and_key": [{"seq": t["body"]["seq"], "entity": t["body"]["entity_key"],
                                           "partition": t["partition"], "offset": t["offset"], "key": t["key"]} for t in tasks],
                "finish_order": [{"seq": d["body"]["seq"], "entity": d["body"]["entity_key"],
                                  "writer": d["body"]["writer"]} for d in drafts],
                "as_expected": ok}
    finally:
        await p.stop()
        stop_all(agents)


TESTS = {"duplicate": test_duplicate, "kill": test_kill, "poison": test_poison, "ordering": test_ordering}


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("test", choices=[*TESTS, "all"])
    parser.add_argument("--variant", choices=["before", "after", "both"], default="both")
    args = parser.parse_args()
    print(BANNER, flush=True)
    names = list(TESTS) if args.test == "all" else [args.test]
    variants = ["before", "after"] if args.variant == "both" else [args.variant]
    summary = []
    for name in names:
        result: Dict[str, Any] = {"test": name, "variants": {}}
        for variant in variants:
            reset_groups()
            logdir = RAW / "part3_logs" / f"{name}_{variant}"
            res = await TESTS[name](variant, logdir)
            res["started_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            result["variants"][variant] = res
            summary.append((name, variant, res.get("as_expected"), res.get("error")))
            say(f"==> {name} / {variant}: " + ("matches what the protection should do" if res.get("as_expected")
                                              else f"DID NOT MATCH {res.get('error') or ''}"))
        RAW.mkdir(parents=True, exist_ok=True)
        (RAW / f"part3_{name}.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        say(f"saved {RAW / f'part3_{name}.json'}")
    print("\n=== summary ===")
    for name, variant, ok, err in summary:
        print(f"  {name:10} {variant:7} {'OK ' if ok else 'CHECK'} {err or ''}")
    return 0 if all(ok for _, _, ok, _ in summary) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
