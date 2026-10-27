# Agent guidance

Build a small, working hackathon MVP that demonstrates an end-to-end AI engineering capability relevant to an early-career AI Engineer role. Focus on one real user problem and a reliable, measurable workflow. Follow repository conventions, keep code straightforward, and avoid unnecessary dependencies.

The code should be explainable and traceable.

## Project context
- Team Logic, HCLTech AI Engineer (Elite Talent Program) hackathon, 27 Oct 2026. Rounds: design (about 1 h), implementation (about 4 h), evaluation.
- Deliverable: a working MVP in this public repo. Judges focus on connectivity (data, backend, frontend), may ask us to change code live, and ask each member what they built.
- Domain: finance. Likely use cases: real-time card payment fraud detection; AML alert prioritisation and false-positive reduction; automated investigation narratives and case summaries.
- Chosen use case: TBD (fill in after the design round).

## Working rules
- Protect a working MVP first. `main` must always run. Build one small step at a time, run tests after each step, and commit each working step.
- Before each step, list the edge cases and constraints it touches.
- Never invent data, metrics or results. Prefer public labelled datasets (for example ULB Credit Card Fraud, PaySim, IBM AML). If data must be generated, use documented, seeded, rule-based code; never ask an LLM to invent rows.
- Keep explanations and reports short and precise.

## Default stack
Python 3.11 with type hints, FastAPI + Uvicorn + Pydantic, Streamlit, pandas, scikit-learn, LightGBM, SHAP, SQLite or CSV, pytest, GitHub Actions. Laptops are CPU-only: use classic ML, train once early, and save the model with joblib.

## Architecture and API contract
Flow: data (CSV) -> validation and cleaning -> features -> ML model (class weights for imbalance) -> risk score and priority -> explanation (top features / SHAP) -> LLM narrative from structured facts only -> FastAPI -> Streamlit dashboard.

All request and response shapes live as Pydantic models in `app/schemas.py`. The frontend codes against this contract:
- `GET /health` -> status, model_loaded, llm_available
- `POST /score` -> input: list of transactions; output: id, risk_score, priority, top_reasons
- `GET /alerts?limit=N` -> ranked alert queue
- `POST /narrative/{case_id}` -> narrative, sources (facts used), latency_ms, fallback_used

Change the contract only with team agreement, and update schemas, tests and README in the same change. Streamlit calls the backend from Python using `API_URL` from `.env`.

## Edge cases to handle
- Missing columns, NaNs, wrong types, negative or zero amounts, duplicate IDs, empty file, very large file (cap rows).
- Extreme class imbalance. No data leakage: features must not use future information.
- Backend down: the UI shows a clear error, never a crash.
- LLM timeout or rate limit: return a template narrative and set fallback_used to true.
- The LLM receives only structured facts. Validate that every number and name in its output exists in those facts.

## Metrics
PR-AUC and recall at top-k (never accuracy alone), false-positive reduction against a simple rule baseline, latency per request, and narrative fact-check rate. Report only numbers produced by code in this repo.

## Repo and integration rules
- Secrets only in `.env`. Keep `.env` in `.gitignore` and ship `.env.example`. Never commit or log keys.
- Each person works on a branch. Pramith or Sparsh merges into `main`.
- `scripts/smoke_test.py` calls every endpoint with sample data and prints PASS/FAIL. Run it after every merge and every hour.
- GitHub Actions runs pytest and the smoke test on every push.
- Feature freeze 30 minutes before the end; then README, backup demo video and a fresh-clone test.
- AI assistants may draft code. A team member reviews, tests and can explain every change.

## Product and engineering
- Inspect relevant files and existing setup before changing the implementation.
- Deliver a runnable vertical slice: validated input or data, a clearly scoped AI capability, a usable result, and an interface or API appropriate to the project.
- Use modular, maintainable code and clean service boundaries. Keep model/provider configuration outside source code; handle missing credentials and service errors visibly.
- Include SQL, ETL, cloud, or streaming components only when they serve the chosen use case. Validate schemas and data quality, and handle PII deliberately.
- Validate inputs, handle expected errors, and never silently conceal failures.

## AI quality and responsible use
- State the task, model or service choice, and important assumptions. Use prompts and structured outputs that can be inspected and validated.
- Add proportionate guardrails, grounding or evidence where applicable, and a safe response for uncertain or invalid outputs. Keep human review for consequential decisions.
- Evaluate the core workflow with representative examples and relevant measures such as accuracy, relevance, groundedness, latency, or robustness. Record failure cases and limitations; avoid unsupported quality claims.
- Treat user input and external data as untrusted. Protect secrets, minimize sensitive data collection and retention, and do not log secrets or unnecessary personal data.

## Testing and delivery
- Add focused tests for changed behavior and run applicable checks. Report what ran and any failures; never claim an unrun check passed.
- Document the problem, setup, architecture, sample usage, evaluation approach and results, assumptions, and known limitations in the project's existing documentation.
- Keep changes focused and explain important decisions in user-facing language.
