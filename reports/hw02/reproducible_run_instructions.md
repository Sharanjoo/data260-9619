# Homework 2 – Reproducible Run Instructions

## Prerequisites
- Python 3.11+, with a virtual environment activated
- Docker Desktop (for the containerized web app)
- [Ollama](https://ollama.com) running locally with `qwen3:8b` pulled (`ollama pull qwen3:8b`)

## 1. Install dependencies

```powershell
pip install -r requirements.txt
pip install -r code\requirements.txt
```

## 2. Part 1 + 2 Web app (FastAPI backend + notices UI)

Run locally:

```powershell
python code\main.py
```

Or via Docker:

```powershell
docker compose up --build -d
docker compose ps
```

Visit `http://localhost:8619`. The list, create form, Update Notice (ID 1), Delete Highest-ID Notice, and Search all operate against the FastAPI backend on port 8619.

## 3. Part 3 Stateful LangGraph agent

Normal run:

```powershell
python code\agent_graph_demo.py --input-file reports\hw02\cases\schema_input.json --output-json reports\hw02\raw\agent_graph_demo_result.json
```

Self-correction loop test (forces the Reviewer to always reject, to observe the loop and the turn-ceiling cutoff):

```powershell
python code\agent_graph_demo.py --input-file reports\hw02\cases\schema_input.json --force-reviewer-issue --turn-ceiling 6
```

Schema-validation retry test (corrupts the first Planner response to trigger a real Pydantic validation failure and retry):

```powershell
python code\agent_graph_demo.py --input-file reports\hw02\cases\schema_input.json --force-planner-invalid-once
```

## 4. Part 4 Experiments

30-run schema classification (fixed input, turn ceiling = 10):

```powershell
python scripts\run_schema_experiment.py --runs 30 --turn-ceiling 10
```

Turn-ceiling comparison (2 vs 10, 20 runs each):

```powershell
python scripts\run_ceiling_comparison.py
```

Adversarial input (5 runs, turn ceiling = 2):

```powershell
python scripts\run_adversarial_experiment.py
```

All three scripts support `--resume` to continue after an interruption without losing completed runs.

## 5. Verification / smoke test

```powershell
python scripts\verify_hw02.py
```

or, via the Makefile:

```powershell
make verify-hw02
```

This writes `reports/hw02/verification.json`, confirming: the FastAPI backend responds on port 8619, the notices list and create/search round-trip work, and the LangGraph agent finishes and returns exactly 3 tags.