# Homework 1 Reproducible Run Instructions

Run all commands from the repository root in Windows PowerShell.

## Verify prerequisites

```powershell
python --version
git --version
docker --version
docker compose version
ollama --version
aws --version
```

Python must be version 3.11 or 3.12. The model used for every Ollama run is `qwen3:8b`.

## Local Docker application

```powershell
docker compose up --build -d
docker compose ps
(Invoke-WebRequest -Uri http://localhost:8619 -UseBasicParsing).StatusCode
```

Open <http://localhost:8619>. Stop the container with `docker compose down` after collecting
local evidence.

## Planner, Reviewer, and Finalizer

```powershell
python scripts/recorded_run.py -- python code/agents_demo.py `
  --input-file reports/hw01/cases/nondeterminism_input.json `
  --model qwen3:8b `
  --temperature 0.0 `
  --output-json reports/hw01/raw/agent_demo_result.json
```

## Five-turn client

```powershell
python scripts/recorded_run.py -- python code/hw1_client.py `
  --demo --model qwen3:8b `
  --output-json reports/hw01/raw/client_token_counts.json
```

## Forty-run experiment

```powershell
python scripts/run_nondeterminism.py --model qwen3:8b --resume
```

## Verification

```powershell
python scripts/verify_hw01.py

Repository: <https://github.com/Sharanjoo/data260-9619>

Required collaborators: `Sbnikitha`, `supriyaselvanganesan`


