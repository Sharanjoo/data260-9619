# AI Use Disclosure

## 1. What I used an AI assistant for and what I did myself

I used an AI assistant to turn the assignment into a checklist, draft the project structure and
code, and suggest repeatable tests and documentation. I supplied and verified my SID-based
configuration, reviewed the assigned domain and form fields, and I will personally run Docker,
Ollama, the 40-run experiment, AWS ECS, capture screenshots, inspect the measured results, and
approve the final report before submission.

## 2. One AI-produced output that was wrong or unsuitable

The first JavaScript draft called `form.checkValidity()` before the assignment-specific checks.
Because the textarea and checkbox also used native `required`/`minlength` validation, the browser
could stop at its own validation message before the required JavaScript alerts appeared.

## 3. How I detected or verified the problem

I traced the `validateForm` branches against the assignment and tested the order of the conditions.
An unchecked required checkbox caused `checkValidity()` to return false, making the later custom
terms alert unreachable; the same issue applied to a description shorter than 26 characters.

## 4. What I changed and why it works now

I moved the explicit description-length and terms checks before the general native-validity check.
Those two required failures now always show the assignment-specific alerts, while
`form.checkValidity()` still validates the remaining required text, email, and category fields.
