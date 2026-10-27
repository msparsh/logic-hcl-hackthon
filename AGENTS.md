# Agent guidance

Build a small, working MVP that solves one real finance problem with AI. Keep the code simple, so every team member can explain it.

## Project
- Goal: a working MVP. Judges check that data, backend and frontend connect, and may ask us to change code live. They will check everything.

## Rules
- `main` must always run. Build in small steps, test each one, then commit.
- Never make up data or results.
- Keep code readable and traceable.
- Add clear comments.

## Stack
Python, FastAPI (backend), Streamlit (frontend), pandas, scikit-learn or LightGBM, pytest, pytorch, tesnsorflow.

## How it works
Data -> clean and check -> ML model gives a risk score -> top reasons for the score -> LLM writes a short case summary -> FastAPI -> Streamlit.

## Edge cases
- Bad input: missing columns, empty values, wrong types, duplicates, empty file.
- Backend down: show a clear error, not a crash.
- LLM fails: use a simple template summary instead.
- LLM gets only the case facts, and every number it writes must match them.

## Measuring results
Use PR-AUC, recall@k and other metrics. Only report numbers our code produced.

## Safety and repo
- API keys only in `.env`, never committed. Share `.env.example`.
- Validate all input and show errors clearly.
