export type CaseItem = {
  case_id: string;
  trigger_type: string;
  trigger_text: string;
  flagged_txn_id: string;
  card_id: string;
  customer_id: string;
  risk_score: number | null;
};

export type ActionItem = {
  action: string;
  route: string;
  reason: string;
  stage?: string;
  status?: string;
};

export type EvidenceItem = {
  claim: string;
  source: string;
  ref: string;
};

export type Answer = {
  case_id: string;
  stop_reason: string;
  tool_calls: number;
  tokens: number;
  latency_s: number;
  case: {
    verdict: string;
    status: string;
    pattern: string;
    fraud_probability: number;
    exposure_usd: number;
    summary: string;
    evidence: EvidenceItem[];
    connected_card_ids: string[];
    connected_device_profiles: string[];
    similar_prior_cases: string[];
    written_to_graph: boolean;
    graph_case_id: string;
  };
  next_best_actions: {
    initial: ActionItem[];
    final: ActionItem[];
    what_changed: string;
  };
  evidence_requests: {
    type: string;
    asked_after_step: string;
    assumed_response: string;
  }[];
  sar: {
    file: boolean;
    reason: string;
    narrative: string;
    subjects?: string[];
    total_amount_usd?: number;
    activity_dates?: string[];
  };
};

export type GraphNode = { id: string; type: string; label: string };
export type GraphEdge = { from: string; to: string; type: string };
export type TimelineRow = {
  txn_id: string;
  ts: string;
  amount: number;
  channel: string;
  flagged: boolean;
  episode: boolean;
};

export type GraphView = {
  case_id: string;
  nodes: GraphNode[];
  edges: GraphEdge[];
  timeline: TimelineRow[];
  approvals: ActionItem[];
  queue: ActionItem[];
  policy: {
    verdict?: string;
    pattern?: string;
    what_changed?: string;
  };
  policy_trace: ActionItem[];
  conflicts: {
    supports_fraud: string[];
    supports_legitimate: string[];
  };
};

export type Health = { status: string; graph: string; llm: string };
export type Stats = {
  exam: number;
  fraud: number;
  legitimate: number;
  uncertain: number;
  sar: number;
};
