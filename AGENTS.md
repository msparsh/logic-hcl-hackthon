# Agent guidance

Build a small, working MVP that solves one real finance problem with AI. Keep the code simple, so every team member can explain it.

## Project
- Team Logic, HCLTech AI Engineer hackathon, 27 Oct 2026.
- Goal: a working MVP in this public repo. Judges check that data, backend and frontend connect, and may ask us to change code live.
- Use case: TBD (fill in after the design round).

## Rules
- `main` must always run. Build in small steps, test each one, then commit.
- Before each step, list what can go wrong (edge cases).
- Never make up data or results. Use a public dataset where possible.
- Keep code short and readable. Avoid extra libraries.

## Stack
Python, FastAPI (backend), Streamlit (frontend), pandas, scikit-learn or LightGBM, pytest. Runs on a laptop CPU.

## How it works
Data -> clean and check -> ML model gives a risk score -> top reasons for the score -> LLM writes a short case summary -> FastAPI -> Streamlit.

API (shapes defined in `app/schemas.py`):
- `GET /health` -> is the app, model and LLM ready
- `POST /score` -> risk score and top reasons for each transaction
- `GET /alerts` -> cases sorted by risk
- `POST /narrative/{case_id}` -> case summary, and whether the fallback was used

## Edge cases
- Bad input: missing columns, empty values, wrong types, duplicates, empty file.
- Backend down: show a clear error, not a crash.
- LLM fails: use a simple template summary instead.
- LLM gets only the case facts, and every number it writes must match them.

## Measuring results
Use PR-AUC and recall on the top alerts (not accuracy alone). Compare against a simple rule. Only report numbers our code produced.

## Safety and repo
- API keys only in `.env`, never committed. Share `.env.example`.
- Validate all input and show errors clearly.
- Work on branches; Pramith or Sparsh merges to `main`.
- Add a test for each feature and run it before merging.
- AI tools may help write code, but a team member reviews, tests and can explain every change.
