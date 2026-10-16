"""Build reports/hw06/METRICS.md and raw/part3_summary.json from the raw Part 2/3 data.

Reads (all written by the demo/sweep scripts, never edited by hand):
    reports/hw06/raw/part3_turns.csv, part3_probes.csv, part3_run_config.json, part2_chat_turns.json
    reports/hw06/memory_probes.yaml (rubric)

Usage (repo root):
    python scripts/build_metrics_hw06.py
"""
from __future__ import annotations

import csv
import json
import statistics
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "reports" / "hw06"
RAW = REPORT_DIR / "raw"

SETTINGS = ["N4", "N12", "N30", "POLICY"]
LABELS = {
    "N4": "SHORT_TERM_N=4",
    "N12": "SHORT_TERM_N=12",
    "N30": "SHORT_TERM_N=30",
    "POLICY": "SHORT_TERM_N=30 + compress_old_assistant",
}
PRICE_IN_PER_M = 1.00   # USD per 1M input tokens (HW6 brief)
PRICE_OUT_PER_M = 5.00  # USD per 1M output tokens (HW6 brief)
CONVERSATIONS = 10_000
QUALITY_TOLERANCE = 0.5  # "best" = cheapest setting whose quality is within this of the top quality


def read_csv(name: str) -> list[dict]:
    with (RAW / name).open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def mean(values: list[float]) -> float:
    return statistics.fmean(values) if values else 0.0


def summarise(turns: list[dict], probes: list[dict]) -> dict:
    out: dict = {}
    for s in SETTINGS:
        t = [r for r in turns if r["setting"] == s]
        p = [r for r in probes if r["setting"] == s]
        n = len(t)
        prompt = [int(r["prompt_tokens"]) for r in t]
        completion = [int(r["completion_tokens"]) for r in t]
        ov_p = [int(r["overhead_prompt_tokens"]) for r in t]
        ov_c = [int(r["overhead_completion_tokens"]) for r in t]
        total_in = sum(prompt) + sum(ov_p)
        total_out = sum(completion) + sum(ov_c)
        cost = total_in / 1e6 * PRICE_IN_PER_M + total_out / 1e6 * PRICE_OUT_PER_M
        out[s] = {
            "label": LABELS[s],
            "turns": n,
            "short_term_n": int(t[0]["short_term_n"]),
            "policy": t[0]["policy"],
            "mean_prompt_tokens": mean(prompt),
            "mean_completion_tokens": mean(completion),
            "mean_overhead_prompt_tokens": mean(ov_p),
            "mean_overhead_completion_tokens": mean(ov_c),
            "mean_reply_latency_ms": mean([float(r["reply_latency_ms"]) for r in t]),
            "mean_total_latency_ms": mean([float(r["latency_ms"]) for r in t]),
            "median_reply_latency_ms": statistics.median([float(r["reply_latency_ms"]) for r in t]),
            "mean_by_component": {
                "system_primer": mean([int(r["tok_system_primer"]) for r in t]),
                "long_term_summary": mean([int(r["tok_long_term_summary"]) for r in t]),
                "short_term_window": mean([int(r["tok_short_term_window"]) for r in t]),
                "episodic_facts": mean([int(r["tok_episodic_facts"]) for r in t]),
                "current_message": mean([int(r["tok_current_message"]) for r in t]),
            },
            "max_prompt_tokens": max(prompt),
            "conversation_input_tokens": total_in,
            "conversation_output_tokens": total_out,
            "conversation_cost_usd": cost,
            "mean_probe_score": mean([float(r["score"]) for r in p]),
            "probe_scores": {r["probe_id"]: int(r["score"]) for r in p},
            "probes_with_retrieved_facts": sum(1 for r in p if r["retrieved_facts"].strip()),
            "probe_prompt_tokens_mean": mean([int(r["prompt_tokens"]) for r in p]),
        }
    return out


def choose_best_worst(summary: dict) -> tuple[str, str, float]:
    top = max(v["mean_probe_score"] for v in summary.values())
    acceptable = [s for s, v in summary.items() if v["mean_probe_score"] >= top - QUALITY_TOLERANCE]
    best = min(acceptable, key=lambda s: summary[s]["conversation_cost_usd"])
    worst = max(summary, key=lambda s: summary[s]["conversation_cost_usd"])
    return best, worst, top


def fmt(value: float, digits: int = 0) -> str:
    return f"{value:,.{digits}f}"


def build_markdown(summary: dict, config: dict, probes_cfg: dict, part2: list[dict], probes: list[dict]) -> str:
    best, worst, top = choose_best_worst(summary)
    n30, pol = summary["N30"], summary["POLICY"]
    saving_pct = 100 * (1 - pol["mean_prompt_tokens"] / n30["mean_prompt_tokens"])
    saving_tokens = n30["mean_prompt_tokens"] - pol["mean_prompt_tokens"]
    quality_change = pol["mean_probe_score"] - n30["mean_probe_score"]
    lines: list[str] = []
    add = lines.append

    add("# HW6 METRICS - what memory costs\n")
    add("Student: Sharan Lourduraj (SID4 9619, PORT_BASE 8619, PREFIX s9619, SEED 9619, VERIFY_SEED 269619, DOMAIN_ID 3 - grocery recall notices).  ")
    add(f"Model: {config['chat_model']} via Ollama on CPU only (HP Pavilion, 32 GB RAM, no GPU); embeddings: {config['embed_model']}; MongoDB 7 database `s9619_doc`.  ")
    add(f"Memory settings during the sweep: summary every {config['summarize_every_user_msgs']} user messages, lifetime summary after {config['lifetime_every_session_summaries']} session summaries, "
        f"episodic top-k {config['episode_top_k']} with minimum cosine {config['episode_min_similarity']}. "
        f"Server source fingerprint {config['source_fingerprint']} (equals the repository fingerprint, so the running container matched the committed code).\n")

    add("## How the numbers were measured\n")
    add("- **Tokens** are Ollama's own counts for each `/api/chat` call: `prompt_tokens` = `prompt_eval_count`, `completion_tokens` = `eval_count` of the answer call. "
        "The memory machinery makes extra model calls (fact extraction every message, a session summary every 5 user messages, a lifetime summary occasionally); "
        "those are logged separately as *overhead* tokens and are included in the cost estimate but not in the prompt-size columns.")
    add("- **Tokens by component** (system primer / long-term summary / short-term window / episodic facts / current message) are character-count estimates (chars / 4) "
        "scaled so that the five parts add up to the real `prompt_tokens`. Ollama only reports a total, so the split is an estimate; the total is exact.")
    add("- **Latency**: `reply latency` is the time of the answering model call; `total latency` is the whole `/api/chat` request (answer + fact extraction + summaries + embeddings). "
        "The brief asks for mean latency, so the main table shows the total in ms and the reply-only value next to it.")
    add("- **Conversation**: the same 30 user messages (`conversation_30.yaml`) in a fresh user and session for each setting. A window of N counts stored *messages* (user and assistant), "
        "so N=30 holds the last 15 turns. The five probes were asked after message 30 in `read_only` mode (they are answered with memory but not stored, so they do not change the memory being tested).")
    add("- **Probe scoring** is rule based, from `memory_probes.yaml` (written before testing): 5 = every required fact present and no stale fact, 4 = required present but stale fact also mentioned, "
        "3 = at least half of the required facts, 2 = wrong but confident, 1 = says it does not know or only the stale fact.\n")

    add("## Part 2 - the 12-message memory demo\n")
    add("| Message | Prompt tokens | Completion tokens | Short-term messages | Episodic facts used | Summary updated | Total latency (s) |")
    add("|---:|---:|---:|---:|---:|:---:|---:|")
    for i, turn in enumerate(part2, start=1):
        m, used, ev = turn["metrics"], turn["memory_used"], turn["memory_events"]
        updated = "session" if ev["session_summary_updated"] else ""
        if ev["lifetime_summary_updated"]:
            updated += (" + " if updated else "") + "lifetime"
        add(f"| {i} | {m['prompt_tokens']} | {m['completion_tokens']} | {used['short_term']['count']} | {len(used['episodic'])} | {updated or '-'} | {m['latency_ms'] / 1000:.1f} |")
    add("\nPrompt size grows while the window fills (messages 1-7) and then levels off at about 600-650 tokens because the window is capped at 12 messages; the full conversation and the three memory collections are in the screenshots.\n")

    add("## Part 3 - SHORT_TERM_N sweep and the compression policy\n")
    add("### Main table (30 messages per setting, mean per message)\n")
    add("| Setting | Mean prompt tokens / turn | Mean latency (ms), total request | Mean reply latency (ms) | Probe quality (1-5) |")
    add("|---|---:|---:|---:|---:|")
    for s in SETTINGS:
        v = summary[s]
        add(f"| {v['label']} | {fmt(v['mean_prompt_tokens'], 1)} | {fmt(v['mean_total_latency_ms'])} | {fmt(v['mean_reply_latency_ms'])} | {v['mean_probe_score']:.1f} |")
    add("")
    add("Extra detail (not required by the brief):\n")
    add("| Setting | Mean completion tokens / turn | Mean overhead prompt tokens / turn | Mean overhead completion tokens / turn | Peak prompt tokens | Median reply latency (ms) |")
    add("|---|---:|---:|---:|---:|---:|")
    for s in SETTINGS:
        v = summary[s]
        add(f"| {v['label']} | {fmt(v['mean_completion_tokens'], 1)} | {fmt(v['mean_overhead_prompt_tokens'], 1)} | {fmt(v['mean_overhead_completion_tokens'], 1)} | {v['max_prompt_tokens']:,} | {fmt(v['median_reply_latency_ms'])} |")
    add("")
    add("### Where the prompt tokens go (mean per turn, estimated split scaled to the real total)\n")
    add("| Setting | System primer | Long-term summaries | Short-term window | Episodic facts | Current message | Total |")
    add("|---|---:|---:|---:|---:|---:|---:|")
    for s in SETTINGS:
        c = summary[s]["mean_by_component"]
        add(f"| {summary[s]['label']} | {c['system_primer']:.0f} | {c['long_term_summary']:.0f} | {c['short_term_window']:.0f} | {c['episodic_facts']:.0f} | {c['current_message']:.0f} | {summary[s]['mean_prompt_tokens']:.0f} |")
    add("\nThe primer and the current message are almost constant. The short-term window is the part that grows with N, and it is the only part the compression policy shrinks.\n")

    add("### Probe scores\n")
    questions = {p["id"]: p["question"] for p in probes_cfg["probes"]}
    add("| Probe | Question | " + " | ".join(summary[s]["label"].replace("SHORT_TERM_", "") for s in SETTINGS) + " |")
    add("|---|---|" + "---:|" * len(SETTINGS))
    for pid, q in questions.items():
        add(f"| {pid} | {q} | " + " | ".join(str(summary[s]["probe_scores"].get(pid, "-")) for s in SETTINGS) + " |")
    add("| **Mean** | | " + " | ".join(f"**{summary[s]['mean_probe_score']:.1f}**" for s in SETTINGS) + " |")
    add("")
    no_fact = {s: sorted(r["probe_id"] for r in probes if r["setting"] == s and not r["retrieved_facts"].strip()) for s in SETTINGS}
    add("Probe facts were planted so that the earliest ones (messages 1 and 2) fall outside every window, one only fits N=30, one fits N=12 and N=30, and one fits all. "
        "Every setting still answered all five correctly. The retrieved-fact column of `part3_probes.csv` shows where the answers could come from: "
        + "; ".join(f"{LABELS[s].replace('SHORT_TERM_', '')}: no episodic fact retrieved for {', '.join(no_fact[s]) or 'none'}" for s in SETTINGS)
        + ". Probes with a retrieved fact were answered from the episodic store; a probe without one can only have been answered from the session/lifetime summaries or the window.\n")

    add("### Compression policy (`compress_old_assistant`): token savings and quality change\n")
    add("Policy: keep the last 2 history messages verbatim, cut every older assistant reply to its first sentence (at most 120 characters); user messages are never touched. Window size stays 30.\n")
    add("| Comparison | N=30 without policy | N=30 with policy | Change |")
    add("|---|---:|---:|---:|")
    add(f"| Mean prompt tokens / turn | {fmt(n30['mean_prompt_tokens'], 1)} | {fmt(pol['mean_prompt_tokens'], 1)} | -{fmt(saving_tokens, 1)} tokens (-{saving_pct:.1f}%) |")
    add(f"| Mean short-term window tokens / turn | {fmt(n30['mean_by_component']['short_term_window'], 1)} | {fmt(pol['mean_by_component']['short_term_window'], 1)} | -{100 * (1 - pol['mean_by_component']['short_term_window'] / n30['mean_by_component']['short_term_window']):.1f}% |")
    add(f"| Mean probe quality | {n30['mean_probe_score']:.1f} | {pol['mean_probe_score']:.1f} | {quality_change:+.1f} |")
    add(f"| Mean total latency (ms) | {fmt(n30['mean_total_latency_ms'])} | {fmt(pol['mean_total_latency_ms'])} | {fmt(pol['mean_total_latency_ms'] - n30['mean_total_latency_ms'])} ms |")
    add(f"\nThe policy cut prompt size by about {saving_pct:.0f}% with no measurable change in probe quality on this conversation. "
        f"Compared with N=12 ({fmt(summary['N12']['mean_prompt_tokens'], 1)} tokens), the policy keeps a 30-message window at a similar token cost "
        f"({fmt(pol['mean_prompt_tokens'], 1)} tokens), because the dropped text is the long assistant replies, not the user's facts.\n")

    add("## Cost estimate: 10,000 conversations of 30 turns\n")
    add(f"Price: ${PRICE_IN_PER_M:.2f} per 1M input tokens, ${PRICE_OUT_PER_M:.2f} per 1M output tokens. Per conversation: input = sum over the 30 turns of (answer prompt tokens + overhead prompt tokens), "
        f"output = sum of (answer completion tokens + overhead completion tokens). The five evaluation probes are not counted because they are not part of normal use. "
        f"Total = per-conversation tokens x {CONVERSATIONS:,}. Nothing was run on a paid hosted model; the tokens are the real counts from the local model.\n")
    add("| Setting | Input tokens / conversation | Output tokens / conversation | Cost / conversation | Cost for 10,000 conversations | Probe quality | Role |")
    add("|---|---:|---:|---:|---:|---:|---|")
    for s in SETTINGS:
        v = summary[s]
        role = "**best**" if s == best else "**worst**" if s == worst else ""
        add(f"| {v['label']} | {v['conversation_input_tokens']:,} | {v['conversation_output_tokens']:,} | ${v['conversation_cost_usd']:.4f} | ${v['conversation_cost_usd'] * CONVERSATIONS:,.2f} | {v['mean_probe_score']:.1f} | {role} |")
    spread = summary[worst]["conversation_cost_usd"] - summary[best]["conversation_cost_usd"]
    add(f"\n**How best and worst were chosen.** Worst = the most expensive setting ({LABELS[worst]}). Best = the cheapest setting whose probe quality is within {QUALITY_TOLERANCE} points of the highest quality seen "
        f"({top:.1f}), so that cheapness cannot win by forgetting facts. Here every setting scored {top:.1f}, so best is simply the cheapest ({LABELS[best]}). "
        f"Choosing worst by cost alone is deliberate: it is the setting someone would pay for by default if they simply kept the longest history. "
        f"Best saves ${spread * CONVERSATIONS:,.2f} per 10,000 conversations (${spread:.4f} per conversation, {100 * spread / summary[worst]['conversation_cost_usd']:.1f}% of the worst).\n")
    overhead_share = {s: 100 * summary[s]["mean_overhead_prompt_tokens"] / (summary[s]["mean_prompt_tokens"] + summary[s]["mean_overhead_prompt_tokens"]) for s in SETTINGS}
    add(f"The memory overhead (extra extraction and summary calls) is about {summary['N12']['mean_overhead_prompt_tokens']:.0f} input tokens per turn in every setting, which is "
        f"{overhead_share['N4']:.0f}% of all input tokens at N=4 but {overhead_share['N30']:.0f}% at N=30; cheap windows therefore save less than the prompt-size column alone suggests.\n")

    add("## Interpretation and limits\n")
    add("- **Quality saturated.** All settings scored 5.0, so the probes cannot separate them. With episodic retrieval and summaries present, a window of 4 messages was enough for this 30-message conversation. "
        "This does not show that the window never matters: the probes are fact-recall questions, and a window-only agent (no summaries or episodes) was not tested here.")
    add("- **Cost scales with the window; quality did not.** Mean prompt size rose from "
        f"{fmt(summary['N4']['mean_prompt_tokens'])} to {fmt(summary['N12']['mean_prompt_tokens'])} to {fmt(summary['N30']['mean_prompt_tokens'])} tokens as N grew 4 -> 12 -> 30, and latency followed the same order for the answer call.")
    add("- **Latency is noisy.** The runs were CPU-only on a laptop, one after another, and other load on the machine was not controlled, so total latency differs between runs by more than prompt size explains "
        "(for example the policy run, with prompt sizes close to N=12, was faster than N=12). Prompt tokens are exact and repeatable; latency should be read as indicative only. "
        "Latency spikes every 5th turn come from the session-summary call.")
    add("- **One conversation per setting, temperature 0.** There is no repeat to give a confidence interval; the numbers describe this one 30-message conversation.")
    add("- The rule-based scorer checks facts, not tone; the replies are stored in `part3_probes.csv` and were also read by hand.\n")

    add("## Raw files\n")
    add("`reports/hw06/raw/part3_turns.csv` (120 rows, one per message), `part3_probes.csv` (20 rows), `part3_probe_scores.json`, `part3_run_config.json`, `part3_summary.json` (all numbers above), "
        "`part2_chat_turns.json`, `part2_memory.json`, `part2_aggregate.json`; console output of the runs is in `reports/hw06/RUN_LOG.txt` "
        "(it also contains earlier aborted attempts: a first N=4 run that failed because the container held an outdated image, and a start-up timing failure; "
        "and the last N=30 run, which crashed on printing an emoji after storing its result and was resumed).\n")
    return "\n".join(lines) + "\n"


def main() -> int:
    turns = read_csv("part3_turns.csv")
    probes = read_csv("part3_probes.csv")
    config = json.loads((RAW / "part3_run_config.json").read_text(encoding="utf-8"))
    probes_cfg = yaml.safe_load((REPORT_DIR / "memory_probes.yaml").read_text(encoding="utf-8"))
    part2 = json.loads((RAW / "part2_chat_turns.json").read_text(encoding="utf-8"))
    summary = summarise(turns, probes)
    best, worst, top = choose_best_worst(summary)
    payload = {
        "price_per_million": {"input": PRICE_IN_PER_M, "output": PRICE_OUT_PER_M},
        "conversations": CONVERSATIONS,
        "quality_tolerance": QUALITY_TOLERANCE,
        "best_setting": best,
        "worst_setting": worst,
        "settings": summary,
        "cost_10000_conversations_usd": {s: round(v["conversation_cost_usd"] * CONVERSATIONS, 2) for s, v in summary.items()},
    }
    (RAW / "part3_summary.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    (REPORT_DIR / "METRICS.md").write_text(build_markdown(summary, config, probes_cfg, part2, probes), encoding="utf-8")
    print("Wrote reports/hw06/METRICS.md and reports/hw06/raw/part3_summary.json")
    for s in SETTINGS:
        v = summary[s]
        print(f"{v['label']:<45} prompt={v['mean_prompt_tokens']:7.1f}  latency={v['mean_total_latency_ms']:8.0f} ms  quality={v['mean_probe_score']:.1f}  "
              f"cost/10k=${v['conversation_cost_usd'] * CONVERSATIONS:,.2f}")
    print(f"best={best} worst={worst}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
