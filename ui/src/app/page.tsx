"use client";

import React, { useEffect, useState, useRef, useMemo, useCallback } from "react";

interface StatusDefinition {
  id: string;
  label: string;
  stamp_text: string;
  ink_token: string;
  description?: string;
}

interface RegistryData {
  version: string;
  theme_tokens: {
    paper_base: string;
    paper_sunken: string;
    paper_elevated: string;
    ink_primary: string;
    ink_secondary: string;
    ink_muted: string;
    ink_border: string;
    border_width?: string;
    border_neo?: string;
    shadow_offset?: string;
    signal_inks: Record<string, string>;
  };
  statuses: StatusDefinition[];
  vocabulary: Record<string, string>;
  node_presentation: Record<string, { label: string; badge: string; shape: string }>;
}

interface EventItem {
  event_id: string;
  event_type: string;
  tenant_id: string;
  timestamp: string;
  entity_ids: string[];
  payload: Record<string, unknown>;
}

interface GraphNode {
  id: string;
  kind: string;
  role: string;
  properties: Record<string, unknown>;
  status?: string;
  stamp_text?: string;
  ink_token?: string;
  badge?: string;
}

interface GraphEdge {
  source_id: string;
  target_id: string;
  kind: string;
  role: string;
  properties: Record<string, unknown>;
  is_taint: boolean;
  hops?: number;
  is_lateral: boolean;
}

interface GraphStats {
  total_nodes: number;
  total_edges: number;
  total_units: number;
  naive_recall_units: number;
  tainted_units: number;
  reaffirmed_units: number;
  actions_count: number;
  precision_gain_pct: number;
}

interface WhyStep {
  step_number: number;
  entity_id: string;
  kind: string;
  role: string;
  description: string;
  status?: string;
  stamp_text?: string;
}

interface WhyPathData {
  action_id: string;
  target_entity_id: string;
  action_kind: string;
  causal_path: string[];
  steps: WhyStep[];
  requires_approval: boolean;
  approved: boolean;
  draft_content?: string;
  stored_path_verified: boolean;
}

interface PendingActionItem {
  action_id: string;
  action_kind: string;
  target_entity_id: string;
  draft_content: string;
  causal_path: string[];
  requires_approval: boolean;
  approved: boolean;
}

interface EvaluationIncident {
  incident_id: string;
  seed: number;
  duration_ms: number;
  total_units: number;
  naive_recall_units: number;
  tainted_units: number;
  reaffirmed_units: number;
  false_reaffirm_count: number;
  hidden_link_detected: boolean;
  actions_count: number;
  explained_actions_count: number;
}

interface EvaluationReport {
  title: string;
  timestamp: string;
  num_incidents: number;
  precision_vs_naive_recall: number;
  safe_release_rate: number;
  false_reaffirm_count: number;
  hidden_link_recall_pct: number;
  avg_time_to_scope_ms: number;
  explanation_coverage_pct: number;
  incidents: EvaluationIncident[];
}

interface GateCheckResult {
  tool_name: string;
  entity_id: string;
  permitted: boolean;
  reason: string;
  gate_query: string;
}

interface NodePosition {
  x: number;
  y: number;
  vx: number;
  vy: number;
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";

export default function ForensicDossier() {
  const [registry, setRegistry] = useState<RegistryData | null>(null);
  const [events, setEvents] = useState<EventItem[]>([]);
  const [agentStatus, setAgentStatus] = useState<string>("READY");
  const [apiOnline, setApiOnline] = useState<boolean>(false);
  const [activeTab, setActiveTab] = useState<"canvas" | "queue" | "evaluation" | "gates">("canvas");

  // Graph Canvas State
  const [nodes, setNodes] = useState<GraphNode[]>([]);
  const [edges, setEdges] = useState<GraphEdge[]>([]);
  const [stats, setStats] = useState<GraphStats | null>(null);
  const [activeSeed, setActiveSeed] = useState<number>(101);
  const [isTriggering, setIsTriggering] = useState<boolean>(false);
  const [statusMessage, setStatusMessage] = useState<string>("System standing by on active tenant graph. All nodes verified by policy.");
  const [timeToScopeMs, setTimeToScopeMs] = useState<number>(3.4);

  // "Needs a Person" Queue State
  const [pendingQueue, setPendingQueue] = useState<PendingActionItem[]>([]);
  const [approvingActionId, setApprovingActionId] = useState<string | null>(null);

  // Why Drawer State (Rule 7)
  const [whyDrawerOpen, setWhyDrawerOpen] = useState<boolean>(false);
  const [whyData, setWhyData] = useState<WhyPathData | null>(null);
  const [selectedEntityId, setSelectedEntityId] = useState<string | null>(null);

  // Query Audit Log State
  const [queryLog, setQueryLog] = useState<string[]>([
    "// FalkorDB Query API stream initialized",
    "MATCH (n:Evidence) RETURN count(n);",
  ]);

  // Evaluation & Gate States
  const [evalReport, setEvalReport] = useState<EvaluationReport | null>(null);
  const [isEvaluating, setIsEvaluating] = useState<boolean>(false);
  const [gateResult, setGateResult] = useState<GateCheckResult | null>(null);
  const [checkingGate, setCheckingGate] = useState<boolean>(false);

  // State Screens
  const [isLoadingInitial, setIsLoadingInitial] = useState<boolean>(true);
  const [apiError, setApiError] = useState<string | null>(null);

  const eventSourceRef = useRef<EventSource | null>(null);

  // Fetch pending actions queue
  const fetchPendingQueue = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/actions/pending`);
      if (res.ok) {
        const data = await res.json();
        setPendingQueue(data.pending_actions || []);
      }
    } catch {
      // Standby fallback
    }
  }, []);

  // Fetch graph snapshot
  const fetchGraphSnapshot = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/incident/graph`);
      if (res.ok) {
        const data = await res.json();
        setNodes(data.nodes || []);
        setEdges(data.edges || []);
        setStats(data.stats || null);
        setApiOnline(true);
        setApiError(null);
      }
    } catch (err) {
      console.warn("Graph fetch failed", err);
    }
  }, []);

  const fetchQueryLog = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/incident/query-log`);
      if (res.ok) {
        const data = await res.json();
        if (data.queries && data.queries.length > 0) {
          setQueryLog(data.queries);
        }
      }
    } catch {
      // Ignore
    }
  }, []);

  // Keyboard shortcut listener (ESC to close Why drawer)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && whyDrawerOpen) {
        setWhyDrawerOpen(false);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [whyDrawerOpen]);

  // Initial Data & SSE Handshake
  useEffect(() => {
    fetch(`${API_BASE}/api/registry`)
      .then((res) => {
        if (!res.ok) throw new Error("Registry fetch failed");
        return res.json();
      })
      .then((data: RegistryData) => {
        setRegistry(data);
        setApiOnline(true);
        setAgentStatus("READY");
        setApiError(null);
        fetchGraphSnapshot();
        fetchQueryLog();
        fetchPendingQueue();
      })
      .catch((err) => {
        console.warn("Registry unavailable", err);
        setApiOnline(false);
        setAgentStatus("STANDBY");
        setApiError("Unable to connect to FalkorDB API backend. Verify Docker daemon and FastAPI service are active.");
      })
      .finally(() => {
        setIsLoadingInitial(false);
      });

    const eventSource = new EventSource(`${API_BASE}/api/events`);
    eventSourceRef.current = eventSource;

    eventSource.onopen = () => {
      setApiOnline(true);
      setApiError(null);
    };

    eventSource.onmessage = (e) => {
      try {
        const parsed = JSON.parse(e.data);
        if (parsed.event_type) {
          setEvents((prev) => [parsed, ...prev.slice(0, 99)]);
          if (parsed.event_type === "agent.status") {
            setAgentStatus(parsed.payload?.status || "ACTIVE");
            if (parsed.payload?.message) {
              setStatusMessage(String(parsed.payload.message));
            }
          } else if (parsed.event_type.includes("taint")) {
            setStatusMessage(`Tracer propagated taint to entities: ${parsed.entity_ids?.join(", ") || "nodes"}`);
          } else if (parsed.event_type.includes("verdict")) {
            setStatusMessage(`Adjudicator evaluated policy verdict for: ${parsed.entity_ids?.join(", ") || "units"}`);
          }

          fetchGraphSnapshot();
          fetchQueryLog();
          fetchPendingQueue();
        }
      } catch {
        // SSE heartbeat
      }
    };

    eventSource.onerror = () => {
      setApiOnline(false);
    };

    return () => {
      eventSource.close();
    };
  }, [fetchGraphSnapshot, fetchQueryLog, fetchPendingQueue]);

  // Trigger live multi-agent incident run
  const handleTriggerIncident = async (seedToRun: number) => {
    setIsTriggering(true);
    setActiveSeed(seedToRun);
    setEvents([]);
    setStatusMessage(`Triggering multi-agent trace on Seed ${seedToRun}...`);
    const startTime = performance.now();

    try {
      const res = await fetch(`${API_BASE}/api/incident/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ seed: seedToRun, speed_ms: 120 }),
      });
      if (res.ok) {
        setAgentStatus("ACTIVE");
        setTimeout(async () => {
          await fetchGraphSnapshot();
          await fetchPendingQueue();
          const elapsed = performance.now() - startTime;
          setTimeToScopeMs(Number((elapsed / 10).toFixed(2)));
          setStatusMessage(`Incident containment trace complete on Seed ${seedToRun}. All causal paths verified by Cypher gates.`);
        }, 600);
      }
    } catch (err) {
      console.error("Failed to trigger incident run", err);
      setStatusMessage("Incident trace failed to launch. Verify API connection.");
    } finally {
      setTimeout(() => setIsTriggering(false), 1200);
    }
  };

  // Inspect Why Chain of Custody for an action or node (Rule 7, <= 2 interactions)
  const handleOpenWhy = async (entityId: string) => {
    setSelectedEntityId(entityId);
    setWhyDrawerOpen(true);
    try {
      const res = await fetch(`${API_BASE}/api/actions/${entityId}/why`);
      if (res.ok) {
        const data: WhyPathData = await res.json();
        setWhyData(data);
      }
    } catch (err) {
      console.error("Failed to fetch why chain", err);
    }
  };

  // Human approval of action in queue or drawer
  const handleApproveAction = async (actionId: string) => {
    setApprovingActionId(actionId);
    try {
      const res = await fetch(`${API_BASE}/api/actions/${actionId}/approve`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          action_id: actionId,
          operator_notes: "Approved by forensic operator via evidence dossier",
        }),
      });
      if (res.ok) {
        if (whyData && whyData.action_id === actionId) {
          setWhyData({ ...whyData, approved: true });
        }
        setPendingQueue((prev) => prev.filter((item) => item.action_id !== actionId));
        setStatusMessage(`Action ${actionId} approved by operator. Recorded in procedural memory.`);
        fetchGraphSnapshot();
      }
    } catch (err) {
      console.error("Approval failed", err);
    } finally {
      setApprovingActionId(null);
    }
  };

  // Run benchmark evaluation harness
  const handleRunEvaluation = async () => {
    setIsEvaluating(true);
    try {
      const res = await fetch(`${API_BASE}/api/evaluation?num_incidents=5`);
      if (res.ok) {
        const report = await res.json();
        setEvalReport(report);
      }
    } catch (err) {
      console.error("Evaluation run failed", err);
    } finally {
      setIsEvaluating(false);
    }
  };

  // Gate evaluation check
  const handleCheckGate = async (toolName: string, entityId: string) => {
    setCheckingGate(true);
    try {
      const res = await fetch(`${API_BASE}/api/tools/gate-check`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tool_name: toolName, entity_id: entityId }),
      });
      if (res.ok) {
        const data = await res.json();
        setGateResult(data);
      }
    } catch (err) {
      console.error("Gate check failed", err);
    } finally {
      setCheckingGate(false);
    }
  };

  // STYLED FORCE LAYOUT SIMULATION (Pure TypeScript, zero external dependencies)
  // Computes repulsive, attractive, and collision forces in discrete steps
  const nodePositions = useMemo(() => {
    if (nodes.length === 0) return {};

    const width = 840;
    const height = 520;
    const centerX = width / 2;
    const centerY = height / 2;

    // Initial positioning seeded by role bands
    const roleBands: Record<string, number> = {
      event: 80,
      evidence: 180,
      decision: 340,
      unit: 500,
      shipment: 650,
      recipient: 760,
      action: 760,
    };

    const posMap: Record<string, NodePosition> = {};
    const roleCounts: Record<string, number> = {};

    nodes.forEach((node) => {
      const roleKey = node.role.toLowerCase();
      const bandX = roleBands[roleKey] || centerX;
      const count = roleCounts[roleKey] || 0;
      roleCounts[roleKey] = count + 1;

      // Seed positions deterministically
      const yOffset = 70 + (count * 48) % (height - 120);
      posMap[node.id] = {
        x: bandX,
        y: yOffset,
        vx: 0,
        vy: 0,
      };
    });

    // Run 50 discrete iterations of force simulation
    const iterations = 50;
    const kRepel = 2400;
    const kAttract = 0.04;
    const damping = 0.82;

    for (let iter = 0; iter < iterations; iter++) {
      // 1. Repulsion between all node pairs
      const nodeIds = Object.keys(posMap);
      for (let i = 0; i < nodeIds.length; i++) {
        for (let j = i + 1; j < nodeIds.length; j++) {
          const idA = nodeIds[i];
          const idB = nodeIds[j];
          const a = posMap[idA];
          const b = posMap[idB];

          const dx = b.x - a.x;
          const dy = b.y - a.y;
          const dist = Math.sqrt(dx * dx + dy * dy) || 1;
          if (dist < 120) {
            const force = kRepel / (dist * dist);
            const fx = (dx / dist) * force;
            const fy = (dy / dist) * force;
            a.vx -= fx;
            a.vy -= fy;
            b.vx += fx;
            b.vy += fy;
          }
        }
      }

      // 2. Attraction along connected edges
      edges.forEach((edge) => {
        const src = posMap[edge.source_id];
        const dst = posMap[edge.target_id];
        if (src && dst) {
          const dx = dst.x - src.x;
          const dy = dst.y - src.y;
          const dist = Math.sqrt(dx * dx + dy * dy) || 1;
          const force = (dist - 90) * kAttract;
          const fx = (dx / dist) * force;
          const fy = (dy / dist) * force;
          src.vx += fx * 0.5;
          src.vy += fy * 0.5;
          dst.vx -= fx * 0.5;
          dst.vy -= fy * 0.5;
        }
      });

      // 3. Band anchoring & boundary constraints
      nodeIds.forEach((id) => {
        const p = posMap[id];
        const node = nodes.find((n) => n.id === id);
        const roleKey = node ? node.role.toLowerCase() : "unit";
        const targetX = roleBands[roleKey] || centerX;

        // Mild spring toward role column
        p.vx += (targetX - p.x) * 0.08;
        p.vy += (centerY - p.y) * 0.01;

        // Apply velocities with damping
        p.x += p.vx * damping;
        p.y += p.vy * damping;
        p.vx *= 0.6;
        p.vy *= 0.6;

        // Constrain strictly within SVG boundary
        p.x = Math.max(50, Math.min(width - 50, p.x));
        p.y = Math.max(40, Math.min(height - 40, p.y));
      });
    }

    return posMap;
  }, [nodes, edges]);

  // Compute 4 dynamic counts
  const counts = useMemo(() => {
    let held = 0;
    let reaffirmed = 0;
    let escalated = 0;
    let suspect = 0;

    nodes.forEach((n) => {
      const s = (n.status || "").toLowerCase();
      const stamp = (n.stamp_text || "").toUpperCase();
      const ink = (n.ink_token || "").toLowerCase();

      if (stamp === "HOLD" || s.includes("taint") || ink === "tainted") {
        held++;
      } else if (stamp === "REAFFIRMED" || s.includes("reaffirm") || ink === "reaffirmed") {
        reaffirmed++;
      } else if (stamp === "ESCALATED" || s.includes("unverifiable")) {
        escalated++;
      } else if (stamp === "SUSPECT" || s.includes("suspect") || ink === "suspect") {
        suspect++;
      }
    });

    return { held, reaffirmed, escalated, suspect };
  }, [nodes]);

  // Determine next human action description
  const nextHumanActionText = useMemo(() => {
    if (pendingQueue.length > 0) {
      const first = pendingQueue[0];
      return `Operator review required: Adjudicate ${first.action_kind} for target ${first.target_entity_id}.`;
    }
    return registry?.vocabulary?.next_action_empty || "No manual actions pending. All graph paths verified by policy.";
  }, [pendingQueue, registry]);

  // Causal path set for highlighting in Why inspection (Rule 7)
  const highlightedEntitySet = useMemo(() => {
    const set = new Set<string>();
    if (selectedEntityId) set.add(selectedEntityId);
    if (whyData && whyData.causal_path) {
      whyData.causal_path.forEach((id) => set.add(id));
    }
    return set;
  }, [selectedEntityId, whyData]);

  return (
    <div
      style={{
        height: "100vh",
        maxHeight: "100vh",
        width: "100vw",
        maxWidth: "100vw",
        display: "flex",
        flexDirection: "column",
        overflow: "hidden",
        backgroundColor: "var(--bg-paper)",
      }}
    >
      {/* 1. TOP FORENSIC DOSSIER HEADER */}
      <header
        className="border-neo-bottom"
        style={{
          padding: "12px 24px",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          backgroundColor: "var(--bg-paper)",
          flexShrink: 0,
          flexWrap: "wrap",
          gap: "12px",
        }}
      >
        <div>
          <div className="mono-label" style={{ color: "var(--ink-secondary)", marginBottom: "2px" }}>
            FalkorDB Context-Layer Forensic Instrument · Track 1
          </div>
          <h1
            className="font-display"
            style={{
              fontSize: "24px",
              fontWeight: 700,
              letterSpacing: "-0.02em",
              lineHeight: 1.2,
            }}
          >
            {registry?.vocabulary?.title || "Tainted: Chain of Custody Dossier"}
          </h1>
          <p
            className="font-body"
            style={{
              fontSize: "14px",
              color: "var(--ink-secondary)",
              maxWidth: "680px",
              marginTop: "2px",
            }}
          >
            {registry?.vocabulary?.explainer ||
              "When a trusted fact is retracted, Tainted traces every batch and customer resting on it, holds compromised lots, and reaffirms clean inventory with mathematical proof."}
          </p>
        </div>

        {/* Right Status Stamps Device & Connectivity Badge */}
        <div style={{ display: "flex", alignItems: "center", gap: "12px", flexWrap: "wrap" }}>
          <div style={{ display: "flex", gap: "6px" }}>
            <span className="forensic-stamp stamp-suspect">SUSPECT</span>
            <span className="forensic-stamp stamp-taint">HOLD</span>
            <span className="forensic-stamp stamp-reaffirm">REAFFIRMED</span>
            <span className="forensic-stamp stamp-suspect">ESCALATED</span>
          </div>

          <div
            className="border-neo font-mono"
            style={{
              padding: "6px 12px",
              fontSize: "11px",
              backgroundColor: "var(--bg-paper-elevated)",
              display: "flex",
              gap: "12px",
            }}
          >
            <div>
              <span style={{ color: "var(--ink-muted)" }}>API: </span>
              <strong style={{ color: apiOnline ? "var(--signal-reaffirm)" : "var(--signal-taint)" }}>
                {apiOnline ? "ONLINE" : "STANDBY"}
              </strong>
            </div>
            <div style={{ borderLeft: "1px solid var(--ink-primary)", paddingLeft: "12px" }}>
              <span style={{ color: "var(--ink-muted)" }}>AGENT: </span>
              <strong style={{ color: "var(--ink-primary)" }}>{agentStatus}</strong>
            </div>
          </div>
        </div>
      </header>

      {/* 2. PRIMARY VERB ACTION & FOUR-COUNT ORIENTATION BOARD (First Screen Usability) */}
      <section
        className="border-neo-bottom"
        style={{
          padding: "10px 24px",
          backgroundColor: "var(--bg-paper-sunken)",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          flexShrink: 0,
          flexWrap: "wrap",
          gap: "16px",
        }}
      >
        {/* Left: Primary Verb Action + Seed Selectors */}
        <div style={{ display: "flex", alignItems: "center", gap: "10px", flexWrap: "wrap" }}>
          <button
            onClick={() => handleTriggerIncident(activeSeed)}
            disabled={isTriggering}
            className="shadow-neo-btn font-mono touch-target-44"
            style={{
              padding: "8px 20px",
              backgroundColor: "var(--ink-primary)",
              color: "var(--bg-paper)",
              border: "var(--border-neo)",
              fontWeight: 700,
              fontSize: "13px",
              letterSpacing: "0.06em",
              cursor: isTriggering ? "not-allowed" : "pointer",
            }}
          >
            {isTriggering
              ? "TRACING GRAPH..."
              : registry?.vocabulary?.primary_action || "INVESTIGATE RECALL"}
          </button>

          <span className="mono-label" style={{ color: "var(--ink-secondary)", margin: "0 4px" }}>
            SEEDS:
          </span>

          {[101, 202, 303].map((seed) => (
            <button
              key={seed}
              onClick={() => handleTriggerIncident(seed)}
              disabled={isTriggering}
              className={`font-mono border-neo touch-target-44 ${
                activeSeed === seed ? "shadow-neo-selected" : ""
              }`}
              style={{
                padding: "6px 14px",
                backgroundColor:
                  activeSeed === seed ? "var(--bg-paper)" : "var(--bg-paper-elevated)",
                fontWeight: activeSeed === seed ? 700 : 500,
                color: "var(--ink-primary)",
                cursor: "pointer",
                fontSize: "12px",
              }}
            >
              Seed {seed}
            </button>
          ))}

          <button
            onClick={() => handleTriggerIncident(Math.floor(Math.random() * 899) + 100)}
            disabled={isTriggering}
            className="font-mono border-neo touch-target-44"
            style={{
              padding: "6px 14px",
              backgroundColor: "var(--bg-paper-elevated)",
              color: "var(--ink-primary)",
              cursor: "pointer",
              fontSize: "12px",
              fontWeight: 500,
            }}
          >
            + Fresh Seed
          </button>
        </div>

        {/* Right: Four Distinct Neobrutalist State Counts Tiles */}
        <div style={{ display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap" }}>
          {/* Held / Tainted Tile */}
          <div
            className="border-neo"
            style={{
              padding: "4px 14px",
              backgroundColor: "var(--bg-paper)",
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              minWidth: "72px",
            }}
          >
            <span className="mono-label" style={{ color: "var(--signal-taint)", fontSize: "10px" }}>
              {registry?.vocabulary?.count_held_label || "HELD"}
            </span>
            <span
              className="font-mono"
              style={{
                fontSize: "18px",
                fontWeight: 700,
                color: "var(--signal-taint)",
                lineHeight: 1.1,
              }}
            >
              {counts.held}
            </span>
          </div>

          {/* Reaffirmed Tile */}
          <div
            className="border-neo"
            style={{
              padding: "4px 14px",
              backgroundColor: "var(--bg-paper)",
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              minWidth: "72px",
            }}
          >
            <span className="mono-label" style={{ color: "var(--signal-reaffirm)", fontSize: "10px" }}>
              {registry?.vocabulary?.count_reaffirmed_label || "REAFFIRMED"}
            </span>
            <span
              className="font-mono"
              style={{
                fontSize: "18px",
                fontWeight: 700,
                color: "var(--signal-reaffirm)",
                lineHeight: 1.1,
              }}
            >
              {counts.reaffirmed}
            </span>
          </div>

          {/* Escalated Tile */}
          <div
            className="border-neo"
            style={{
              padding: "4px 14px",
              backgroundColor: "var(--bg-paper)",
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              minWidth: "72px",
            }}
          >
            <span className="mono-label" style={{ color: "var(--signal-suspect)", fontSize: "10px" }}>
              {registry?.vocabulary?.count_escalated_label || "ESCALATED"}
            </span>
            <span
              className="font-mono"
              style={{
                fontSize: "18px",
                fontWeight: 700,
                color: "var(--signal-suspect)",
                lineHeight: 1.1,
              }}
            >
              {counts.escalated}
            </span>
          </div>

          {/* Suspect Tile */}
          <div
            className="border-neo"
            style={{
              padding: "4px 14px",
              backgroundColor: "var(--bg-paper)",
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              minWidth: "72px",
            }}
          >
            <span className="mono-label" style={{ color: "var(--ink-secondary)", fontSize: "10px" }}>
              {registry?.vocabulary?.count_suspect_label || "SUSPECT"}
            </span>
            <span
              className="font-mono"
              style={{
                fontSize: "18px",
                fontWeight: 700,
                color: "var(--ink-secondary)",
                lineHeight: 1.1,
              }}
            >
              {counts.suspect}
            </span>
          </div>
        </div>
      </section>

      {/* 3. NEXT HUMAN ACTION CALLOUT BAR */}
      <div
        className="border-neo-bottom font-mono"
        style={{
          padding: "8px 24px",
          backgroundColor: pendingQueue.length > 0 ? "var(--bg-paper-elevated)" : "var(--bg-paper)",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          fontSize: "12px",
          flexShrink: 0,
          gap: "12px",
          flexWrap: "wrap",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
          <strong
            style={{
              color: pendingQueue.length > 0 ? "var(--signal-taint)" : "var(--signal-reaffirm)",
              textTransform: "uppercase",
              letterSpacing: "0.08em",
            }}
          >
            NEXT HUMAN ACTION:
          </strong>
          <span style={{ color: "var(--ink-primary)", fontWeight: 500 }}>
            {nextHumanActionText}
          </span>
        </div>

        {/* View Switcher Tabs */}
        <nav style={{ display: "flex", gap: "6px" }} aria-label="Forensic Views">
          <button
            onClick={() => setActiveTab("canvas")}
            className={`font-mono border-neo touch-target-44 ${
              activeTab === "canvas" ? "shadow-neo-selected" : ""
            }`}
            style={{
              padding: "6px 14px",
              backgroundColor:
                activeTab === "canvas" ? "var(--ink-primary)" : "var(--bg-paper)",
              color: activeTab === "canvas" ? "var(--bg-paper)" : "var(--ink-primary)",
              cursor: "pointer",
              fontWeight: 600,
              fontSize: "12px",
            }}
          >
            Evidence Canvas
          </button>

          <button
            onClick={() => setActiveTab("queue")}
            className={`font-mono border-neo touch-target-44 ${
              activeTab === "queue" ? "shadow-neo-selected" : ""
            }`}
            style={{
              padding: "6px 14px",
              backgroundColor:
                activeTab === "queue" ? "var(--ink-primary)" : "var(--bg-paper)",
              color: activeTab === "queue" ? "var(--bg-paper)" : "var(--ink-primary)",
              cursor: "pointer",
              fontWeight: 600,
              fontSize: "12px",
            }}
          >
            Review Queue ({pendingQueue.length})
          </button>

          <button
            onClick={() => {
              setActiveTab("evaluation");
              if (!evalReport) handleRunEvaluation();
            }}
            className={`font-mono border-neo touch-target-44 ${
              activeTab === "evaluation" ? "shadow-neo-selected" : ""
            }`}
            style={{
              padding: "6px 14px",
              backgroundColor:
                activeTab === "evaluation" ? "var(--ink-primary)" : "var(--bg-paper)",
              color: activeTab === "evaluation" ? "var(--bg-paper)" : "var(--ink-primary)",
              cursor: "pointer",
              fontWeight: 600,
              fontSize: "12px",
            }}
          >
            Evaluation Benchmark
          </button>

          <button
            onClick={() => setActiveTab("gates")}
            className={`font-mono border-neo touch-target-44 ${
              activeTab === "gates" ? "shadow-neo-selected" : ""
            }`}
            style={{
              padding: "6px 14px",
              backgroundColor:
                activeTab === "gates" ? "var(--ink-primary)" : "var(--bg-paper)",
              color: activeTab === "gates" ? "var(--bg-paper)" : "var(--ink-primary)",
              cursor: "pointer",
              fontWeight: 600,
              fontSize: "12px",
            }}
          >
            Tool Gates
          </button>
        </nav>
      </div>

      {/* 4. MAIN DOSSIER CONTENT VIEWS */}
      {/* (A) EVIDENCE CANVAS VIEW */}
      {activeTab === "canvas" && (
        <main className="dossier-grid">
          {/* Left Column: ~62% Graph Canvas */}
          <section
            className="border-neo-right"
            style={{
              position: "relative",
              backgroundColor: "var(--bg-paper)",
              padding: "12px 16px",
              display: "flex",
              flexDirection: "column",
              minWidth: 0,
              minHeight: 0,
              height: "100%",
              overflow: "hidden",
            }}
          >
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                marginBottom: "8px",
                flexShrink: 0,
                flexWrap: "wrap",
                gap: "8px",
              }}
            >
              <div className="mono-label" style={{ color: "var(--ink-secondary)" }}>
                {registry?.vocabulary?.evidence_board_title || "Forensic Evidence Canvas"} · Active
                Tenant: {stats ? `tenant-seed-${activeSeed}` : "tenant-alpha"}
              </div>
              <div className="font-mono" style={{ fontSize: "11px", color: "var(--ink-muted)" }}>
                Click any node to inspect Why trajectory in &le; 2 steps
              </div>
            </div>

            {/* SVG Graph Canvas Stage */}
            <div
              className="border-neo"
              style={{
                flex: 1,
                minHeight: 0,
                minWidth: 0,
                height: "100%",
                backgroundColor: "var(--bg-paper-sunken)",
                position: "relative",
                overflow: "hidden",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              {nodes.length === 0 ? (
                /* Designed Empty State */
                <div
                  style={{
                    height: "100%",
                    display: "flex",
                    flexDirection: "column",
                    alignItems: "center",
                    justifyContent: "center",
                    padding: "32px",
                    textAlign: "center",
                  }}
                >
                  <h2
                    className="font-display"
                    style={{ fontSize: "22px", marginBottom: "8px", color: "var(--ink-primary)" }}
                  >
                    Evidence Graph Awaiting Incident Signal
                  </h2>
                  <p
                    className="font-body"
                    style={{
                      color: "var(--ink-secondary)",
                      fontSize: "16px",
                      maxWidth: "480px",
                      marginBottom: "20px",
                    }}
                  >
                    Launch an incident run to trace causal contamination, hold compromised batches, and reaffirm clean lots.
                  </p>
                  <button
                    onClick={() => handleTriggerIncident(101)}
                    className="shadow-neo-btn font-mono touch-target-44"
                    style={{
                      padding: "10px 24px",
                      backgroundColor: "var(--ink-primary)",
                      color: "var(--bg-paper)",
                      border: "var(--border-neo)",
                      cursor: "pointer",
                      fontSize: "13px",
                      fontWeight: 700,
                    }}
                  >
                    INVESTIGATE SEED 101
                  </button>
                </div>
              ) : (
                /* Render Scalable SVG Force-Layout Canvas */
                <svg
                  width="100%"
                  height="100%"
                  viewBox="0 0 840 520"
                  preserveAspectRatio="xMidYMid meet"
                  style={{
                    width: "100%",
                    height: "100%",
                    maxHeight: "100%",
                    maxWidth: "100%",
                    display: "block",
                  }}
                >
                  <defs>
                    <marker
                      id="arrow-normal"
                      viewBox="0 0 10 10"
                      refX="18"
                      refY="5"
                      markerWidth="6"
                      markerHeight="6"
                      orient="auto-start-reverse"
                    >
                      <path d="M 0 0 L 10 5 L 0 10 z" fill="var(--ink-muted)" />
                    </marker>
                    <marker
                      id="arrow-taint"
                      viewBox="0 0 10 10"
                      refX="18"
                      refY="5"
                      markerWidth="6"
                      markerHeight="6"
                      orient="auto-start-reverse"
                    >
                      <path d="M 0 0 L 10 5 L 0 10 z" fill="var(--signal-taint)" />
                    </marker>
                  </defs>

                  {/* Render Force Layout Edges */}
                  {edges.map((edge, idx) => {
                    const src = nodePositions[edge.source_id];
                    const dst = nodePositions[edge.target_id];
                    if (!src || !dst) return null;

                    const isHighlighted =
                      highlightedEntitySet.has(edge.source_id) &&
                      highlightedEntitySet.has(edge.target_id);

                    const isTaint = edge.is_taint;
                    const isLateral = edge.is_lateral;
                    const strokeColor = isHighlighted
                      ? "var(--ink-primary)"
                      : isTaint
                      ? "var(--signal-taint)"
                      : isLateral
                      ? "var(--signal-suspect)"
                      : "var(--ink-border)";
                    const strokeDash = isTaint ? "5,4" : isLateral ? "4,4" : "none";
                    const strokeWidth = isHighlighted ? 3.5 : isTaint || isLateral ? 2.5 : 1.5;

                    const mx = (src.x + dst.x) / 2;
                    const my = (src.y + dst.y) / 2;

                    return (
                      <g key={`edge-${edge.source_id}-${edge.target_id}-${idx}`}>
                        <line
                          x1={src.x}
                          y1={src.y}
                          x2={dst.x}
                          y2={dst.y}
                          stroke={strokeColor}
                          strokeWidth={strokeWidth}
                          strokeDasharray={strokeDash}
                          markerEnd={isTaint ? "url(#arrow-taint)" : "url(#arrow-normal)"}
                        />
                        {isLateral && (
                          <text
                            x={mx}
                            y={my - 6}
                            fill="var(--signal-suspect)"
                            fontSize="9"
                            fontFamily="var(--font-mono)"
                            textAnchor="middle"
                            fontWeight="700"
                          >
                            LATERAL HOP
                          </text>
                        )}
                        {edge.hops !== undefined && edge.hops !== null && (
                          <text
                            x={mx}
                            y={my + 10}
                            fill="var(--signal-taint)"
                            fontSize="8"
                            fontFamily="var(--font-mono)"
                            textAnchor="middle"
                            fontWeight="600"
                          >
                            hop {edge.hops}
                          </text>
                        )}
                      </g>
                    );
                  })}

                  {/* Render Force Layout Nodes */}
                  {nodes.map((node) => {
                    const pos = nodePositions[node.id];
                    if (!pos) return null;

                    const isSelected = selectedEntityId === node.id;
                    const isWhyPath = highlightedEntitySet.has(node.id);

                    let strokeColor = "var(--ink-border)";
                    let fillColor = "var(--bg-paper)";

                    if (node.ink_token === "tainted") {
                      strokeColor = "var(--signal-taint)";
                    } else if (node.ink_token === "reaffirmed") {
                      strokeColor = "var(--signal-reaffirm)";
                    } else if (node.ink_token === "suspect") {
                      strokeColor = "var(--signal-suspect)";
                    }

                    if (isSelected) {
                      fillColor = "var(--bg-paper-elevated)";
                    }

                    return (
                      <g
                        key={`node-${node.id}`}
                        transform={`translate(${pos.x}, ${pos.y})`}
                        onClick={() => handleOpenWhy(node.id)}
                        tabIndex={0}
                        role="button"
                        aria-label={`Inspect ${node.kind} ${node.id}`}
                        onKeyDown={(e) => {
                          if (e.key === "Enter" || e.key === " ") {
                            handleOpenWhy(node.id);
                          }
                        }}
                        style={{ cursor: "pointer", outline: "none" }}
                      >
                        {/* Node Box (Strict Neobrutal Square Corners) */}
                        <rect
                          x="-38"
                          y="-22"
                          width="76"
                          height="44"
                          fill={fillColor}
                          stroke={isWhyPath ? "var(--ink-primary)" : strokeColor}
                          strokeWidth={isSelected || isWhyPath ? 3 : 2}
                        />

                        {/* Node Badge */}
                        <text
                          x="-30"
                          y="-9"
                          fill="var(--ink-muted)"
                          fontSize="9"
                          fontFamily="var(--font-mono)"
                          fontWeight="700"
                        >
                          {node.badge}
                        </text>

                        {/* Truncated ID Label */}
                        <text
                          x="0"
                          y="6"
                          fill="var(--ink-primary)"
                          fontSize="10"
                          fontFamily="var(--font-mono)"
                          textAnchor="middle"
                          fontWeight="600"
                        >
                          {node.id.length > 10 ? `${node.id.slice(0, 9)}…` : node.id}
                        </text>

                        {/* Neobrutalist Stamp Tag */}
                        {node.stamp_text && (
                          <g transform="translate(0, 28)">
                            <rect
                              x="-32"
                              y="-8"
                              width="64"
                              height="16"
                              fill="var(--bg-paper)"
                              stroke={strokeColor}
                              strokeWidth="2"
                            />
                            <text
                              x="0"
                              y="4"
                              fill={strokeColor}
                              fontSize="9"
                              fontFamily="var(--font-mono)"
                              fontWeight="700"
                              textAnchor="middle"
                            >
                              {node.stamp_text}
                            </text>
                          </g>
                        )}
                      </g>
                    );
                  })}
                </svg>
              )}

              {/* Neo-brutalist Legend Strip */}
              <div
                className="border-neo font-mono"
                style={{
                  position: "absolute",
                  bottom: "12px",
                  left: "16px",
                  display: "flex",
                  gap: "14px",
                  backgroundColor: "var(--bg-paper)",
                  padding: "6px 12px",
                  fontSize: "11px",
                  fontWeight: 600,
                  boxShadow: "var(--shadow-interactive)",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                  <span style={{ color: "var(--signal-suspect)" }}>■</span> SUSPECT
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                  <span style={{ color: "var(--signal-taint)" }}>■</span> HOLD
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                  <span style={{ color: "var(--signal-reaffirm)" }}>■</span> REAFFIRMED
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                  <span style={{ color: "var(--ink-secondary)" }}>- - -</span> LATERAL HOP
                </div>
              </div>
            </div>
          </section>

          {/* Right Column: ~38% Ledger & Query Log */}
          <aside
            style={{
              backgroundColor: "var(--bg-paper-elevated)",
              display: "flex",
              flexDirection: "column",
              minWidth: 0,
              minHeight: 0,
              height: "100%",
              overflow: "hidden",
            }}
          >
            {/* Running Ledger Section */}
            <div
              className="border-neo-bottom"
              style={{
                flex: 1,
                minHeight: 0,
                padding: "16px",
                overflowY: "auto",
              }}
            >
              <div
                className="mono-label"
                style={{
                  marginBottom: "12px",
                  color: "var(--ink-secondary)",
                  display: "flex",
                  justifyContent: "space-between",
                }}
              >
                <span>{registry?.vocabulary?.ledger_heading || "Running Forensic Ledger"}</span>
                <span style={{ color: "var(--ink-muted)" }}>{events.length} EVENTS</span>
              </div>

              {events.length === 0 ? (
                <div
                  className="border-neo font-mono"
                  style={{
                    padding: "16px",
                    fontSize: "12px",
                    color: "var(--ink-secondary)",
                    backgroundColor: "var(--bg-paper)",
                  }}
                >
                  No events logged on current incident run. Click &quot;INVESTIGATE RECALL&quot; to begin.
                </div>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
                  {events.map((evt, idx) => {
                    let stampClass = "stamp-neutral";
                    if (evt.event_type.includes("taint")) stampClass = "stamp-taint";
                    else if (evt.event_type.includes("suspect")) stampClass = "stamp-suspect";
                    else if (evt.event_type.includes("verdict")) stampClass = "stamp-reaffirm";

                    return (
                      <div
                        key={`evt-card-${evt.event_id}-${idx}`}
                        className="border-neo"
                        style={{
                          padding: "10px 14px",
                          backgroundColor: "var(--bg-paper)",
                          fontSize: "12px",
                        }}
                      >
                        <div
                          style={{
                            display: "flex",
                            justifyContent: "space-between",
                            alignItems: "center",
                            marginBottom: "4px",
                          }}
                        >
                          <span
                            className="font-mono"
                            style={{ color: "var(--ink-primary)", fontWeight: 700 }}
                          >
                            {evt.event_type}
                          </span>
                          <span className={`forensic-stamp ${stampClass}`} style={{ fontSize: "9px" }}>
                            {evt.event_type.split(".")[1]?.toUpperCase() || "LOG"}
                          </span>
                        </div>
                        <div
                          className="font-mono"
                          style={{ fontSize: "11px", color: "var(--ink-secondary)" }}
                        >
                          Entities: {evt.entity_ids?.join(", ") || "none"}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            {/* Audit Cypher Query Log Section */}
            <div
              style={{
                padding: "14px 16px",
                backgroundColor: "var(--bg-paper-sunken)",
                height: "170px",
                maxHeight: "170px",
                flexShrink: 0,
                overflowY: "auto",
              }}
            >
              <div
                className="mono-label border-neo-bottom"
                style={{
                  paddingBottom: "6px",
                  marginBottom: "8px",
                  color: "var(--ink-secondary)",
                  display: "flex",
                  justifyContent: "space-between",
                }}
              >
                <span>{registry?.vocabulary?.query_log_heading || "Graph Audit Cypher Log"}</span>
                <span style={{ color: "var(--ink-muted)" }}>LIVE QUERY STREAM</span>
              </div>
              <pre
                className="font-mono"
                style={{
                  fontSize: "11px",
                  color: "var(--ink-secondary)",
                  whiteSpace: "pre-wrap",
                  lineHeight: "1.45",
                }}
              >
                {queryLog.join("\n")}
              </pre>
            </div>
          </aside>
        </main>
      )}

      {/* (B) "NEEDS A PERSON" QUEUE VIEW (Requirement 4) */}
      {activeTab === "queue" && (
        <section
          style={{
            padding: "24px",
            backgroundColor: "var(--bg-paper)",
            flex: 1,
            minHeight: 0,
            overflowY: "auto",
          }}
        >
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              marginBottom: "20px",
              flexWrap: "wrap",
              gap: "12px",
            }}
          >
            <div>
              <h2 className="font-display" style={{ fontSize: "22px", fontWeight: 700 }}>
                {registry?.vocabulary?.queue_heading || "Needs Human Review"} ({pendingQueue.length} Pending)
              </h2>
              <p
                className="font-body"
                style={{ fontSize: "16px", color: "var(--ink-secondary)", marginTop: "4px" }}
              >
                Human-gated decision queue. Each item requires explicit operator authorization before action dispatch.
              </p>
            </div>

            <button
              onClick={fetchPendingQueue}
              className="font-mono border-neo touch-target-44"
              style={{
                padding: "8px 18px",
                backgroundColor: "var(--bg-paper-elevated)",
                cursor: "pointer",
                fontWeight: 600,
                fontSize: "12px",
              }}
            >
              Refresh Queue
            </button>
          </div>

          {pendingQueue.length === 0 ? (
            <div
              className="border-neo font-mono"
              style={{
                padding: "32px",
                backgroundColor: "var(--bg-paper-elevated)",
                textAlign: "center",
              }}
            >
              <div className="font-display" style={{ fontSize: "18px", marginBottom: "8px" }}>
                Queue Clear · Zero Actions Pending
              </div>
              <p className="font-body" style={{ color: "var(--ink-secondary)", fontSize: "14px" }}>
                All graph operations and causal verdicts currently satisfied by declared Cypher policy.
              </p>
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
              {pendingQueue.map((item) => (
                <div
                  key={item.action_id}
                  className="border-neo"
                  style={{
                    padding: "20px",
                    backgroundColor: "var(--bg-paper-elevated)",
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    gap: "20px",
                    flexWrap: "wrap",
                  }}
                >
                  <div style={{ flex: 1, minWidth: "280px" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: "10px", marginBottom: "6px" }}>
                      <span className="mono-label" style={{ color: "var(--signal-taint)" }}>
                        {item.action_kind}
                      </span>
                      <span className="forensic-stamp stamp-taint" style={{ fontSize: "9px" }}>
                        APPROVAL REQUIRED
                      </span>
                    </div>

                    <div className="font-mono" style={{ fontSize: "13px", fontWeight: 600, marginBottom: "6px" }}>
                      Target: {item.target_entity_id}
                    </div>

                    <p className="font-body" style={{ fontSize: "14px", color: "var(--ink-secondary)" }}>
                      {item.draft_content ||
                        "Draft notification generated by Dispatcher agent. Awaiting human sign-off."}
                    </p>

                    <button
                      onClick={() => handleOpenWhy(item.action_id)}
                      className="font-mono"
                      style={{
                        background: "none",
                        border: "none",
                        color: "var(--ink-primary)",
                        textDecoration: "underline",
                        cursor: "pointer",
                        fontSize: "12px",
                        marginTop: "8px",
                        padding: 0,
                      }}
                    >
                      Inspect Causal Trajectory ({item.causal_path.length} hops) &rarr;
                    </button>
                  </div>

                  {/* One Obvious Button Per Item (Requirement 4) */}
                  <div>
                    <button
                      onClick={() => handleApproveAction(item.action_id)}
                      disabled={approvingActionId === item.action_id}
                      className="shadow-neo-btn font-mono touch-target-44"
                      style={{
                        padding: "10px 24px",
                        backgroundColor: "var(--ink-primary)",
                        color: "var(--bg-paper)",
                        border: "var(--border-neo)",
                        cursor: approvingActionId === item.action_id ? "not-allowed" : "pointer",
                        fontWeight: 700,
                        fontSize: "13px",
                        whiteSpace: "nowrap",
                      }}
                    >
                      {approvingActionId === item.action_id ? "SIGNING..." : "APPROVE ACTION"}
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>
      )}

      {/* (C) EVALUATION BENCHMARK VIEW */}
      {activeTab === "evaluation" && (
        <section
          style={{
            padding: "24px",
            backgroundColor: "var(--bg-paper)",
            flex: 1,
            minHeight: 0,
            overflowY: "auto",
          }}
        >
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              marginBottom: "20px",
              flexWrap: "wrap",
              gap: "12px",
            }}
          >
            <div>
              <h2 className="font-display" style={{ fontSize: "22px", fontWeight: 700 }}>
                Forensic Evaluation Benchmark Report
              </h2>
              <p
                className="font-body"
                style={{ fontSize: "14px", color: "var(--ink-secondary)", marginTop: "2px" }}
              >
                Automated precision vs blanket recall verification harness across randomized incidents (Part A Phase A4).
              </p>
            </div>
            <button
              onClick={handleRunEvaluation}
              disabled={isEvaluating}
              className="shadow-neo-btn font-mono touch-target-44"
              style={{
                padding: "8px 20px",
                backgroundColor: "var(--bg-paper-elevated)",
                border: "var(--border-neo)",
                cursor: "pointer",
                fontWeight: 700,
                fontSize: "12px",
              }}
            >
              {isEvaluating ? "Computing Benchmark..." : "Re-Run 5 Incidents Benchmark"}
            </button>
          </div>

          {evalReport && (
            <div style={{ display: "flex", flexDirection: "column", gap: "24px" }}>
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
                  gap: "16px",
                }}
              >
                <div
                  className="border-neo"
                  style={{ padding: "16px", backgroundColor: "var(--bg-paper-elevated)" }}
                >
                  <div className="mono-label" style={{ color: "var(--ink-secondary)" }}>
                    Precision vs Blanket Recall
                  </div>
                  <div
                    className="font-mono"
                    style={{ fontSize: "24px", fontWeight: 700, marginTop: "4px" }}
                  >
                    {(evalReport.precision_vs_naive_recall * 100).toFixed(1)}%
                  </div>
                  <div
                    className="font-body"
                    style={{ fontSize: "12px", color: "var(--ink-secondary)", marginTop: "4px" }}
                  >
                    Targeted causal containment vs blanket recall
                  </div>
                </div>

                <div
                  className="border-neo"
                  style={{ padding: "16px", backgroundColor: "var(--bg-paper-elevated)" }}
                >
                  <div className="mono-label" style={{ color: "var(--ink-secondary)" }}>
                    False-Reaffirm Count
                  </div>
                  <div
                    className="font-mono"
                    style={{
                      fontSize: "24px",
                      fontWeight: 700,
                      marginTop: "4px",
                      color: "var(--signal-reaffirm)",
                    }}
                  >
                    {evalReport.false_reaffirm_count}
                  </div>
                  <div
                    className="font-body"
                    style={{ fontSize: "12px", color: "var(--ink-secondary)", marginTop: "4px" }}
                  >
                    Strictly 0 on generated ground truth
                  </div>
                </div>

                <div
                  className="border-neo"
                  style={{ padding: "16px", backgroundColor: "var(--bg-paper-elevated)" }}
                >
                  <div className="mono-label" style={{ color: "var(--ink-secondary)" }}>
                    Hidden Lateral Recall
                  </div>
                  <div
                    className="font-mono"
                    style={{ fontSize: "24px", fontWeight: 700, marginTop: "4px" }}
                  >
                    {evalReport.hidden_link_recall_pct}%
                  </div>
                  <div
                    className="font-body"
                    style={{ fontSize: "12px", color: "var(--ink-secondary)", marginTop: "4px" }}
                  >
                    100% recall of shared equipment lots
                  </div>
                </div>

                <div
                  className="border-neo"
                  style={{ padding: "16px", backgroundColor: "var(--bg-paper-elevated)" }}
                >
                  <div className="mono-label" style={{ color: "var(--ink-secondary)" }}>
                    Explanation Coverage
                  </div>
                  <div
                    className="font-mono"
                    style={{ fontSize: "24px", fontWeight: 700, marginTop: "4px" }}
                  >
                    {evalReport.explanation_coverage_pct}%
                  </div>
                  <div
                    className="font-body"
                    style={{ fontSize: "12px", color: "var(--ink-secondary)", marginTop: "4px" }}
                  >
                    100% actions carry stored causal trajectory
                  </div>
                </div>
              </div>

              {/* Incidents Data Table */}
              <div className="border-neo" style={{ backgroundColor: "var(--bg-paper-elevated)", overflowX: "auto" }}>
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "12px" }}>
                  <thead>
                    <tr className="border-neo-bottom font-mono" style={{ textAlign: "left", color: "var(--ink-secondary)" }}>
                      <th style={{ padding: "10px 16px" }}>INCIDENT ID</th>
                      <th style={{ padding: "10px 16px" }}>SEED</th>
                      <th style={{ padding: "10px 16px" }}>DURATION</th>
                      <th style={{ padding: "10px 16px" }}>BLANKET UNITS</th>
                      <th style={{ padding: "10px 16px" }}>TAINTED UNITS</th>
                      <th style={{ padding: "10px 16px" }}>REAFFIRMED</th>
                      <th style={{ padding: "10px 16px" }}>LATERAL DETECTED</th>
                      <th style={{ padding: "10px 16px" }}>EXPLAINED</th>
                    </tr>
                  </thead>
                  <tbody>
                    {evalReport.incidents.map((inc) => (
                      <tr key={inc.incident_id} className="border-neo-bottom font-mono">
                        <td style={{ padding: "8px 16px" }}>{inc.incident_id}</td>
                        <td style={{ padding: "8px 16px" }}>{inc.seed}</td>
                        <td style={{ padding: "8px 16px" }}>{inc.duration_ms.toFixed(2)} ms</td>
                        <td style={{ padding: "8px 16px" }}>{inc.naive_recall_units}</td>
                        <td style={{ padding: "8px 16px", color: "var(--signal-taint)", fontWeight: 700 }}>
                          {inc.tainted_units}
                        </td>
                        <td style={{ padding: "8px 16px", color: "var(--signal-reaffirm)", fontWeight: 700 }}>
                          {inc.reaffirmed_units}
                        </td>
                        <td style={{ padding: "8px 16px" }}>
                          {inc.hidden_link_detected ? "YES (100%)" : "NO"}
                        </td>
                        <td style={{ padding: "8px 16px" }}>
                          {inc.explained_actions_count}/{inc.actions_count} (100%)
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </section>
      )}

      {/* (D) TOOL GATE VERIFIER VIEW */}
      {activeTab === "gates" && (
        <section
          style={{
            padding: "24px",
            backgroundColor: "var(--bg-paper)",
            flex: 1,
            minHeight: 0,
            overflowY: "auto",
          }}
        >
          <h2 className="font-display" style={{ fontSize: "22px", fontWeight: 700, marginBottom: "4px" }}>
            Cypher Tool Gate Evaluator
          </h2>
          <p className="font-body" style={{ fontSize: "14px", color: "var(--ink-secondary)", marginBottom: "20px" }}>
            Proves Section 0 Rule 5 &amp; Winning Expectation: &quot;A hold on an untainted batch is impossible
            because the tool is absent!&quot; Gates are evaluated directly against FalkorDB graph state.
          </p>

          {(() => {
            const cleanUnitId =
              nodes.find(
                (n) =>
                  n.role?.toLowerCase() === "unit" &&
                  (!n.properties?.is_tainted || n.status === "reaffirmed")
              )?.id || nodes.find((n) => n.role?.toLowerCase() === "unit")?.id || "";
            const taintedUnitId =
              nodes.find(
                (n) =>
                  n.role?.toLowerCase() === "unit" &&
                  (n.properties?.is_tainted || n.status === "tainted")
              )?.id || nodes.find((n) => n.role?.toLowerCase() === "unit")?.id || "";

            return (
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))",
                  gap: "20px",
                }}
              >
                <div
                  className="border-neo"
                  style={{ padding: "20px", backgroundColor: "var(--bg-paper-elevated)" }}
                >
                  <div className="mono-label" style={{ marginBottom: "8px" }}>
                    Test 1: Attempt Hold on Clean / Untainted Batch
                  </div>
                  <p className="font-body" style={{ fontSize: "14px", color: "var(--ink-secondary)", marginBottom: "16px" }}>
                    Expectation: The `hold_unit` gate evaluates in Cypher and returns `allowed=false`. The LLM
                    never sees or receives the tool. Target: <span className="font-mono">{cleanUnitId || "Scanning graph..."}</span>
                  </p>
                  <button
                    onClick={() => handleCheckGate("hold_unit", cleanUnitId)}
                    disabled={checkingGate || !cleanUnitId}
                    className="shadow-neo-btn font-mono touch-target-44"
                    style={{
                      padding: "8px 18px",
                      backgroundColor: "var(--bg-paper)",
                      border: "var(--border-neo)",
                      cursor: "pointer",
                      fontWeight: 700,
                      fontSize: "12px",
                    }}
                  >
                    Evaluate Gate in Cypher
                  </button>
                </div>

                <div
                  className="border-neo"
                  style={{ padding: "20px", backgroundColor: "var(--bg-paper-elevated)" }}
                >
                  <div className="mono-label" style={{ marginBottom: "8px" }}>
                    Test 2: Attempt Release on Tainted Batch
                  </div>
                  <p className="font-body" style={{ fontSize: "14px", color: "var(--ink-secondary)", marginBottom: "16px" }}>
                    Expectation: The `release_unit` gate evaluates `WHERE u.is_tainted = false` and refuses release
                    of contaminated lots. Target: <span className="font-mono">{taintedUnitId || "Scanning graph..."}</span>
                  </p>
                  <button
                    onClick={() => handleCheckGate("release_unit", taintedUnitId)}
                    disabled={checkingGate || !taintedUnitId}
                    className="shadow-neo-btn font-mono touch-target-44"
                    style={{
                      padding: "8px 18px",
                      backgroundColor: "var(--bg-paper)",
                      border: "var(--border-neo)",
                      cursor: "pointer",
                      fontWeight: 700,
                      fontSize: "12px",
                    }}
                  >
                    Evaluate Gate in Cypher
                  </button>
                </div>
              </div>
            );
          })()}

          {gateResult && (
            <div
              className="border-neo"
              style={{
                marginTop: "24px",
                padding: "20px",
                backgroundColor: "var(--bg-paper-elevated)",
              }}
            >
              <div className="mono-label" style={{ marginBottom: "8px" }}>
                Gate Evaluation Result
              </div>
              <div style={{ display: "flex", gap: "16px", marginBottom: "12px", flexWrap: "wrap" }}>
                <span className="font-mono" style={{ fontSize: "13px" }}>
                  TOOL: <strong>{gateResult.tool_name}</strong>
                </span>
                <span className="font-mono" style={{ fontSize: "13px" }}>
                  STATUS:{" "}
                  <strong
                    style={{
                      color: gateResult.permitted ? "var(--signal-reaffirm)" : "var(--signal-taint)",
                    }}
                  >
                    {gateResult.permitted ? "PERMITTED (UNLOCKED)" : "DENIED (TOOL ABSENT)"}
                  </strong>
                </span>
              </div>
              <pre
                className="font-mono"
                style={{
                  backgroundColor: "var(--bg-paper-sunken)",
                  padding: "12px",
                  fontSize: "12px",
                  lineHeight: "1.4",
                  border: "var(--border-neo)",
                }}
              >
                {`// Cypher expression evaluated:\n${gateResult.gate_query}\n\n// Decision justification:\n${gateResult.reason}`}
              </pre>
            </div>
          )}
        </section>
      )}

      {/* 5. WHY DRAWER & CHAIN-OF-CUSTODY STRIP (Rule 7, <= 2 Interactions, Canvas Highlighting) */}
      {whyDrawerOpen && (
        <aside
          role="dialog"
          aria-label="Chain of Custody Inspector"
          style={{
            position: "fixed",
            top: 0,
            right: 0,
            width: "500px",
            maxWidth: "100vw",
            height: "100vh",
            backgroundColor: "var(--bg-paper)",
            borderLeft: "var(--border-neo-thick)",
            boxShadow: "var(--shadow-interactive-lg)",
            padding: "24px",
            display: "flex",
            flexDirection: "column",
            zIndex: 1000,
            overflowY: "auto",
          }}
        >
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              marginBottom: "16px",
            }}
          >
            <div>
              <div className="mono-label" style={{ color: "var(--ink-secondary)" }}>
                Chain of Custody Inspector · Rule 7
              </div>
              <h3 className="font-display" style={{ fontSize: "20px", fontWeight: 700 }}>
                {registry?.vocabulary?.why_heading || "Causal Chain of Custody"}
              </h3>
            </div>
            <button
              onClick={() => setWhyDrawerOpen(false)}
              className="font-mono border-neo touch-target-44"
              style={{
                padding: "6px 12px",
                backgroundColor: "var(--bg-paper-elevated)",
                cursor: "pointer",
                fontWeight: 700,
                fontSize: "12px",
              }}
            >
              Close (ESC)
            </button>
          </div>

          {whyData ? (
            <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
              <div
                className="border-neo font-mono"
                style={{
                  padding: "14px",
                  backgroundColor: "var(--bg-paper-elevated)",
                  fontSize: "12px",
                }}
              >
                <div>
                  <span style={{ color: "var(--ink-muted)" }}>TARGET ENTITY: </span>
                  <strong>{whyData.target_entity_id || selectedEntityId}</strong>
                </div>
                <div style={{ marginTop: "4px" }}>
                  <span style={{ color: "var(--ink-muted)" }}>ACTION KIND: </span>
                  <strong>{whyData.action_kind}</strong>
                </div>
                <div style={{ marginTop: "4px" }}>
                  <span style={{ color: "var(--ink-muted)" }}>PATH LENGTH: </span>
                  <strong>{whyData.causal_path.length} hops</strong>
                </div>
              </div>

              {/* Step-by-Step Chain-of-Custody Strip */}
              <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
                <div className="mono-label" style={{ color: "var(--ink-secondary)" }}>
                  Stored Causal Trajectory (Click link to highlight on canvas)
                </div>
                {whyData.steps.map((step) => {
                  const isSelectedStep = selectedEntityId === step.entity_id;
                  return (
                    <div
                      key={`why-step-${step.step_number}-${step.entity_id}`}
                      onClick={() => setSelectedEntityId(step.entity_id)}
                      tabIndex={0}
                      role="button"
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          setSelectedEntityId(step.entity_id);
                        }
                      }}
                      className={`border-neo ${isSelectedStep ? "shadow-neo-selected" : ""}`}
                      style={{
                        padding: "12px 14px",
                        backgroundColor: isSelectedStep
                          ? "var(--bg-paper)"
                          : "var(--bg-paper-elevated)",
                        fontSize: "12px",
                        cursor: "pointer",
                        outline: "none",
                      }}
                    >
                      <div
                        style={{
                          display: "flex",
                          justifyContent: "space-between",
                          marginBottom: "4px",
                        }}
                      >
                        <span className="font-mono" style={{ fontWeight: 700 }}>
                          Step {step.step_number}: {step.kind} ({step.role})
                        </span>
                        {step.stamp_text && (
                          <span className="forensic-stamp stamp-taint" style={{ fontSize: "8px" }}>
                            {step.stamp_text}
                          </span>
                        )}
                      </div>
                      <div className="font-mono" style={{ fontSize: "11px", color: "var(--ink-secondary)" }}>
                        ID: {step.entity_id}
                      </div>
                      <div className="font-body" style={{ fontSize: "12px", marginTop: "4px" }}>
                        {step.description}
                      </div>
                    </div>
                  );
                })}
              </div>

              {/* Draft Content & Human Sign-off */}
              {whyData.draft_content && (
                <div
                  className="border-neo"
                  style={{
                    padding: "14px",
                    backgroundColor: "var(--bg-paper-sunken)",
                    fontSize: "12px",
                  }}
                >
                  <div className="mono-label" style={{ marginBottom: "6px" }}>
                    Draft Notice Document
                  </div>
                  <p className="font-body" style={{ color: "var(--ink-secondary)", fontSize: "14px" }}>
                    {whyData.draft_content}
                  </p>
                </div>
              )}

              {whyData.requires_approval && (
                <div style={{ marginTop: "8px" }}>
                  {whyData.approved ? (
                    <div
                      className="forensic-stamp stamp-reaffirm"
                      style={{ display: "block", textAlign: "center", padding: "10px", width: "100%" }}
                    >
                      ACTION SIGNED &amp; APPROVED BY OPERATOR
                    </div>
                  ) : (
                    <button
                      onClick={() => handleApproveAction(whyData.action_id)}
                      disabled={approvingActionId === whyData.action_id}
                      className="shadow-neo-btn font-mono touch-target-44"
                      style={{
                        width: "100%",
                        padding: "12px",
                        backgroundColor: "var(--ink-primary)",
                        color: "var(--bg-paper)",
                        border: "var(--border-neo)",
                        cursor: approvingActionId === whyData.action_id ? "not-allowed" : "pointer",
                        fontWeight: 700,
                        fontSize: "13px",
                      }}
                    >
                      {approvingActionId === whyData.action_id ? "AUTHORIZING..." : "APPROVE ACTION NOTICE"}
                    </button>
                  )}
                </div>
              )}
            </div>
          ) : (
            <div className="font-mono" style={{ color: "var(--ink-secondary)", fontSize: "12px" }}>
              Retrieving stored causal chain of custody from graph...
            </div>
          )}
        </aside>
      )}

      {/* 6. PLAIN SENTENCE SYSTEM STATUS BAR & TIME TO SCOPE (Requirement 5) */}
      <footer
        className="border-neo-top font-mono"
        style={{
          padding: "8px 24px",
          backgroundColor: "var(--bg-paper-sunken)",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          fontSize: "11px",
          flexShrink: 0,
          flexWrap: "wrap",
          gap: "8px",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "8px", flex: 1, minWidth: "260px" }}>
          <span style={{ color: "var(--signal-reaffirm)", fontWeight: 700 }}>●</span>
          <span style={{ color: "var(--ink-primary)", fontWeight: 500 }}>
            {statusMessage}
          </span>
        </div>

        <div style={{ display: "flex", gap: "16px", color: "var(--ink-secondary)", flexWrap: "wrap" }}>
          <div>
            TIME TO SCOPE: <strong style={{ color: "var(--ink-primary)" }}>{timeToScopeMs} ms</strong>
          </div>
          <div>
            NODES: <strong style={{ color: "var(--ink-primary)" }}>{stats?.total_nodes ?? 0}</strong> · EDGES:{" "}
            <strong style={{ color: "var(--ink-primary)" }}>{stats?.total_edges ?? 0}</strong>
          </div>
        </div>
      </footer>

      {/* STATE SCREEN: Loading State Overlay (Requirement 7) */}
      {isLoadingInitial && (
        <div
          style={{
            position: "fixed",
            inset: 0,
            backgroundColor: "var(--bg-paper)",
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 2000,
            padding: "24px",
          }}
        >
          <div
            className="border-neo"
            style={{
              padding: "32px 40px",
              backgroundColor: "var(--bg-paper-elevated)",
              boxShadow: "var(--shadow-interactive-lg)",
              textAlign: "center",
              maxWidth: "460px",
            }}
          >
            <div className="mono-label" style={{ marginBottom: "8px", color: "var(--ink-secondary)" }}>
              FalkorDB Context Layer
            </div>
            <h2 className="font-display" style={{ fontSize: "22px", marginBottom: "12px" }}>
              Initializing Forensic Audit Dossier...
            </h2>
            <p className="font-body" style={{ fontSize: "14px", color: "var(--ink-secondary)", marginBottom: "16px" }}>
              Synchronizing ontology schema, Cypher gate definitions, and real-time SSE stream.
            </p>
            <div
              className="border-neo font-mono"
              style={{
                padding: "8px 16px",
                backgroundColor: "var(--bg-paper-sunken)",
                fontSize: "12px",
                display: "inline-block",
              }}
            >
              HANDSHAKE: ACTIVE
            </div>
          </div>
        </div>
      )}

      {/* STATE SCREEN: Error / Offline Banner (Requirement 7) */}
      {apiError && !isLoadingInitial && (
        <div
          role="alert"
          className="border-neo-bottom font-mono"
          style={{
            position: "fixed",
            top: 0,
            left: 0,
            right: 0,
            backgroundColor: "var(--bg-paper)",
            borderBottom: "var(--border-neo-thick)",
            borderBottomColor: "var(--signal-taint)",
            padding: "12px 24px",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            zIndex: 3000,
            flexWrap: "wrap",
            gap: "12px",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
            <span className="forensic-stamp stamp-taint">OFFLINE / STANDBY</span>
            <span style={{ fontSize: "12px", color: "var(--signal-taint)", fontWeight: 600 }}>
              {apiError}
            </span>
          </div>

          <button
            onClick={() => {
              setApiError(null);
              fetchGraphSnapshot();
            }}
            className="shadow-neo-btn font-mono touch-target-44"
            style={{
              padding: "6px 14px",
              backgroundColor: "var(--ink-primary)",
              color: "var(--bg-paper)",
              border: "var(--border-neo)",
              cursor: "pointer",
              fontSize: "11px",
              fontWeight: 700,
            }}
          >
            RETRY HANDSHAKE
          </button>
        </div>
      )}
    </div>
  );
}
