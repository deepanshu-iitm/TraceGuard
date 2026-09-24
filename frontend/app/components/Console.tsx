"use client";

import { useEffect, useState } from "react";
import { getJson } from "../lib/api";
import type { Answer, CaseItem, GraphView, Health, Stats } from "../lib/types";
import { Neighborhood } from "./Neighborhood";

export function Console() {
  const [cases, setCases] = useState<CaseItem[]>([]);
  const [health, setHealth] = useState<Health | null>(null);
  const [stats, setStats] = useState<Stats | null>(null);
  const [selected, setSelected] = useState<CaseItem | null>(null);
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [graph, setGraph] = useState<GraphView | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    Promise.all([
      getJson<CaseItem[]>("/cases"),
      getJson<CaseItem[]>("/monitoring").catch(() => [] as CaseItem[]),
      getJson<Health>("/health").catch(() => null),
      getJson<Stats>("/stats").catch(() => null),
    ])
      .then(([exam, extra, live, counts]) => {
        setCases([...(exam || []), ...(extra || [])]);
        setHealth(live);
        setStats(counts);
      })
      .catch((err: Error) => setError(err.message));
  }, []);

  async function openCase(item: CaseItem) {
    setSelected(item);
    setError("");
    setAnswer(null);
    setGraph(null);
    try {
      const route = item.case_id.startsWith("MON-")
        ? `/monitoring/${encodeURIComponent(item.case_id)}`
        : `/cases/${encodeURIComponent(item.case_id)}`;
      const [saved, neighborhood] = await Promise.all([
        getJson<Answer>(route),
        getJson<GraphView>(`/graph/${encodeURIComponent(item.case_id)}`).catch(() => null),
      ]);
      setAnswer(saved);
      setGraph(neighborhood);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load case");
    }
  }

  async function investigate() {
    if (!selected) return;
    setBusy(true);
    setError("");
    try {
      const live = await getJson<Answer>(`/investigate/${encodeURIComponent(selected.case_id)}`, {
        method: "POST",
      });
      const neighborhood = await getJson<GraphView>(`/graph/${encodeURIComponent(selected.case_id)}`).catch(
        () => null,
      );
      setAnswer(live);
      setGraph(neighborhood);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Investigation failed");
    } finally {
      setBusy(false);
    }
  }

  const exam = cases.filter((item) => item.case_id.startsWith("HHG-"));
  const monitor = cases.filter((item) => item.case_id.startsWith("MON-"));
  const flaggedTxnId = selected?.flagged_txn_id || firstTxn(answer);

  return (
    <div className="shell">
      <header className="topbar">
        <div className="brand">
          <h1>TraceGuard</h1>
          <span>Investigation console</span>
        </div>
        <p className="status" id="mode">
          Graph <b>{health?.graph ?? "…"}</b> · LLM <b>{health?.llm ?? "…"}</b>
        </p>
        <p className="stats">
          {stats
            ? `${stats.exam} exam · ${stats.fraud} fraud · ${stats.legitimate} legitimate · ${stats.sar} SAR`
            : ""}
        </p>
      </header>
      <div className="workspace">
        <aside className="cases">
          <div className="group">Exam cases</div>
          {exam.map((item) => (
            <CaseButton key={item.case_id} item={item} active={selected?.case_id === item.case_id} onOpen={openCase} />
          ))}
          {monitor.length > 0 && <div className="group">Monitoring</div>}
          {monitor.map((item) => (
            <CaseButton key={item.case_id} item={item} active={selected?.case_id === item.case_id} onOpen={openCase} />
          ))}
        </aside>
        <main className="main">
          {error && <p className="error">{error}</p>}
          {!answer && !error && <p className="empty">Select a case to inspect the graph, timeline, and decision.</p>}
          {answer && (
            <CaseWorkspace
              answer={answer}
              graph={graph}
              flaggedTxnId={flaggedTxnId}
            />
          )}
        </main>
        <aside className="decision">
          <button className="run" onClick={investigate} disabled={!selected || busy}>
            {busy ? "Investigating…" : "Investigate"}
          </button>
          {answer && <DecisionRail answer={answer} graph={graph} />}
        </aside>
      </div>
    </div>
  );
}

function CaseButton({
  item,
  active,
  onOpen,
}: {
  item: CaseItem;
  active: boolean;
  onOpen: (item: CaseItem) => void;
}) {
  return (
    <button className={`case ${active ? "active" : ""}`} onClick={() => onOpen(item)}>
      <strong>{item.case_id}</strong>
      <em>
        {plain(item.trigger_type)}
        {item.risk_score != null ? ` · ${item.risk_score.toFixed(2)}` : ""}
      </em>
    </button>
  );
}

function CaseWorkspace({
  answer,
  graph,
  flaggedTxnId,
}: {
  answer: Answer;
  graph: GraphView | null;
  flaggedTxnId?: string;
}) {
  const c = answer.case;
  const timeline = (() => {
    const rows = graph?.timeline || [];
    const index = rows.findIndex((row) => row.flagged);
    if (index < 0) return rows.slice(0, 5);
    return rows.slice(Math.max(0, index - 2), index + 3);
  })();
  return (
    <>
      <div className="hero">
        <div>
          <p className={`verdict ${c.verdict}`}>{c.verdict}</p>
          <p className="quiet">
            {answer.case_id} · {plain(c.pattern) || "no known pattern"}
          </p>
        </div>
        <div className="kpis">
          <div>
            Probability<b>{c.fraud_probability.toFixed(2)}</b>
          </div>
          <div>
            Exposure<b>${c.exposure_usd.toFixed(2)}</b>
          </div>
          <div>
            SAR<b>{answer.sar.file ? "filed" : "not filed"}</b>
          </div>
        </div>
      </div>
      <p className="summary">{c.summary}</p>
      {graph && <Neighborhood graph={graph} flaggedTxnId={flaggedTxnId} />}
      <section className="panel">
        <h2>Timeline</h2>
        <ul className="timeline">
          {timeline.map((row) => (
            <li key={row.txn_id} className={row.flagged ? "flagged" : ""}>
              <span>{row.ts}</span>
              <span>{row.txn_id}</span>
              <span>
                ${row.amount.toFixed(2)} · {plain(row.channel)}
              </span>
            </li>
          ))}
          {timeline.length === 0 && <li>No history loaded.</li>}
        </ul>
      </section>
      <section className="panel">
        <h2>Conflicts</h2>
        <div className="split body">
          <div>
            <p className="quiet">Supports fraud</p>
            <List items={graph?.conflicts?.supports_fraud || claims(c.evidence, "Supports fraud")} />
          </div>
          <div>
            <p className="quiet">Supports legitimate</p>
            <List items={graph?.conflicts?.supports_legitimate || claims(c.evidence, "Supports legitimate")} />
          </div>
        </div>
      </section>
      <section className="panel">
        <h2>Evidence</h2>
        <ul className="evidence">
          {c.evidence.map((item) => (
            <li key={item.ref + item.claim}>
              <span className="chip">{item.source}</span>
              {item.claim}
              <span className="ref">{item.ref}</span>
            </li>
          ))}
        </ul>
      </section>
    </>
  );
}

function DecisionRail({ answer, graph }: { answer: Answer; graph: GraphView | null }) {
  const queue = (graph?.queue || answer.next_best_actions.final).filter(
    (item) => item.route.toLowerCase() !== "auto",
  );
  const approvals = graph?.approvals || answer.next_best_actions.final;
  const c = answer.case;
  const graphWrite = c.written_to_graph ? `Written as ${c.graph_case_id}` : "Not written";
  return (
    <>
      <section className="panel" style={{ marginTop: 14 }}>
        <h2>Approvals</h2>
        <div className="stack">
          {approvals.map((item) => (
            <div className="action" key={`${item.action}-${item.route}-${item.reason}`}>
              <strong>{plain(item.action)}</strong>
              <span className={`route ${item.route.toLowerCase()}`}>{plain(item.route)}</span>
              <p className="reason">{item.reason}</p>
            </div>
          ))}
        </div>
      </section>
      <section className="panel">
        <h2>Approval queue</h2>
        <div className="stack">
          {queue.length === 0 && <p className="quiet">Nothing waiting on a person.</p>}
          {queue.map((item) => (
            <div className="action" key={`q-${item.action}`}>
              <strong>{plain(item.action)}</strong>
              <span className={`route ${item.route.toLowerCase()}`}>{plain(item.route)}</span>
            </div>
          ))}
        </div>
      </section>
      <section className="panel">
        <h2>Policy trace</h2>
        <div className="stack">
          {(graph?.policy_trace || []).map((item, index) => (
            <div className="action" key={`${item.stage}-${index}`}>
              <strong>
                {plain(item.stage)} · {plain(item.action)}
              </strong>
              <p className="reason">{item.reason}</p>
            </div>
          ))}
        </div>
      </section>
      <section className="panel">
        <h2>Connected cards</h2>
        <div className="stack">
          <List items={c.connected_card_ids} />
          <h2 style={{ padding: 0, border: 0, marginTop: 12 }}>Evidence requests</h2>
          <List
            items={(answer.evidence_requests || []).map(
              (item) => `${plain(item.type)}: ${item.assumed_response}`,
            )}
          />
        </div>
      </section>
      <section className="panel">
        <h2>SAR</h2>
        <div className="stack">
          <p className="quiet">{answer.sar.file ? answer.sar.narrative : answer.sar.reason}</p>
        </div>
      </section>
      <section className="panel">
        <h2>Graph write</h2>
        <div className="stack">
          <p className="quiet">{graphWrite}</p>
        </div>
      </section>
    </>
  );
}

function List({ items }: { items: string[] }) {
  if (!items.length) return <p className="quiet">None.</p>;
  return (
    <ul className="list">
      {items.map((item) => (
        <li key={item}>{item}</li>
      ))}
    </ul>
  );
}

function claims(evidence: Answer["case"]["evidence"], prefix: string) {
  return evidence.filter((item) => item.claim.startsWith(prefix)).map((item) => item.claim);
}

function firstTxn(answer: Answer | null) {
  if (!answer) return "";
  const hit = answer.case.evidence.find((item) => item.ref.startsWith("query:investigate_txn"));
  return hit?.ref.match(/t=([^)]+)/)?.[1] || "";
}

function plain(value?: string) {
  return (value || "").replaceAll("_", " ");
}
