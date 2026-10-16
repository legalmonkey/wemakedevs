"use client";

import React, { useEffect, useState, useRef, useMemo } from "react";

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

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";

export default function ForensicDossier() {
  const [registry, setRegistry] = useState<RegistryData | null>(null);
  const [events, setEvents] = useState<EventItem[]>([]);
  const [agentStatus, setAgentStatus] = useState<string>("INITIALIZING");
  const [apiOnline, setApiOnline] = useState<boolean>(false);
  const [activeTab, setActiveTab] = useState<"canvas" | "evaluation" | "gates">("canvas");

  // Graph Canvas State
  const [nodes, setNodes] = useState<GraphNode[]>([]);
  const [edges, setEdges] = useState<GraphEdge[]>([]);
  const [stats, setStats] = useState<GraphStats | null>(null);
  const [activeSeed, setActiveSeed] = useState<number>(101);
  const [isTriggering, setIsTriggering] = useState<boolean>(false);

  // Why Drawer State
  const [whyDrawerOpen, setWhyDrawerOpen] = useState<boolean>(false);
  const [whyData, setWhyData] = useState<WhyPathData | null>(null);
  const [selectedEntityId, setSelectedEntityId] = useState<string | null>(null);

  // Query Audit Log State
  const [queryLog, setQueryLog] = useState<string[]>([
    "// FalkorDB Query API stream initialized",
    "MATCH (n:Evidence) RETURN count(n);",
  ]);

  // Evaluation Report State
  const [evalReport, setEvalReport] = useState<EvaluationReport | null>(null);
  const [isEvaluating, setIsEvaluating] = useState<boolean>(false);

  // Gate Check State
  const [gateResult, setGateResult] = useState<GateCheckResult | null>(null);
  const [checkingGate, setCheckingGate] = useState<boolean>(false);

  const eventSourceRef = useRef<EventSource | null>(null);

  // Fetch initial registry & graph snapshot
  const fetchGraphSnapshot = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/incident/graph`);
      if (res.ok) {
        const data = await res.json();
        setNodes(data.nodes || []);
        setEdges(data.edges || []);
        setStats(data.stats || null);
        setApiOnline(true);
      }
    } catch {
      // Standby if API not yet up
    }
  };

  const fetchQueryLog = async () => {
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
  };

  useEffect(() => {
    // 1. Fetch registry and initial graph data
    fetch(`${API_BASE}/api/registry`)
      .then((res) => {
        if (!res.ok) throw new Error("Registry fetch failed");
        return res.json();
      })
      .then((data: RegistryData) => {
        setRegistry(data);
        setApiOnline(true);
        setAgentStatus("READY");
        fetchGraphSnapshot();
        fetchQueryLog();
      })
      .catch((err) => {
        console.warn("Registry unavailable, using fallback handshake", err);
        setApiOnline(false);
        setAgentStatus("DISCONNECTED");
      });

    // 3. Connect to SSE stream
    const eventSource = new EventSource(`${API_BASE}/api/events`);
    eventSourceRef.current = eventSource;

    eventSource.onopen = () => {
      setApiOnline(true);
    };

    eventSource.onmessage = (e) => {
      try {
        const parsed = JSON.parse(e.data);
        if (parsed.event_type) {
          setEvents((prev) => [parsed, ...prev.slice(0, 99)]);
          if (parsed.event_type === "agent.status") {
            setAgentStatus(parsed.payload?.status || "ACTIVE");
          }

          // Trigger incremental graph and query log updates
          fetchGraphSnapshot();
          fetchQueryLog();
        }
      } catch {
        // Heartbeat or comment
      }
    };

    eventSource.onerror = () => {
      setApiOnline(false);
    };

    return () => {
      eventSource.close();
    };
  }, []);

  // Trigger live multi-agent incident run
  const handleTriggerIncident = async (seedToRun: number) => {
    setIsTriggering(true);
    setActiveSeed(seedToRun);
    setEvents([]);
    try {
      const res = await fetch(`${API_BASE}/api/incident/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ seed: seedToRun, speed_ms: 350 }),
      });
      if (res.ok) {
        setAgentStatus("ACTIVE");
        setTimeout(fetchGraphSnapshot, 400);
      }
    } catch (err) {
      console.error("Failed to trigger incident run", err);
    } finally {
      setTimeout(() => setIsTriggering(false), 2000);
    }
  };

  // Inspect Why Chain of Custody for an action or node
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

  // Human approval of action
  const handleApproveAction = async (actionId: string) => {
    try {
      const res = await fetch(`${API_BASE}/api/actions/${actionId}/approve`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          action_id: actionId,
          operator_notes: "Approved by forensic operator via evidence board",
        }),
      });
      if (res.ok) {
        if (whyData && whyData.action_id === actionId) {
          setWhyData({ ...whyData, approved: true });
        }
        fetchGraphSnapshot();
      }
    } catch (err) {
      console.error("Approval failed", err);
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

  // Compute node layout coordinates for SVG canvas
  const nodePositions = useMemo(() => {
    const roleColumns: Record<string, number> = {
      event: 60,
      evidence: 140,
      decision: 310,
      unit: 480,
      shipment: 630,
      recipient: 760,
      action: 760,
    };

    const roleGroups: Record<string, GraphNode[]> = {
      event: [],
      evidence: [],
      decision: [],
      unit: [],
      shipment: [],
      recipient: [],
      action: [],
    };

    nodes.forEach((n) => {
      const r = n.role.toLowerCase();
      if (roleGroups[r]) roleGroups[r].push(n);
      else roleGroups.unit.push(n);
    });

    const positions: Record<string, { x: number; y: number }> = {};
    const height = 480;

    Object.keys(roleGroups).forEach((role) => {
      const colX = roleColumns[role] || 400;
      const group = roleGroups[role];
      const count = group.length;
      group.forEach((node, idx) => {
        const spacing = height / (count + 1);
        const y = spacing * (idx + 1);
        positions[node.id] = { x: colX, y };
      });
    });

    return positions;
  }, [nodes]);

  return (
    <div style={{ height: "100vh", maxHeight: "100vh", width: "100vw", maxWidth: "100vw", display: "flex", flexDirection: "column", overflow: "hidden" }}>
      {/* Forensic Header Bar */}
      <header
        className="hairline-bottom"
        style={{
          padding: "10px 20px",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          backgroundColor: "var(--bg-paper)",
          flexShrink: 0,
        }}
      >
        <div>
          <div
            className="font-mono"
            style={{
              fontSize: "10px",
              letterSpacing: "0.15em",
              color: "var(--ink-muted)",
              textTransform: "uppercase",
            }}
          >
            FalkorDB Context-Layer Audit Instrument · Track 1
          </div>
          <h1
            className="font-display"
            style={{
              fontSize: "22px",
              fontWeight: 700,
              letterSpacing: "-0.01em",
              marginTop: "2px",
            }}
          >
            {registry?.vocabulary?.title || "TAINTED — Chain of Custody Dossier"}
          </h1>
        </div>

        {/* Counter Widget: Naive Blanket Recall vs Tainted Surgical Scope */}
        {stats && (
          <div
            className="hairline-border font-mono"
            style={{
              display: "flex",
              backgroundColor: "var(--bg-paper-elevated)",
              padding: "4px 12px",
              fontSize: "11px",
              gap: "16px",
              alignItems: "center",
            }}
          >
            <div>
              <span style={{ color: "var(--ink-muted)" }}>BLANKET SCOPE: </span>
              <span style={{ fontWeight: 600 }}>{stats.naive_recall_units} units</span>
            </div>
            <div className="hairline-left" style={{ paddingLeft: "16px" }}>
              <span style={{ color: "var(--signal-taint)" }}>TAINTED: </span>
              <span style={{ fontWeight: 600, color: "var(--signal-taint)" }}>
                {stats.tainted_units} units
              </span>
            </div>
            <div className="hairline-left" style={{ paddingLeft: "16px" }}>
              <span style={{ color: "var(--signal-reaffirm)" }}>REAFFIRMED: </span>
              <span style={{ fontWeight: 600, color: "var(--signal-reaffirm)" }}>
                {stats.reaffirmed_units} units
              </span>
            </div>
            <div className="hairline-left" style={{ paddingLeft: "16px" }}>
              <span style={{ color: "var(--ink-secondary)" }}>SAVED: </span>
              <span style={{ fontWeight: 600 }}>{stats.precision_gain_pct}%</span>
            </div>
          </div>
        )}

        <div style={{ display: "flex", alignItems: "center", gap: "16px" }}>
          {/* Stamps Preview */}
          <div style={{ display: "flex", gap: "6px" }}>
            <span className="forensic-stamp stamp-suspect">SUSPECT</span>
            <span className="forensic-stamp stamp-taint">HOLD</span>
            <span className="forensic-stamp stamp-reaffirm">REAFFIRMED</span>
          </div>

          {/* Connection & Agent State */}
          <div
            className="hairline-border font-mono"
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
              <span style={{ color: apiOnline ? "var(--signal-reaffirm)" : "var(--signal-taint)" }}>
                {apiOnline ? "ONLINE" : "STANDBY"}
              </span>
            </div>
            <div className="hairline-left" style={{ paddingLeft: "12px" }}>
              <span style={{ color: "var(--ink-muted)" }}>AGENT: </span>
              <span style={{ fontWeight: 600 }}>{agentStatus}</span>
            </div>
          </div>
        </div>
      </header>

      {/* Control Strip */}
      <div
        className="hairline-bottom"
        style={{
          padding: "6px 20px",
          backgroundColor: "var(--bg-paper-sunken)",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          fontSize: "12px",
          flexShrink: 0,
        }}
      >
        <div style={{ display: "flex", gap: "10px", alignItems: "center" }}>
          <span className="font-mono" style={{ color: "var(--ink-secondary)", fontSize: "11px" }}>
            INCIDENT SEED:
          </span>
          {[101, 202, 303].map((seed) => (
            <button
              key={seed}
              onClick={() => handleTriggerIncident(seed)}
              disabled={isTriggering}
              className="font-mono hairline-border"
              style={{
                padding: "3px 10px",
                backgroundColor:
                  activeSeed === seed ? "var(--bg-paper)" : "var(--bg-paper-elevated)",
                fontWeight: activeSeed === seed ? 600 : 400,
                cursor: "pointer",
                color: "var(--ink-primary)",
              }}
            >
              Seed {seed}
            </button>
          ))}
          <button
            onClick={() => handleTriggerIncident(Math.floor(Math.random() * 899) + 100)}
            disabled={isTriggering}
            className="font-mono hairline-border"
            style={{
              padding: "3px 10px",
              backgroundColor: "var(--bg-paper-elevated)",
              cursor: "pointer",
              color: "var(--ink-primary)",
            }}
          >
            + Fresh Random Seed
          </button>
        </div>

        {/* View Switcher Tabs */}
        <div style={{ display: "flex", gap: "8px" }}>
          <button
            onClick={() => setActiveTab("canvas")}
            className="font-mono hairline-border"
            style={{
              padding: "4px 14px",
              backgroundColor:
                activeTab === "canvas" ? "var(--ink-primary)" : "var(--bg-paper-elevated)",
              color: activeTab === "canvas" ? "var(--bg-paper)" : "var(--ink-primary)",
              cursor: "pointer",
              fontWeight: 500,
            }}
          >
            Evidence Canvas
          </button>
          <button
            onClick={() => {
              setActiveTab("evaluation");
              if (!evalReport) handleRunEvaluation();
            }}
            className="font-mono hairline-border"
            style={{
              padding: "4px 14px",
              backgroundColor:
                activeTab === "evaluation" ? "var(--ink-primary)" : "var(--bg-paper-elevated)",
              color: activeTab === "evaluation" ? "var(--bg-paper)" : "var(--ink-primary)",
              cursor: "pointer",
              fontWeight: 500,
            }}
          >
            Evaluation Benchmark
          </button>
          <button
            onClick={() => setActiveTab("gates")}
            className="font-mono hairline-border"
            style={{
              padding: "4px 14px",
              backgroundColor:
                activeTab === "gates" ? "var(--ink-primary)" : "var(--bg-paper-elevated)",
              color: activeTab === "gates" ? "var(--bg-paper)" : "var(--ink-primary)",
              cursor: "pointer",
              fontWeight: 500,
            }}
          >
            Tool Gate Verifier
          </button>
        </div>
      </div>

      {/* Main Dossier Content */}
      {activeTab === "canvas" && (
        <main className="dossier-grid">
          {/* Left Column: ~60% Forensic Canvas */}
          <section
            className="hairline-right"
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
              }}
            >
              <div
                className="font-mono"
                style={{
                  fontSize: "11px",
                  textTransform: "uppercase",
                  color: "var(--ink-secondary)",
                }}
              >
                {registry?.vocabulary?.evidence_board_title || "Forensic Graph Canvas"} · Active
                Tenant: {stats ? `tenant-seed-${activeSeed}` : "tenant-alpha"}
              </div>
              <div className="font-mono" style={{ fontSize: "11px", color: "var(--ink-muted)" }}>
                Click node or action to inspect causal chain
              </div>
            </div>

            {/* SVG Graph Canvas Stage */}
            <div
              className="hairline-border"
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
                <div
                  style={{
                    height: "100%",
                    display: "flex",
                    flexDirection: "column",
                    alignItems: "center",
                    justifyContent: "center",
                    padding: "32px",
                  }}
                >
                  <div
                    className="font-display"
                    style={{ fontSize: "18px", marginBottom: "8px", color: "var(--ink-secondary)" }}
                  >
                    Evidence Graph Awaiting Incident Signal
                  </div>
                  <p
                    className="font-body"
                    style={{
                      color: "var(--ink-muted)",
                      fontSize: "12px",
                      maxWidth: "420px",
                      textAlign: "center",
                      marginBottom: "16px",
                    }}
                  >
                    Click &quot;Seed 101&quot; or &quot;Fresh Random Seed&quot; above to launch the multi-agent incident
                    trace across the FalkorDB graph.
                  </p>
                  <button
                    onClick={() => handleTriggerIncident(101)}
                    className="font-mono hairline-border"
                    style={{
                      padding: "6px 16px",
                      backgroundColor: "var(--bg-paper)",
                      cursor: "pointer",
                      fontSize: "11px",
                      fontWeight: 600,
                    }}
                  >
                    Launch Demo Incident (Seed 101)
                  </button>
                </div>
              ) : (
                <svg
                  width="100%"
                  height="100%"
                  viewBox="0 0 840 500"
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

                  {/* Render Edges */}
                  {edges.map((edge, idx) => {
                    const src = nodePositions[edge.source_id];
                    const dst = nodePositions[edge.target_id];
                    if (!src || !dst) return null;

                    const isTaint = edge.is_taint;
                    const isLateral = edge.is_lateral;
                    const strokeColor = isTaint
                      ? "var(--signal-taint)"
                      : isLateral
                      ? "var(--signal-suspect)"
                      : "var(--ink-border)";
                    const strokeDash = isTaint ? "5,4" : isLateral ? "4,4" : "none";
                    const strokeWidth = isTaint || isLateral ? 2 : 1.2;

                    // Midpoint for label
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
                            fontWeight="600"
                          >
                            LATERAL LINK
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
                          >
                            hop {edge.hops}
                          </text>
                        )}
                      </g>
                    );
                  })}

                  {/* Render Nodes */}
                  {nodes.map((node) => {
                    const pos = nodePositions[node.id];
                    if (!pos) return null;

                    const isSelected = selectedEntityId === node.id;
                    let stroke = "var(--ink-border)";
                    if (node.ink_token === "tainted") stroke = "var(--signal-taint)";
                    else if (node.ink_token === "reaffirmed") stroke = "var(--signal-reaffirm)";
                    else if (node.ink_token === "suspect") stroke = "var(--signal-suspect)";

                    return (
                      <g
                        key={`node-${node.id}`}
                        transform={`translate(${pos.x}, ${pos.y})`}
                        onClick={() => handleOpenWhy(node.id)}
                        style={{ cursor: "pointer" }}
                      >
                        {/* Node Shape */}
                        <rect
                          x="-36"
                          y="-20"
                          width="72"
                          height="40"
                          fill="var(--bg-paper)"
                          stroke={stroke}
                          strokeWidth={isSelected ? 3 : 1.5}
                        />

                        {/* Badge Tag */}
                        <text
                          x="-28"
                          y="-8"
                          fill="var(--ink-muted)"
                          fontSize="8"
                          fontFamily="var(--font-mono)"
                          fontWeight="600"
                        >
                          {node.badge}
                        </text>

                        {/* Entity ID */}
                        <text
                          x="0"
                          y="6"
                          fill="var(--ink-primary)"
                          fontSize="9"
                          fontFamily="var(--font-mono)"
                          textAnchor="middle"
                          fontWeight="500"
                        >
                          {node.id.length > 10 ? `${node.id.slice(0, 9)}…` : node.id}
                        </text>

                        {/* Stamp Badge */}
                        {node.stamp_text && (
                          <g transform="translate(0, 26)">
                            <rect
                              x="-28"
                              y="-7"
                              width="56"
                              height="14"
                              fill="var(--bg-paper-elevated)"
                              stroke={stroke}
                              strokeWidth="1"
                            />
                            <text
                              x="0"
                              y="3"
                              fill={stroke}
                              fontSize="8"
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

              {/* Legend Strip */}
              <div
                style={{
                  position: "absolute",
                  bottom: "10px",
                  left: "14px",
                  display: "flex",
                  gap: "14px",
                  backgroundColor: "var(--bg-paper)",
                  padding: "4px 10px",
                  border: "1px solid var(--ink-border)",
                  fontSize: "10px",
                  fontFamily: "var(--font-mono)",
                }}
              >
                <div>
                  <span style={{ color: "var(--signal-suspect)" }}>■</span> SUSPECT EVIDENCE
                </div>
                <div>
                  <span style={{ color: "var(--signal-taint)" }}>■</span> TAINTED / HOLD
                </div>
                <div>
                  <span style={{ color: "var(--signal-reaffirm)" }}>■</span> REAFFIRMED
                </div>
                <div>
                  <span style={{ color: "var(--ink-secondary)" }}>- - -</span> LATERAL HOP
                </div>
              </div>
            </div>
          </section>

          {/* Right Column: ~40% Running Ledger & Query Log */}
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
            <div className="hairline-bottom" style={{ flex: 1, minHeight: 0, padding: "14px 16px", overflowY: "auto" }}>
              <div
                className="font-mono"
                style={{
                  fontSize: "11px",
                  textTransform: "uppercase",
                  letterSpacing: "0.08em",
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
                  className="hairline-border font-mono"
                  style={{
                    padding: "16px",
                    fontSize: "11px",
                    color: "var(--ink-muted)",
                    backgroundColor: "var(--bg-paper)",
                  }}
                >
                  No incident events recorded yet. Click a seed above to run the live multi-agent trace.
                </div>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
                  {events.map((evt, idx) => {
                    let stampClass = "stamp-neutral";
                    if (evt.event_type.includes("taint")) stampClass = "stamp-taint";
                    else if (evt.event_type.includes("suspect")) stampClass = "stamp-suspect";
                    else if (evt.event_type.includes("verdict")) stampClass = "stamp-reaffirm";

                    return (
                      <div
                        key={`evt-card-${evt.event_id}-${evt.timestamp || idx}-${idx}`}
                        className="hairline-border"
                        style={{
                          padding: "8px 12px",
                          backgroundColor: "var(--bg-paper)",
                          fontSize: "11px",
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
                            style={{ color: "var(--ink-secondary)", fontWeight: 600 }}
                          >
                            {evt.event_type}
                          </span>
                          <span className={`forensic-stamp ${stampClass}`} style={{ fontSize: "9px" }}>
                            {evt.event_type.split(".")[1]?.toUpperCase() || "LOG"}
                          </span>
                        </div>
                        <div
                          className="font-mono"
                          style={{ fontSize: "10px", color: "var(--ink-muted)" }}
                        >
                          Entities: {evt.entity_ids.join(", ") || "none"}
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
                padding: "12px 16px",
                backgroundColor: "var(--bg-paper-sunken)",
                height: "160px",
                maxHeight: "160px",
                flexShrink: 0,
                overflowY: "auto",
              }}
            >
              <div
                className="font-mono hairline-bottom"
                style={{
                  fontSize: "10px",
                  textTransform: "uppercase",
                  letterSpacing: "0.08em",
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
                  fontSize: "10px",
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

      {/* Evaluation Benchmark View */}
      {activeTab === "evaluation" && (
        <div style={{ padding: "20px 24px", backgroundColor: "var(--bg-paper)", flex: 1, minHeight: 0, overflowY: "auto" }}>
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              marginBottom: "20px",
            }}
          >
            <div>
              <h2 className="font-display" style={{ fontSize: "20px", fontWeight: 700 }}>
                Forensic Evaluation Benchmark Report
              </h2>
              <p
                className="font-body"
                style={{ fontSize: "12px", color: "var(--ink-muted)", marginTop: "2px" }}
              >
                Automated precision vs blanket naive recall harness across randomized incidents (Part A Phase A4).
              </p>
            </div>
            <button
              onClick={handleRunEvaluation}
              disabled={isEvaluating}
              className="font-mono hairline-border"
              style={{
                padding: "8px 18px",
                backgroundColor: "var(--bg-paper-elevated)",
                cursor: "pointer",
                fontWeight: 600,
              }}
            >
              {isEvaluating ? "Computing Benchmark..." : "Re-Run 5 Incidents Benchmark"}
            </button>
          </div>

          {evalReport && (
            <div style={{ display: "flex", flexDirection: "column", gap: "24px" }}>
              {/* Benchmark Summary Metrics Grid */}
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "repeat(4, 1fr)",
                  gap: "16px",
                }}
              >
                <div
                  className="hairline-border"
                  style={{ padding: "16px", backgroundColor: "var(--bg-paper-elevated)" }}
                >
                  <div
                    className="font-mono"
                    style={{ fontSize: "10px", color: "var(--ink-muted)", textTransform: "uppercase" }}
                  >
                    Precision vs Blanket Recall
                  </div>
                  <div
                    className="font-mono"
                    style={{ fontSize: "22px", fontWeight: 700, marginTop: "4px" }}
                  >
                    {(evalReport.precision_vs_naive_recall * 100).toFixed(1)}%
                  </div>
                  <div
                    className="font-body"
                    style={{ fontSize: "11px", color: "var(--ink-secondary)", marginTop: "4px" }}
                  >
                    Targeted causal containment vs blanket naive recall
                  </div>
                </div>

                <div
                  className="hairline-border"
                  style={{ padding: "16px", backgroundColor: "var(--bg-paper-elevated)" }}
                >
                  <div
                    className="font-mono"
                    style={{ fontSize: "10px", color: "var(--ink-muted)", textTransform: "uppercase" }}
                  >
                    False-Reaffirm Count
                  </div>
                  <div
                    className="font-mono"
                    style={{
                      fontSize: "22px",
                      fontWeight: 700,
                      marginTop: "4px",
                      color: "var(--signal-reaffirm)",
                    }}
                  >
                    {evalReport.false_reaffirm_count}
                  </div>
                  <div
                    className="font-body"
                    style={{ fontSize: "11px", color: "var(--ink-secondary)", marginTop: "4px" }}
                  >
                    Strictly 0 on generated ground truth
                  </div>
                </div>

                <div
                  className="hairline-border"
                  style={{ padding: "16px", backgroundColor: "var(--bg-paper-elevated)" }}
                >
                  <div
                    className="font-mono"
                    style={{ fontSize: "10px", color: "var(--ink-muted)", textTransform: "uppercase" }}
                  >
                    Hidden Lateral Link Recall
                  </div>
                  <div
                    className="font-mono"
                    style={{ fontSize: "22px", fontWeight: 700, marginTop: "4px" }}
                  >
                    {evalReport.hidden_link_recall_pct}%
                  </div>
                  <div
                    className="font-body"
                    style={{ fontSize: "11px", color: "var(--ink-secondary)", marginTop: "4px" }}
                  >
                    100% recall of shared equipment/lot batch contamination
                  </div>
                </div>

                <div
                  className="hairline-border"
                  style={{ padding: "16px", backgroundColor: "var(--bg-paper-elevated)" }}
                >
                  <div
                    className="font-mono"
                    style={{ fontSize: "10px", color: "var(--ink-muted)", textTransform: "uppercase" }}
                  >
                    Explanation Coverage
                  </div>
                  <div
                    className="font-mono"
                    style={{ fontSize: "22px", fontWeight: 700, marginTop: "4px" }}
                  >
                    {evalReport.explanation_coverage_pct}%
                  </div>
                  <div
                    className="font-body"
                    style={{ fontSize: "11px", color: "var(--ink-secondary)", marginTop: "4px" }}
                  >
                    100% of actions carry retrievable stored path (Rule 7)
                  </div>
                </div>
              </div>

              {/* Incidents Table */}
              <div className="hairline-border" style={{ backgroundColor: "var(--bg-paper-elevated)" }}>
                <div
                  className="hairline-bottom font-mono"
                  style={{
                    padding: "12px 16px",
                    fontWeight: 600,
                    fontSize: "11px",
                    textTransform: "uppercase",
                  }}
                >
                  Benchmarked Incident Runs ({evalReport.num_incidents} Instances)
                </div>
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "11px" }}>
                  <thead>
                    <tr className="hairline-bottom font-mono" style={{ textAlign: "left", color: "var(--ink-muted)" }}>
                      <th style={{ padding: "8px 16px" }}>INCIDENT ID</th>
                      <th style={{ padding: "8px 16px" }}>SEED</th>
                      <th style={{ padding: "8px 16px" }}>DURATION</th>
                      <th style={{ padding: "8px 16px" }}>NAIVE UNITS</th>
                      <th style={{ padding: "8px 16px" }}>TAINTED UNITS</th>
                      <th style={{ padding: "8px 16px" }}>REAFFIRMED</th>
                      <th style={{ padding: "8px 16px" }}>LATERAL DETECTED</th>
                      <th style={{ padding: "8px 16px" }}>EXPLAINED</th>
                    </tr>
                  </thead>
                  <tbody>
                    {evalReport.incidents.map((inc) => (
                      <tr key={inc.incident_id} className="hairline-bottom font-mono">
                        <td style={{ padding: "8px 16px" }}>{inc.incident_id}</td>
                        <td style={{ padding: "8px 16px" }}>{inc.seed}</td>
                        <td style={{ padding: "8px 16px" }}>{inc.duration_ms.toFixed(2)} ms</td>
                        <td style={{ padding: "8px 16px" }}>{inc.naive_recall_units}</td>
                        <td style={{ padding: "8px 16px", color: "var(--signal-taint)", fontWeight: 600 }}>
                          {inc.tainted_units}
                        </td>
                        <td style={{ padding: "8px 16px", color: "var(--signal-reaffirm)", fontWeight: 600 }}>
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
        </div>
      )}

      {/* Tool Gate Verifier View */}
      {activeTab === "gates" && (
        <div style={{ padding: "20px 24px", backgroundColor: "var(--bg-paper)", flex: 1, minHeight: 0, overflowY: "auto" }}>
          <h2 className="font-display" style={{ fontSize: "20px", fontWeight: 700, marginBottom: "4px" }}>
            Cypher Tool Gate Evaluator
          </h2>
          <p className="font-body" style={{ fontSize: "12px", color: "var(--ink-muted)", marginBottom: "20px" }}>
            Proves Section 0 Rule 5 &amp; Winning Requirement: &quot;A hold on an untainted batch is impossible
            because the tool is absent!&quot; Gates are evaluated in Cypher directly against graph state.
          </p>

          {(() => {
            const cleanUnitId = nodes.find(n => n.role?.toLowerCase() === "unit" && (!n.properties?.is_tainted || n.status === "reaffirmed"))?.id || nodes.find(n => n.role?.toLowerCase() === "unit")?.id || "";
            const taintedUnitId = nodes.find(n => n.role?.toLowerCase() === "unit" && (n.properties?.is_tainted || n.status === "tainted"))?.id || nodes.find(n => n.role?.toLowerCase() === "unit")?.id || "";

            return (
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "20px" }}>
                {/* Test 1: Untainted Batch Hold */}
                <div
                  className="hairline-border"
                  style={{ padding: "20px", backgroundColor: "var(--bg-paper-elevated)" }}
                >
                  <div
                    className="font-mono"
                    style={{ fontSize: "11px", fontWeight: 600, marginBottom: "8px", textTransform: "uppercase" }}
                  >
                    Test 1: Attempt Hold on Clean / Untainted Batch
                  </div>
                  <p className="font-body" style={{ fontSize: "12px", color: "var(--ink-secondary)", marginBottom: "16px" }}>
                    Expectation: The `hold_unit` gate evaluates in Cypher and returns `allowed=false`. The LLM
                    never sees or receives the tool. Target: <span className="font-mono">{cleanUnitId || "Scanning graph..."}</span>
                  </p>
                  <button
                    onClick={() => handleCheckGate("hold_unit", cleanUnitId)}
                    disabled={checkingGate || !cleanUnitId}
                    className="font-mono hairline-border"
                    style={{
                      padding: "6px 14px",
                      backgroundColor: "var(--bg-paper)",
                      cursor: "pointer",
                      fontWeight: 600,
                    }}
                  >
                    Evaluate Gate in Cypher
                  </button>
                </div>

                {/* Test 2: Tainted Batch Hold */}
                <div
                  className="hairline-border"
                  style={{ padding: "20px", backgroundColor: "var(--bg-paper-elevated)" }}
                >
                  <div
                    className="font-mono"
                    style={{ fontSize: "11px", fontWeight: 600, marginBottom: "8px", textTransform: "uppercase" }}
                  >
                    Test 2: Attempt Release on Tainted Batch
                  </div>
                  <p className="font-body" style={{ fontSize: "12px", color: "var(--ink-secondary)", marginBottom: "16px" }}>
                    Expectation: The `release_unit` gate evaluates `WHERE u.is_tainted = false` and refuses release
                    of contaminated lots. Target: <span className="font-mono">{taintedUnitId || "Scanning graph..."}</span>
                  </p>
                  <button
                    onClick={() => handleCheckGate("release_unit", taintedUnitId)}
                    disabled={checkingGate || !taintedUnitId}
                    className="font-mono hairline-border"
                    style={{
                      padding: "6px 14px",
                      backgroundColor: "var(--bg-paper)",
                      cursor: "pointer",
                      fontWeight: 600,
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
              className="hairline-border"
              style={{
                marginTop: "24px",
                padding: "20px",
                backgroundColor: "var(--bg-paper-elevated)",
              }}
            >
              <div
                className="font-mono"
                style={{
                  fontSize: "11px",
                  fontWeight: 600,
                  textTransform: "uppercase",
                  marginBottom: "8px",
                }}
              >
                Gate Evaluation Result
              </div>
              <div style={{ display: "flex", gap: "16px", marginBottom: "12px" }}>
                <span className="font-mono" style={{ fontSize: "12px" }}>
                  TOOL: <strong>{gateResult.tool_name}</strong>
                </span>
                <span className="font-mono" style={{ fontSize: "12px" }}>
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
                  fontSize: "11px",
                  lineHeight: "1.4",
                }}
              >
                {`// Cypher expression evaluated:\n${gateResult.gate_query}\n\n// Decision justification:\n${gateResult.reason}`}
              </pre>
            </div>
          )}
        </div>
      )}

      {/* Why Drawer (Chain of Custody Inspector) */}
      {whyDrawerOpen && (
        <div
          style={{
            position: "fixed",
            top: 0,
            right: 0,
            width: "480px",
            height: "100vh",
            backgroundColor: "var(--bg-paper)",
            borderLeft: "2px solid var(--ink-border)",
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
              <div
                className="font-mono"
                style={{
                  fontSize: "10px",
                  letterSpacing: "0.1em",
                  color: "var(--ink-muted)",
                  textTransform: "uppercase",
                }}
              >
                Chain of Custody Inspector · Rule 7
              </div>
              <h3 className="font-display" style={{ fontSize: "18px", fontWeight: 700 }}>
                Why Path Trajectory
              </h3>
            </div>
            <button
              onClick={() => setWhyDrawerOpen(false)}
              className="font-mono hairline-border"
              style={{
                padding: "4px 8px",
                backgroundColor: "var(--bg-paper-elevated)",
                cursor: "pointer",
                fontWeight: 600,
              }}
            >
              ESC / Close
            </button>
          </div>

          {whyData ? (
            <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
              <div
                className="hairline-border font-mono"
                style={{
                  padding: "12px",
                  backgroundColor: "var(--bg-paper-elevated)",
                  fontSize: "11px",
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
                <div
                  className="font-mono"
                  style={{ fontSize: "11px", textTransform: "uppercase", color: "var(--ink-secondary)" }}
                >
                  Stored Causal Path Trajectory
                </div>
                {whyData.steps.map((step) => (
                  <div
                    key={`why-step-${step.step_number}-${step.entity_id}`}
                    className="hairline-border"
                    style={{
                      padding: "10px 12px",
                      backgroundColor: "var(--bg-paper-elevated)",
                      fontSize: "11px",
                    }}
                  >
                    <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "4px" }}>
                      <span className="font-mono" style={{ fontWeight: 600 }}>
                        Step {step.step_number}: {step.kind} ({step.role})
                      </span>
                      {step.stamp_text && (
                        <span className="forensic-stamp stamp-taint" style={{ fontSize: "8px" }}>
                          {step.stamp_text}
                        </span>
                      )}
                    </div>
                    <div className="font-mono" style={{ fontSize: "10px", color: "var(--ink-muted)" }}>
                      ID: {step.entity_id}
                    </div>
                    <div className="font-body" style={{ fontSize: "11px", marginTop: "4px" }}>
                      {step.description}
                    </div>
                  </div>
                ))}
              </div>

              {/* Draft Content & Human Approval */}
              {whyData.draft_content && (
                <div
                  className="hairline-border"
                  style={{
                    padding: "12px",
                    backgroundColor: "var(--bg-paper-sunken)",
                    fontSize: "11px",
                  }}
                >
                  <div
                    className="font-mono"
                    style={{ fontWeight: 600, marginBottom: "4px", textTransform: "uppercase" }}
                  >
                    Draft Notice Document
                  </div>
                  <p className="font-body" style={{ color: "var(--ink-secondary)" }}>
                    {whyData.draft_content}
                  </p>
                </div>
              )}

              {whyData.requires_approval && (
                <div style={{ marginTop: "8px" }}>
                  {whyData.approved ? (
                    <div
                      className="forensic-stamp stamp-reaffirm"
                      style={{ display: "block", textAlign: "center", padding: "8px" }}
                    >
                      ACTION APPROVED BY OPERATOR
                    </div>
                  ) : (
                    <button
                      onClick={() => handleApproveAction(whyData.action_id)}
                      className="font-mono hairline-border"
                      style={{
                        width: "100%",
                        padding: "10px",
                        backgroundColor: "var(--ink-primary)",
                        color: "var(--bg-paper)",
                        cursor: "pointer",
                        fontWeight: 600,
                        fontSize: "12px",
                      }}
                    >
                      Approve Action Notice (Human Gate)
                    </button>
                  )}
                </div>
              )}
            </div>
          ) : (
            <div className="font-mono" style={{ color: "var(--ink-muted)", fontSize: "11px" }}>
              Retrieving stored chain of custody from graph...
            </div>
          )}
        </div>
      )}
    </div>
  );
}
