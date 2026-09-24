# TraceGuard

Agentic fraud investigation on TigerGraph. The agent starts from an uncertain alert, walks the graph, retrieves policy and closed-case notes, applies R1–R10 in code, and writes a defensible next action.

## What it does

1. Loads IEEE-CIS–based exam data into **FraudGraph** on TigerGraph Savanna.
2. Investigates the 20 `case_pack.csv` cases (risk score, customer report, analyst request).
3. Recommends policy actions with `auto` / `L1` / `L2` routes, initial vs final, and a SAR when required.
4. Writes each case back to the graph as `InvestigationCase`.
5. Serves an analyst page at `/` and `POST /investigate/{case_id}`.

Policy, exposure, approval routes, and JSON schema are deterministic Python. Graph hops are GSQL queries (`get_case_facts`, `investigate_txn`, `shared_cards_on_device`). GraphRAG retrieves policy text, known patterns, and closed-case notes. LangGraph runs facts → policy → retrieve → compose. MCP exposes those queries as tools (`python -m backend.mcp.server`).

## 20 exam answers

```
cases/HHG-001.json
…
cases/HHG-020.json
```

## Run locally

Python 3.10+. Use the project venv.

```powershell
pip install -r backend/requirements.txt
python -m pytest
python -m uvicorn backend.main:app --reload
```

Open http://127.0.0.1:8000 — select a case to open the saved answer, or Investigate to re-run the graph loop.

## TigerGraph

Schema, load jobs, and queries live in `tigergraph/`. Graph name: **FraudGraph**.

Installed investigation queries:

- `investigate_txn`
- `get_case_facts`
- `shared_cards_on_device`
- `get_investigation_case`

Copy `.env.example` to `.env` and set `TG_HOST` plus username/secret to point the agent at Savanna. Empty `TG_HOST` uses the same query names on `data/processed/` CSVs.

Do not commit dataset CSVs or `.env`. Do not use the original public Kaggle IEEE-CIS files.

## Layout

```
backend/          FastAPI, policy, composer, LangGraph, GraphRAG, MCP
tigergraph/       schema, load jobs, GSQL queries
cases/            20 scored answer files
frontend/         analyst UI
data/case_pack.csv
```
