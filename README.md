# DATA 260 Homework 1 - SID4 9619

Homework 1 implementation for the **Grocery supply and recall notices** domain.

## Personal configuration

| Value | Result |
| --- | --- |
| SID4 | `9619` |
| PORT_BASE | `8619` |
| PREFIX | `s9619` |
| SEED | `9619` |
| VERIFY_SEED | `269619` |
| DOMAIN_ID | `3` |
| Hardware | HP Pavilion laptop, 32 GB RAM, 512 GB storage |
| Local model | `qwen3:8b` |

The configuration is calculated as follows:

- `PORT_BASE = 8000 + (9619 mod 900) = 8619`
- `DOMAIN_ID = 9619 mod 8 = 3`

## Repository contents

- `DOMAIN_SCHEMA.md` - entity fields and four category values, defined before the UI.
- `code/web_application/` - shared Part 1 HTML, CSS, and JavaScript application.
- `code/Dockerfile`, `compose.yaml` - local container and ECS-compatible image.
- `code/agents_demo.py` - Planner, Reviewer, and deterministic Finalizer pipeline.
- `src/model_client.py` - stable Ollama adapter used for every model call.
- `code/hw1_client.py` - interactive client and required five-turn demo.
- `scripts/run_nondeterminism.py` - resumable 20 + 20 run experiment.
- `scripts/verify_hw01.py` - writes `reports/hw01/verification.json`.
- `reports/hw01/` - report evidence, raw outputs, metrics, and AI-use disclosure.

Application code remains in the shared root-level `code/` and `src/` folders so later homework
can extend it. Homework-specific evidence belongs only under `reports/hwXX/`.

Repository: <https://github.com/Sharanjoo/data260-9619>

Required collaborators: `Sbnikitha`, `supriyaselvanganesan`

## 1. One-time Windows setup

Use **PowerShell as Administrator** for WSL setup:

```powershell
wsl --install
wsl --set-default-version 2
```

Install Docker Desktop with WSL 2 integration enabled. Install Python 3.11 or 3.12, Git,
Ollama, and AWS CLI. The commands below can be run from PowerShell in the repository root.

Verify the required commands:

```powershell
python --version
git --version
docker --version
docker compose version
ollama --version
aws --version
```

## 2. Local web application and Docker

Build and start the container:

```powershell
docker compose up --build -d
docker compose ps
(Invoke-WebRequest -Uri http://localhost:8619 -UseBasicParsing).StatusCode
```

Open <http://localhost:8619>, submit a valid notice, and open the browser developer console.
Capture these screenshots in `reports/hw01/screenshots/`:

1. `01_web_form.png` - completed form before submission.
2. `02_js_console.png` - JSON string, destructured values, updated object, and count.
3. `03_docker_localhost.png` - browser URL and running page.

Troubleshoot with:

```powershell
docker compose logs web
docker exec data260-hw1-s9619 wget -qO- http://127.0.0.1/
```

Stop it when finished:

```powershell
docker compose down
```

## 3. Ollama and agent runs

With 32 GB RAM, try the requested `qwen3:8b` model first:

```powershell
ollama pull qwen3:8b
ollama list
```

Ollama normally starts as a desktop service. If required, run `ollama serve` in a separate
terminal. Run the agent pipeline and record its real output:

```powershell
python scripts/recorded_run.py -- python code/agents_demo.py `
  --input-file reports/hw01/cases/nondeterminism_input.json `
  --model qwen3:8b `
  --temperature 0.0 `
  --output-json reports/hw01/raw/agent_demo_result.json
```

Capture `04_agents_console.png` showing Planner, Reviewer, Finalized, and Publish output.

Run the required five-turn client. It saves per-turn token counts and prints `/stats` after
turns 3 and 5:

```powershell
python scripts/recorded_run.py -- python code/hw1_client.py `
  --demo --model qwen3:8b `
  --output-json reports/hw01/raw/client_token_counts.json
```

Capture `05_client_stats_turn3.png` and `06_client_stats_turn5.png`.

Run the 40-run experiment. The checkpoint makes interruption recovery possible:

```powershell
python scripts/run_nondeterminism.py --model qwen3:8b --resume
```

This writes both JSON and CSV under `reports/hw01/raw/`, fills `METRICS.md`, and appends real
timestamps/results to `RUN_LOG.txt`. Capture `07_nondeterminism_complete.png` after completion.
Do not edit or regenerate the fixed input between runs.

If `qwen3:8b` cannot run acceptably on the laptop, use a smaller Ollama model that supports
structured JSON, rerun **all** agent experiments with that same model, and document the exact
model in README and the report. Never mix measurements from two models.

## 4. Self-check and report

Install the report-only dependency, run the self-check, and build the draft:

```powershell
python scripts/verify_hw01.py
```

The final report was created in Microsoft Word and exported as
reports/hw01/report.pdf. The PDF was reviewed to confirm that all required
code, answers, and evidence screenshots are present and readable.

## 5. Why conversation input tokens grow

Prior context is resent because the model does not retain hidden state between independent API
requests; earlier messages must be included again so the next response remains coherent. A system
prompt supplies high-priority behavior and constraints, while a user message supplies the current
request and has lower instruction priority. Input tokens grow because the serialized history adds
every prior user and assistant message to later requests. Growth is eventually limited by the
model's context window, application token limits, latency/cost limits, or deliberate trimming and
summarization.

## 6. AWS ECS deployment

Use the AWS Console steps in the supplied deployment guide. Suggested resource names are:

- ECR repository: `s9619-hw1-web`
- ECS cluster: `s9619-hw1-cluster`
- Task family: `s9619-hw1-task`
- Service: `s9619-hw1-service`
- Container: `s9619-hw1-web`, port `80`
- Desired task count: `1`

Build for ECS, authenticate to ECR, tag, and push (replace placeholders only in your terminal):

```bash
AWS_REGION=us-east-1
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_URI="$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/s9619-hw1-web"

aws ecr create-repository --repository-name s9619-hw1-web --region "$AWS_REGION"
aws ecr get-login-password --region "$AWS_REGION" | \
  docker login --username AWS --password-stdin \
  "$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com"
docker build --platform linux/amd64 -f code/Dockerfile -t s9619-hw1-web:latest code
docker tag s9619-hw1-web:latest "$ECR_URI:latest"
docker push "$ECR_URI:latest"
```

In ECS, use Fargate, Linux/X86_64, 0.25 vCPU, 0.5 GB RAM, assign a public IP, map container port
80, and allow inbound TCP/80 in the task security group. Capture:

1. `08_aws_ecs_service.png` - service with exactly one RUNNING task.
2. `09_aws_public_ip.png` - application loaded from the task's public IP.

Delete the service, cluster, ECR images/repository, and unused log group/security group after the
screenshot to stop charges.

## 7. Git history and submission

The GitHub repository is named exactly `data260-9619`. Its remote URL is:

```powershell
git remote set-url origin https://github.com/Sharanjoo/data260-9619.git
git remote -v
```

Before submission, confirm that GitHub users `Sbnikitha` and `supriyaselvanganesan` accepted their
collaborator invitations and can open the repository.

The project should be committed at genuine milestones (schema, web/Docker, agents, experiments,
final evidence). Do not fake commit dates. Before submission:

```powershell
git status
git add reports/hw01
git commit -m "docs: add verified Homework 1 evidence and report"
git tag -a hw1 -m "DATA 260 Homework 1"
git push origin main
git push origin hw1
git rev-parse hw1^{}
```

Submit the GitHub URL ending in `/tree/hw1` and the exact `reports/hw01/report.pdf` stored at that
tag.
