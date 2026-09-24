# Homework 4 – Reproducible Run Instructions

## Prerequisites
- Python 3.11+, with a virtual environment activated
- Node.js 22.x / npm 10.x (for the `client/` React app)
- Docker Desktop (for MySQL + the FastAPI backend)
- [Ollama](https://ollama.com) running locally with `qwen3:8b` pulled (`ollama pull qwen3:8b`)

## 1. Install dependencies

```powershell
pip install -r requirements.txt
cd client
npm install
cd ..
```

## 2. Start MySQL + the FastAPI backend (Docker)

```powershell
docker compose up --build -d
docker compose ps
```

This starts two containers: `data260-hw4-mysql-s9619` (MySQL 8.0, host port `43306` mapped to
the container's `3306`) and the FastAPI backend on `http://localhost:8619` (which reaches MySQL
over the internal Docker network at `mysql:3306`).

## 3. Part 3: seed data, N+1 measurement, index

Any script run directly on the host (outside Docker) needs the **host-mapped** MySQL port:

```powershell
$env:MYSQL_HOST="127.0.0.1"
$env:MYSQL_PORT="43306"
$env:MYSQL_USER="hw4_user"
$env:MYSQL_PASSWORD="hw4_pass_9619"
$env:MYSQL_DB="s9619_rel"
```

Seed 200 `recall_source` rows and 5,000 `recall_record` rows (deterministic, `SEED = 9619`):

```powershell
python scripts\seed_hw04.py --reset
```

Measure the naive (N+1) vs. fixed (`joinedload`) endpoints — 180 requests total (3 page sizes x
2 versions x 30 requests), writing `reports/hw04/raw/n1_measurements.jsonl` and `n1_summary.csv`:

```powershell
python scripts\measure_n1.py
```

Add `idx_recall_record_product_name` and capture EXPLAIN before/after into
`reports/hw04/raw/explain_before_after.json`:

```powershell
python scripts\add_index_hw04.py
```

## 4. Part 1 + 2: React client (login / register / CRUD)

```powershell
cd client
npm run dev
```

Opens on `http://localhost:5174` (pinned — the backend's CORS config in `code/main.py` only
allows this exact origin). Register a new account, log in, then exercise the record list,
Create, Update, and Delete screens against the live MySQL-backed API.

## 5. Part 4: grounded RAG pipeline

Standalone — runs against `data/hw03_corpus`, does not need MySQL/Docker, but does need Ollama:

```powershell
ollama pull qwen3:8b
python code\rag.py
```

Answers all 6 fixed questions under 3 configurations (No-RAG / Basic-RAG / Context-engineered),
runs the k-sweep (k = 1, 3, 5) on Q2, and writes `reports/hw04/raw/rag_question_results.jsonl`,
`rag_k_sweep.json`, and `rag_eval_table.csv`.

## 6. Verification / smoke test

With the Docker backend still running (step 2) and the env vars from step 3 still set:

```powershell
python scripts\verify_hw04.py
```

Writes `reports/hw04/verification.json`, confirming: the backend responds on port 8619, login
issues a session cookie, unauthenticated requests are blocked, the fixed endpoint uses fewer SQL
statements than the naive one, the Part 3 seed/index/measurement data is all present, Ollama is
reachable, and all 6 Part 4 questions plus the k-sweep and eval table exist.

## 7. Shut down

```powershell
docker compose down
```
