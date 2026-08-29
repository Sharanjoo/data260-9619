.PHONY: serve verify report agents client experiment docker-up docker-down

serve:
	python3 -m http.server 8619 --directory code/web_application

verify:
	python3 scripts/verify_hw01.py

report:
	python3 scripts/build_report.py

agents:
	python3 scripts/recorded_run.py -- python3 code/agents_demo.py --input-file reports/hw01/cases/nondeterminism_input.json --model qwen3:8b --temperature 0.0 --output-json reports/hw01/raw/agent_demo_result.json

client:
	python3 scripts/recorded_run.py -- python3 code/hw1_client.py --demo --model qwen3:8b --output-json reports/hw01/raw/client_token_counts.json

experiment:
	python3 scripts/run_nondeterminism.py --model qwen3:8b --resume

docker-up:
	docker compose up --build -d

docker-down:
	docker compose down
