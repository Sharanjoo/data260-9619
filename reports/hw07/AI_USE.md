# HW7 AI Use

Sharan Lourduraj, SID4 9619 (DRAFT: review each answer and put it in your own words before submitting; every fact below comes from this build's logs.)

## 1. What did you use AI for, and what did you do yourself?

I used Claude (in the Claude desktop app) as a coding assistant for all six parts: it wrote the source files (JWT auth and role checks, the hand-written tool loop, the Reflexion verifier, the file tools and safety gate, the LangChain/LangGraph bike-share agent, the Streamlit page, the prompt-injection fixture and runner, and the verify script) and the offline test suites. I made the project decisions and ran everything myself: I chose the framework (LangGraph ReAct), the UI (Streamlit) and how to build the second bike scenario, ran every command in my own PowerShell against my own Docker stack and local Ollama model, kept the console output in RUN_LOG.txt, took the screenshots, committed and pushed myself, and decided which results go in the report. The local model (qwen3:8b) is what runs inside the agents.

## 2. Describe one thing the AI got wrong, or one thing you verified.

In Part 6 the model-driven safety-gate test (case 2) printed PASS even though the model never called the bash tool at all. The script treated "no command was allowed" as "every command was blocked", so the test passed without testing anything. A second example: the first Part 4 live runs of the bike agent gave confident answers with wrong dollar totals (for example $5,104.05 pay-per-use against an independent reference of $2,911.45), and in two scenario P runs it recommended the membership while its own totals showed pay-per-use was cheaper.

## 3. How did you detect or verify it?

For case 2, the screenshot of the run showed no bash call in the transcript while the verdict said PASS, so the verdict logic was corrected. For the bike agent, the runner compares every run to an independent reference calculation (src/bike_pricing.py) that the agent never sees, and prints PASS/FAIL per check, so the wrong totals were visible immediately rather than hidden behind a plausible-looking answer. I also kept every earlier attempt in RUN_LOG.txt and reports/hw07/PART4_NOTES.md instead of keeping only the best run.

## 4. What changed, and why does it work?

For case 2 the verdict is now PASS only if bash was actually called and every call was blocked; otherwise it prints NOT EXERCISED, and I re-ran it until the gate was really exercised (third attempt, all attempts disclosed). For the bike agent I fixed the causes I could find: the pricing tool now rebuilds the page's flattened plan table so the model reads the Month pass line instead of the $165 annual price; repeated identical tool calls now return a note with the next step; the prompt states the cost structure and that the decision must follow the lower total; and the results page flags a decision that contradicts the agent's own totals. This improved the runs (membership total exact in several runs, pay-per-use exact in P_run2 and P_run4) but did not make the 8B model reliable: the final runs still show a wrong pay-per-use total in scenario M and a wrong decision in scenario P, and I report them as they happened.
