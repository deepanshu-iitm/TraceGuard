# TraceGuard

TraceGuard is a graph-native fraud investigation platform. It takes an uncertain payment alert, walks the transaction graph, retrieves policy and closed-case notes, applies a coded fraud policy, and returns a defensible verdict with next actions.

The system is investigation, not classification. A risk score, customer report, or analyst request opens a case. The agent then gathers neighborhood facts, reconstructs the spending episode, compares the pattern to prior closed cases, and writes the outcome back onto the graph.

Verdict, fraud probability, policy actions, and approval routes are produced in Python. Language models, when configured, select graph tools and rewrite analyst-facing narrative. They do not change the decision.

## Capabilities

- Investigate a case pack of twenty inbound alerts (`HHG-001` … `HHG-020`) from graph facts, policy rules R1–R10, and retrieved notes.
- Recommend next-best actions with `auto`, `L1`, or `L2` approval routes, including an initial recommendation and a final recommendation after assumed evidence.
- File a SAR block when policy requires `FILE_REPORT`.
- Persist each closed investigation as an `InvestigationCase` vertex with `CASE_*` edges.
- Serve a Next.js analyst console: case list, verdict, neighborhood, timeline, policy trace, conflicts, approval queue, evidence, and SAR.
- Rank additional high-risk transactions and produce optional monitoring investigations (`MON-001` …).
- Expose the same installed GSQL queries through FastAPI, LangGraph, and MCP.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  Analyst console (Next.js, :3000)                               │
│  cases · neighborhood · timeline · policy · approvals · SAR     │
└──────────────────────────────┬──────────────────────────────────┘
                               │ rewrites
┌──────────────────────────────▼──────────────────────────────────┐
│  FastAPI (uvicorn, :8000)                                       │
│  /cases  /investigate  /graph  /monitoring  /stats  /health     │
└──────────────────────────────┬──────────────────────────────────┘
                               │
        ┌──────────────────────┼──────────────────────┐
        ▼                      ▼                      ▼
┌───────────────┐    ┌─────────────────┐    ┌────────────────────┐
│ LangGraph     │    │ Policy engine   │    │ Graph tools        │
│ facts →       │───▶│ R1–R10          │    │ tigergraph-mcp or  │
│ policy →      │    │ stopping rules  │    │ local GSQL twins   │
│ retrieve →    │    │ auto / L1 / L2  │    └─────────┬──────────┘
│ compose →     │    └─────────────────┘              │
│ explain →     │    ┌─────────────────┐              ▼
│ persist       │───▶│ GraphRAG        │    ┌────────────────────┐
└───────────────┘    │ rag_search      │───▶│ FraudGraph         │
                     │ RagDocument     │    │ TigerGraph Savanna │
                     └─────────────────┘    └────────────────────┘
```

### Runtime layers

| Layer | Responsibility |
| --- | --- |
| **Console** | `frontend/` is a Next.js 15 App Router console. It calls the API through Next rewrites (`TRACEGUARD_API`, default `http://127.0.0.1:8000`). |
| **HTTP API** | FastAPI in `backend/main.py`. Lists cases, returns saved answers, runs live investigations, and serves neighborhood views. |
| **Agent** | LangGraph state machine in `backend/investigate/agent.py`. One compiled graph: facts, policy, retrieve, compose, explain, persist. |
| **Policy** | Deterministic rules in `backend/policy/`. Action names, approval routes, and stop conditions are code, not prompts. |
| **Analysis** | Pattern detection, episode reconstruction, exposure, and calibrated probability in `backend/investigate/analysis.py`. |
| **Graph** | Installed GSQL on graph **FraudGraph**. Live calls go through official `tigergraph-mcp` tools. Empty `TG_HOST` uses the same query names on exported CSVs. |
| **GraphRAG** | `RagDocument` vertices with a 32-dimension cosine `embedding`. `rag_search` ranks policy, pattern, closed-case, and regulatory notes for the current neighborhood. |
| **MCP** | `python -m backend.mcp.server` exposes investigation tools. `python -m backend.mcp.official` starts the vendor TigerGraph MCP server against `.env`. |

### Decision boundary

| Produced in Python | Optional language model |
| --- | --- |
| Verdict, status, pattern | Graph-tool selection from the offered neighborhood |
| Fraud probability and exposure | Analyst summary (2–4 sentences) |
| Policy actions and routes | SAR narrative, using the same subjects, amount, and dates |
| Evidence claims with query refs | Embeddings for GraphRAG (`text-embedding-3-small`, projected to 32 dimensions) |
| Stop reason | |

If `OPENAI_API_KEY` is empty, embeddings fall back to hashed tokens, tool selection uses the neighborhood heuristic, and the composer’s Python summary and SAR text are kept.

## Graph data model

Schema lives in `tigergraph/schema/schema.gsql`. The graph name is **FraudGraph**.

### Vertices

| Type | Role |
| --- | --- |
| `Customer` | Account holder. |
| `PaymentCard` | Instrument (`card1`, network, card type). |
| `CardTransaction` | Payment event (time, amount, channel, product, risk score, billing). |
| `DeviceProfile` | Device fingerprint used on a transaction. |
| `EmailDomain` | Purchaser or recipient email. |
| `BillingRegion` | Billing region and country. |
| `ClosedCase` | Historical investigation (outcome, pattern, notes, exposure). |
| `InvestigationCase` | TraceGuard’s written outcome for a live case. |
| `RagDocument` | Retrievable note with vector attribute `embedding`. |

### Edges

| Edge | From → To | Use |
| --- | --- | --- |
| `OWNS` | Customer → PaymentCard | Card ownership. |
| `MADE` | PaymentCard → CardTransaction | Spend. |
| `FROM_DEVICE` | CardTransaction → DeviceProfile | Device used. |
| `PURCHASER_EMAIL` / `RECIPIENT_EMAIL` | CardTransaction → EmailDomain | Email linkage. |
| `BILLED_IN` | CardTransaction → BillingRegion | Billing location. |
| `NEXT` | CardTransaction → CardTransaction | Temporal episode chain. |
| `INVOLVES` / `ON_CARD` / `CONNECTED_TO` | ClosedCase → transaction or card | Prior case linkage. |
| `CASE_FOR_CUSTOMER` | InvestigationCase → Customer | Written case. |
| `CASE_INVOLVES` | InvestigationCase → CardTransaction | Flagged and affected spend. |
| `CASE_ON_CARD` / `CASE_CONNECTED_TO` | InvestigationCase → PaymentCard | Primary and linked cards. |
| `CASE_MATCHES` | InvestigationCase → ClosedCase | Similar prior cases. |

## Installed GSQL

Queries are in `tigergraph/queries/`. The agent chooses among them from the neighborhood (device, email, region present or not). It does not run a fixed three-hop path.

| Query | Input | What it returns |
| --- | --- | --- |
| `investigate_txn` | `CardTransaction` | Amount, time, channel, card, customer, closed cases on the card, history count. |
| `get_case_facts` | `CardTransaction` | Full neighborhood: card, customer, history, device, emails, closed cases. |
| `next_chain` | `CardTransaction` | Forward and backward `NEXT` neighbors for episode reconstruction. |
| `card_component` | `PaymentCard` | Two-hop component: devices, emails, cards reached through shared devices. |
| `shared_cards_on_device` | `DeviceProfile` | Other payment cards on the same device (shared origin). |
| `device_fanout` | `DeviceProfile` | Cards reached by expanding `FROM_DEVICE` neighbors. |
| `device_degree` | `DeviceProfile` | Transaction count and unique cards on the device. |
| `email_fanout` | `EmailDomain` | Cards that share a purchaser or recipient email. |
| `region_fanout` | `BillingRegion` | Cards billed in the same region (context; not automatic shared origin). |
| `rag_search` | query vector, `k` | Top-k `RagDocument` hits by cosine distance. |
| `get_investigation_case` | `InvestigationCase` | Persisted case vertex and its `CASE_*` links. |

Loading jobs are in `tigergraph/loading/`. Vector schema is in `tigergraph/schema/add_rag_vectors.gsql`.

Live graph calls use official tigergraph-mcp names:

- `tigergraph__run_query`
- `tigergraph__run_installed_query`
- `tigergraph__search_top_k_similarity`

`backend/mcp/client.py` wraps those async tools with a persistent event loop, maps vertex parameters, and parses the MCP JSON payload. `backend/graph/tools.py` is the single switch: TigerGraph when `TG_HOST` is set, otherwise `LocalGraphTools` on `data/processed/` CSVs with the same query names.

## Investigation agent

`investigate(case_id)` compiles one LangGraph:

```
START → facts → policy → retrieve → compose → explain → persist → END
```

### 1. Facts

Load the case-pack item and the flagged transaction. On a live graph, run `get_case_facts` / `investigate_txn`, then neighborhood algorithms:

- Always candidates: `next_chain`, `card_component`.
- If a device exists: `shared_cards_on_device`, `device_fanout`, `device_degree`.
- If an email exists: `email_fanout`.
- If a billing region exists: `region_fanout`.

With an API key, the model may reorder that offered list. `get_case_facts` and `investigate_txn` are always kept. Tool results merge extra cards and `NEXT` transactions into `CaseFacts`.

### 2. Policy

`decide_investigation` in `backend/investigate/compose.py` derives a `PolicySnapshot` from graph analysis, then `recommend_actions` in `backend/policy/rules.py` emits actions. A second pass may assume a customer or step-up response and produce **final** actions. `what_changed` records the difference.

### 3. Retrieve

`retrieve_documents` ranks notes for the detected pattern. On a live graph this is `rag_search` over `RagDocument`. Offline it is TF-IDF over the same corpus: policy ids allowed for the pattern, named pattern documents, closed-case notes, and regulatory text. Citations are stored as `Evidence` with `source` and `ref` (for example `query:rag_search(...)`).

### 4. Compose

Build the answer JSON: verdict, probability, pattern, affected transactions, exposure, evidence list, similar prior cases, initial/final actions, SAR, stop reason, tool-call count.

### 5. Explain

If an API key is set, rewrite `summary` and, when a SAR is filed, `sar.narrative`. Verdict, pattern, probability, actions, subjects, amount, and dates are not allowed to change.

### 6. Persist

Upsert `InvestigationCase` and `CASE_*` edges through MCP `add_nodes` / `add_edge` (or the local CSV export). The answer records `written_to_graph` and `graph_case_id`.

## Analysis

`backend/investigate/analysis.py` is deterministic.

**Patterns** (`FraudPattern`): `card_testing`, `card_not_present_fraud`, `card_not_present_new_device`, `out_of_region_use`, `account_takeover`, `undocumented`, `none`.

Signals used in detection include:

- Rapid low-value online authorizations followed by a larger purchase (card testing).
- Card-not-present spend, optionally on a device not seen in prior history.
- Account-takeover style shifts in device and spend.
- Shared origin: a specific device used by more than one card, or a tight email cluster. High-volume mail domains are not treated as shared origin. A common billing region is context, not automatic shared origin.
- Coordinated undocumented structure when the graph shows multi-card coordination that does not match a named pattern.
- Known-spend checks against prior amounts on the same channel or region.

**Episode.** `NEXT` edges plus time/amount clustering define affected transaction ids and exposure. Legitimate cases have an empty affected list and zero exposure.

**Probability.** A calibrated score in `[0, 1]` from pattern, known spend, closed-case history, and conflicting evidence. It is an investigation output, not a classifier label. Risk score on the inbound alert is a trigger, not the verdict.

**Conflicts.** Evidence is split into claims that support fraud and claims that support legitimate, so the console can show both sides.

## Policy engine

Rules R1–R10 live in `backend/policy/rules.py`. Approval routes live in `backend/policy/permissions.py`. Stopping lives in `backend/policy/stopping.py`.

### Actions

`ALLOW_TRANSACTION`, `DECLINE_TRANSACTION`, `MONITOR_CARD`, `MONITOR_CONNECTED_CARDS`, `WARN_CUSTOMER`, `VERIFY_WITH_CUSTOMER`, `STEP_UP_AUTH`, `BLOCK_CARD`, `BLOCK_ALL_CARDS`, `GENERATE_REPORT`, `CREATE_CASE`, `FILE_REPORT`, `ESCALATE_TO_ANALYST`, `CLOSE_NO_FRAUD`.

### Routes

| Route | Meaning |
| --- | --- |
| `auto` | Execute without a human queue (monitor, warn, verify, create case, close no fraud, and similar). |
| `L1` | Analyst approval (for example decline). |
| `L2` | Senior approval (`FILE_REPORT`, `BLOCK_ALL_CARDS`, and `BLOCK_CARD` above $2,500 exposure). |

### Rules (summary)

| Rule | When it fires | Typical actions |
| --- | --- | --- |
| R1 | Single weak signal, probability under 0.70 | Verify with customer or step-up auth |
| R2 | Customer denies the spend | Block card, create case; SAR / connected-card monitor when exposure or origin warrants |
| R3 | Customer confirms the spend | Close no fraud |
| R4 | No customer reply | Monitor card, decline; escalate when exposure &gt; $500 |
| R5 | Card testing | Decline, step-up; block card if a large follow-on cleared |
| R6 | Shared origin | Create case, file report, monitor connected cards |
| R7 | Disputed but recurring known spend | Create case, verify, warn — do not treat as confirmed fraud |
| R8 | Uncertain probability and material exposure or conflicting evidence | Escalate to analyst |
| R9 | Coordinated undocumented pattern | Create case, file report, escalate |
| R10 | `BLOCK_ALL_CARDS` only if two or more confirmed-fraud cards or compromised credentials | Filter otherwise |

`CREATE_CASE` is also added when probability is at least 0.30, evidence was requested, or the customer disputed.

### Stopping

The investigation stops when:

- **A** — Probability ≤ 0.15 or ≥ 0.85 with at least two independent evidence items.
- **B** — A customer verification reply settled the question (confirm or deny).
- **C** — Further hops are unlikely to change the decision.

The stop reason is stored on the answer and on `InvestigationCase`.

## Answer contract

Each investigation writes a Pydantic `Answer` (`backend/models/answer.py`) to `cases/HHG-###.json`.

```json
{
  "case_id": "HHG-001",
  "case": {
    "status": "closed_legitimate",
    "verdict": "legitimate",
    "fraud_probability": 0.12,
    "pattern": "none",
    "affected_txn_ids": [],
    "exposure_usd": 0.0,
    "evidence": [{ "claim": "...", "source": "graph", "ref": "query:investigate_txn(t=...)", "entity_ids": [] }],
    "summary": "...",
    "written_to_graph": true,
    "graph_case_id": "HHG-001"
  },
  "evidence_requests": [],
  "next_best_actions": { "initial": [], "final": [], "what_changed": "nothing" },
  "sar": { "file": false, "reason": "...", "narrative": "", "subjects": [], "total_amount_usd": 0, "activity_dates": [] },
  "stop_reason": "...",
  "tool_calls": 0,
  "tokens": 0,
  "latency_s": 0.0
}
```

Validators enforce, among other checks: legitimate cases have no exposure and do not file a SAR; a filed SAR has a narrative and two activity dates; `sar.file` matches `FILE_REPORT` in final actions; `what_changed` is `nothing` when no evidence was requested.

## HTTP API

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/` | Service descriptor and console URL. |
| `GET` | `/health` | `{ "status": "ok", "graph": "tigergraph" \| "local", "llm": "on" \| "off" }`. Never includes secrets. |
| `GET` | `/cases` | Case-pack queue. |
| `GET` | `/cases/{id}` | Saved answer JSON. |
| `GET` | `/stats` | Counts of verdicts and filed SARs across saved pack answers. |
| `POST` | `/investigate/{id}` | Run the LangGraph loop for a pack case and return the answer. |
| `GET` | `/graph/{id}` | Neighborhood nodes/edges, timeline, policy trace, conflicts, approvals, queue. Pack and monitoring ids. |
| `GET` | `/monitoring` | Optional high-risk investigations. |
| `GET` | `/monitoring/{id}` | Saved monitoring answer. |

CORS allows the console origins `http://127.0.0.1:3000` and `http://localhost:3000`.

## Analyst console

`frontend/` is Next.js 15 (React 19, TypeScript). Layout:

- **Left** — Case pack and monitoring lists.
- **Center** — Verdict, probability, exposure, summary, neighborhood (people → instruments → transactions → prior cases), timeline around the flagged payment, conflicts, evidence.
- **Right** — Investigate, approvals, approval queue (L1/L2 only), policy trace, connected cards, evidence requests, SAR, graph write.

`GET /graph/{id}` drives the neighborhood and timeline. Investigate calls `POST /investigate/{id}`.

```powershell
cd frontend
npm install
npx next dev --port 3000
```

Open http://127.0.0.1:3000. The API must be running on port 8000 (or set `TRACEGUARD_API`).

## Monitoring

`backend/investigate/monitor.py` ranks transactions with `risk_score >= 0.70` in the investigation window that are not already in the case pack, investigates them with the same composer, and writes `optional_monitoring/MON-###.json`. The console lists those files beside the pack.

## MCP

```powershell
python -m backend.mcp.server
python -m backend.mcp.official
```

TraceGuard MCP tools: `get_case_facts`, `investigate_txn`, `shared_cards_on_device`, `email_fanout`, `region_fanout`, `next_chain`, `device_degree`, `device_fanout`, `card_component`, `rag_search`, `get_investigation_case`, `upsert_investigation_case`, `investigate_case`, plus official names `tigergraph__run_query`, `tigergraph__run_installed_query`, and `tigergraph__search_top_k_similarity`.

## Configuration

Copy `.env.example` to `.env`. Do not commit `.env` or dataset CSVs.

| Variable | Purpose |
| --- | --- |
| `TG_HOST` | TigerGraph REST host. Empty → local processed CSVs. |
| `TG_GRAPHNAME` | Graph name (default `FraudGraph`). |
| `TG_USERNAME` / `TG_PASSWORD` / `TG_SECRET` / `TG_API_TOKEN` | Savanna authentication. |
| `TG_TGCLOUD` | TigerGraph Cloud / Savanna flag. |
| `OPENAI_API_KEY` | Optional. Embeddings, tool selection, summary/SAR wording. |
| `LLM_MODEL` | Chat model (default `gpt-4.1-mini`). |
| `TRACEGUARD_API` | Console rewrite target (default `http://127.0.0.1:8000`). |

`GET /health` reports whether the graph backend is `tigergraph` or `local`, and whether the LLM path is `on` or `off`.

## Run locally

Python 3.10+ and Node.js 18+. Use the project virtualenv.

```powershell
pip install -r backend/requirements.txt
python -m pytest
python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

```powershell
cd frontend
npm install
npx next dev --port 3000
```

Open http://127.0.0.1:3000. Select a case to load the saved answer. **Investigate** re-runs the live graph loop for pack cases.

Without `TG_HOST`, investigations use `data/processed/` exports and the same installed-query names. With `TG_HOST`, facts, GraphRAG, and persistence hit Savanna through tigergraph-mcp.

## Tests

```powershell
python -m pytest
```

Coverage includes policy routing, pattern analysis, answer validators, local graph tools, MCP client parsing, neighborhood views, monitoring, and the console contract.

## Layout

```
backend/                 FastAPI, LangGraph agent, policy, GraphRAG, MCP
backend/investigate/    facts, analysis, compose, explain, persist, monitor
backend/policy/          R1–R10, approval routes, stopping
backend/graph/           TigerGraph / local tool switch
backend/retrieve/        corpus, vector search, rag_search client
backend/mcp/              TraceGuard MCP server, official tigergraph-mcp
backend/api/              HTTP routes
tigergraph/schema/       FraudGraph DDL and RagDocument vectors
tigergraph/queries/      installed GSQL
tigergraph/loading/      load jobs and RAG seed
cases/                   pack answers HHG-001.json … HHG-020.json
optional_monitoring/     MON-*.json high-risk investigations
frontend/                Next.js investigation console
data/case_pack.csv       inbound alert queue
```
