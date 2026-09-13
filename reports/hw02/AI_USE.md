# AI Use Disclosure

## 1. What I used an AI assistant for and what I did myself

I used an AI assistant to help build the structure of the assignment and the requirements. I personally implemented the web page styling, the FastAPI backend, the LangGraph agent, and the experiment scripts and ran every command, tested the app and the experiments, reviewed the results, and made every git commit. AI was also used for report structuring and organize text.

## 2. One AI-produced output that was wrong or unsuitable

The script that classified my 30 test runs used a formula based on `turn_count` to guess how many attempts the Planner took. That formula was wrong it couldn't tell a first-try success apart from a one-retry case.

## 3. How I detected or verified the problem

The script said all 30 runs needed a retry, with none succeeding on the first try. That didn't match two earlier manual runs, which both succeeded immediately. A result that never varies across 30 runs of an LLM looked wrong, so I flagged it.

## 4. What I changed and why it works now

I changed the script to directly count how many times the Planner actually ran, instead of guessing from `turn_count`. Re-running the experiment then correctly showed all 30 runs succeeding on the first try, matching the manual tests.