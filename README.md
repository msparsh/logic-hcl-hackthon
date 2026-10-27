# Logic

Team Logic's project for the HCLTech AI Engineer Hackathon 2026: an **autonomous customer support agent** that turns chat requests (change address, cancel order, postpone delivery, track order) into safe, verified PostgreSQL updates. Every change is checked against business rules, shown to the customer for confirmation, and applied in a single transaction with a full audit trail.

How it works, part by part: [docs/PROJECT_GUIDE.md](docs/PROJECT_GUIDE.md) · Rules: [docs/BUSINESS_RULES.md](docs/BUSINESS_RULES.md) · Schema: [docs/DATABASE_SCHEMA.md](docs/DATABASE_SCHEMA.md)

## Team

- Kalabandi Pramith Joy
- Ganivada Lalith
- Sparsh Mishra
- Chitteti Vagdevi
- Banoth Arvind Nayak

## Quick start

```bash
python -m venv .venv
.venv\Scripts\activate            # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt

python scripts/create_instant_db.py   # free PostgreSQL, no signup; writes DATABASE_URL to .env
python scripts/init_db.py --reset --seed
python data/load_data.py               # optional: Kaggle CSVs in data/raw/ (not committed)
```

Optional: add `GEMINI_API_KEY` or `GROQ_API_KEY` to `.env`. With no key the agent uses a keyless provider and then a regex parser, so it always works. Check with `python scripts/check_llm.py`.

Run (two terminals):

```bash
uvicorn app.api:app --port 8000      # API, docs at http://127.0.0.1:8000/docs
streamlit run streamlit_app.py       # UI at http://localhost:8501
```

On Windows, `.\scripts\run_demo.ps1` starts both. Demo login: `alice@example.com` / `1234`. Every loaded customer also uses PIN `1234`.

Tests: `python -m pytest -q`. Database tests run when `TEST_DATABASE_URL` points to an empty test database.
