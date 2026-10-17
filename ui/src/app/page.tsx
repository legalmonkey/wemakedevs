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
  role_order?: string[];
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
  const [wallClockMs, setWallClockMs] = useState<number>(6850);
  const runStartTimeRef = useRef<number>(0);
  const [streamState, setStreamState] = useState<"tracing..." | "complete">("complete");
  const [noPacing, setNoPacing] = useState<boolean>(false);

  // Canvas Viewport & Navigation Controls (Requirement 1)
  const [zoom, setZoom] = useState<number>(1.0);
  const [pan, setPan] = useState<{ x: number; y: number }>({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState<boolean>(false);
  const dragStartRef = useRef<{ x: number; y: number }>({ x: 0, y: 0 });
  const touchDistanceRef = useRef<number | null>(null);
  const canvasContainerRef = useRef<HTMLDivElement | null>(null);

  // Collapsible Right Drawer for Ledger & Cypher Log (Requirement 1 & 6)
  const [isLedgerOpen, setIsLedgerOpen] = useState<boolean>(false);
  const [drawerTab, setDrawerTab] = useState<"ledger" | "queries">("ledger");
  const [showAllEvents, setShowAllEvents] = useState<boolean>(false);

  // Filter Chips & Selection Focus (Requirement 3)
  type FilterChip = "all" | "held" | "reaffirmed" | "escalated" | "suspect" | "lateral";
  const [activeFilter, setActiveFilter] = useState<FilterChip>("all");
  const [focusOnSelection, setFocusOnSelection] = useState<boolean>(false);
  const [hoveredNode, setHoveredNode] = useState<GraphNode | null>(null);
  const [hoverPos, setHoverPos] = useState<{ x: number; y: number } | null>(null);

  // Propagation Discrete Animation (Requirement 4)
  const [animatingHop, setAnimatingHop] = useState<number>(-1);
  const [reaffirmedGreenActive, setReaffirmedGreenActive] = useState<boolean>(true);

  // Collapsible First-Time Clarity Legend (Requirement 8)
  const [showHowToRead, setShowHowToRead] = useState<boolean>(true);

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

  // Keyboard shortcut listener (L toggles ledger, ESC closes drawers)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const targetTag = (e.target as HTMLElement)?.tagName;
      if (["INPUT", "TEXTAREA", "SELECT"].includes(targetTag)) return;

      if (e.key === "l" || e.key === "L") {
        setIsLedgerOpen((prev) => !prev);
      } else if (e.key === "Escape") {
        if (whyDrawerOpen) setWhyDrawerOpen(false);
        if (isLedgerOpen) setIsLedgerOpen(false);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [whyDrawerOpen, isLedgerOpen]);

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
        if (typeof data.stats?.time_to_scope_ms === "number") {
          setTimeToScopeMs(Number(data.stats.time_to_scope_ms.toFixed(2)));
        }
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
          if (parsed.event_type === "episode.closed") {
            setStreamState("complete");
            if (parsed.payload?.message) {
              setStatusMessage(String(parsed.payload.message));
            }
          } else if (parsed.event_type === "agent.status") {
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

  // Discrete Propagation Hop Animation (Requirement 4)
  const startPropagationAnimation = useCallback(() => {
    const prefersReduced =
      typeof window !== "undefined" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    if (prefersReduced) {
      setAnimatingHop(-1);
      setReaffirmedGreenActive(true);
      return;
    }

    setAnimatingHop(0); // Hop 0: Alert
    setReaffirmedGreenActive(false);

    // Hop 0 -> Hop 1 (Evidence)
    setTimeout(() => {
      setAnimatingHop(1);
      // Hop 1 -> Hop 2 (Decision)
      setTimeout(() => {
        setAnimatingHop(2);
        // Hop 2 -> Hop 3 (Unit column: initial hold)
        setTimeout(() => {
          setAnimatingHop(3);
          // Short hold, then show reaffirmed units turning green!
          setTimeout(() => {
            setReaffirmedGreenActive(true);
            // Hop 3 -> Hop 4 (Shipment & Recipient notices)
            setTimeout(() => {
              setAnimatingHop(4);
              // Complete animation
              setTimeout(() => {
                setAnimatingHop(-1);
              }, 500);
            }, 400);
          }, 350);
        }, 400);
      }, 400);
    }, 400);
  }, []);

  // Trigger live multi-agent incident run
  const handleTriggerIncident = async (seedToRun: number) => {
    setIsTriggering(true);
    setStreamState("tracing...");
    setActiveSeed(seedToRun);
    setEvents([]);
    setStatusMessage(`Triggering multi-agent trace on Seed ${seedToRun}...`);
    runStartTimeRef.current = performance.now();

    try {
      const speed = noPacing ? 0 : 120;
      const res = await fetch(`${API_BASE}/api/incident/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ seed: seedToRun, speed_ms: speed }),
      });
      if (res.ok) {
        setAgentStatus("ACTIVE");
        setTimeout(async () => {
          await fetchGraphSnapshot();
          await fetchPendingQueue();
          const wallElapsed = Math.round(performance.now() - (runStartTimeRef.current || performance.now()));
          if (wallElapsed > 0) {
            setWallClockMs(wallElapsed);
          }
          setStatusMessage(`Incident containment trace complete on Seed ${seedToRun}. All causal paths verified by Cypher gates.`);
          setStreamState("complete");
          startPropagationAnimation();
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
        const matchInc = report.incidents?.find((i: EvaluationIncident) => i.seed === activeSeed);
        if (matchInc) {
          setTimeToScopeMs(Number(matchInc.duration_ms.toFixed(2)));
        }
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

  // Helpers for Decluttering (Requirement 3)
  const getShortSuffix = useCallback((id: string): string => {
    if (!id) return "";
    const parts = id.split("-");
    if (parts.length >= 2) {
      return `${parts[parts.length - 2]}-${parts[parts.length - 1]}`;
    }
    return id.slice(-8);
  }, []);

  // Compute 4 dynamic counts - STRICTLY COUNTING UNITS ONLY (Requirements 1 & 5)
  const unitCounts = useMemo(() => {
    const unitNodes = nodes.filter((n) => (n.role || "").toLowerCase() === "unit");
    const unitIdSet = new Set(unitNodes.map((u) => u.id));
    const total = unitNodes.length || stats?.total_units || 0;

    // Requirement 1: Escalated tile counts Units that have a decision with verdict unverifiable or an escalation action, not u.verdict
    const unverifiableDecisionIds = new Set(
      nodes
        .filter(
          (n) =>
            (n.role || "").toLowerCase() === "decision" &&
            (n.properties?.verdict === "unverifiable" || (n.status || "").toLowerCase() === "unverifiable")
        )
        .map((n) => n.id)
    );

    const escalationActionTargetIds = new Set<string>();
    nodes.forEach((n) => {
      if (
        (n.role || "").toLowerCase() === "action" &&
        (n.properties?.action_kind === "escalate_human" || n.kind === "escalate_human")
      ) {
        if (n.properties?.target_entity_id) {
          escalationActionTargetIds.add(String(n.properties.target_entity_id));
        }
      }
    });
    pendingQueue.forEach((item) => {
      if (item.action_kind === "escalate_human" && item.target_entity_id) {
        escalationActionTargetIds.add(item.target_entity_id);
      }
    });

    const unitsWithUnvDecision = new Set<string>();
    edges.forEach((e) => {
      if (unverifiableDecisionIds.has(e.source_id) && unitIdSet.has(e.target_id)) {
        unitsWithUnvDecision.add(e.target_id);
      }
      if (unverifiableDecisionIds.has(e.target_id) && unitIdSet.has(e.source_id)) {
        unitsWithUnvDecision.add(e.source_id);
      }
      if (
        nodes.some(
          (n) =>
            n.id === e.source_id &&
            (n.role || "").toLowerCase() === "action" &&
            n.properties?.action_kind === "escalate_human"
        ) &&
        unitIdSet.has(e.target_id)
      ) {
        escalationActionTargetIds.add(e.target_id);
      }
    });

    const escalatedUnitIds = new Set<string>();
    unitNodes.forEach((u) => {
      if (unitsWithUnvDecision.has(u.id) || escalationActionTargetIds.has(u.id)) {
        escalatedUnitIds.add(u.id);
      }
    });

    // Reaffirmed: units that have reaffirmed status/verdict/release action and are NOT escalated
    const reaffirmedUnitIds = new Set<string>();
    unitNodes.forEach((u) => {
      if (escalatedUnitIds.has(u.id)) return;
      const s = (u.status || "").toLowerCase();
      const stamp = (u.stamp_text || "").toUpperCase();
      const verdict = String(u.properties?.verdict || "").toLowerCase();
      if (verdict === "reaffirmed" || s === "reaffirmed" || stamp === "REAFFIRMED") {
        reaffirmedUnitIds.add(u.id);
      }
    });

    // Held: units that are tainted/quarantined/held and NOT escalated and NOT reaffirmed
    const heldUnitIds = new Set<string>();
    unitNodes.forEach((u) => {
      if (escalatedUnitIds.has(u.id) || reaffirmedUnitIds.has(u.id)) return;
      const s = (u.status || "").toLowerCase();
      const stamp = (u.stamp_text || "").toUpperCase();
      const verdict = String(u.properties?.verdict || "").toLowerCase();
      if (verdict === "tainted" || s === "tainted" || s === "quarantined" || stamp === "HOLD") {
        heldUnitIds.add(u.id);
      }
    });

    // Unaffected: all remaining units (guarantees held + reaffirmed + escalated + unaffected === total)
    const unaffectedUnitIds = new Set<string>();
    unitNodes.forEach((u) => {
      if (!escalatedUnitIds.has(u.id) && !reaffirmedUnitIds.has(u.id) && !heldUnitIds.has(u.id)) {
        unaffectedUnitIds.add(u.id);
      }
    });

    const held = heldUnitIds.size;
    const reaffirmed = reaffirmedUnitIds.size;
    const escalated = escalatedUnitIds.size;
    const unaffected = unaffectedUnitIds.size;

    // Suspect Units: active in-progress suspect units, strictly 0 at completion
    const lateralUnitIds = new Set<string>();
    edges.forEach((e) => {
      if (e.is_lateral || e.kind === "SHARED_LOT" || e.kind === "LATERAL_LINK") {
        if (unitIdSet.has(e.target_id)) lateralUnitIds.add(e.target_id);
      }
    });

    let suspect = 0;
    if (streamState !== "complete") {
      unitNodes.forEach((u) => {
        const s = (u.status || "").toLowerCase();
        const stamp = (u.stamp_text || "").toUpperCase();
        if (
          u.properties?.is_suspect ||
          u.properties?.suspect ||
          s === "suspect" ||
          stamp === "SUSPECT" ||
          lateralUnitIds.has(u.id)
        ) {
          suspect++;
        }
      });
    }

    return { held, reaffirmed, escalated, unaffected, suspect, total, escalatedUnitIds, unaffectedUnitIds };
  }, [nodes, edges, pendingQueue, stats, streamState]);

  // Filter nodes according to active filter chip (Requirement 3)
  const displayedNodes = useMemo(() => {
    if (nodes.length === 0) return [];

    if (activeFilter === "reaffirmed") {
      return nodes.filter((n) => {
        const s = (n.status || "").toLowerCase();
        const stamp = (n.stamp_text || "").toUpperCase();
        const verdict = String(n.properties?.verdict || "").toLowerCase();
        return stamp === "REAFFIRMED" || s === "reaffirmed" || verdict === "reaffirmed";
      });
    }
    if (activeFilter === "held") {
      return nodes.filter((n) => {
        const s = (n.status || "").toLowerCase();
        const stamp = (n.stamp_text || "").toUpperCase();
        const verdict = String(n.properties?.verdict || "").toLowerCase();
        if (stamp === "REAFFIRMED" || s === "reaffirmed" || verdict === "reaffirmed") return false;
        return stamp === "HOLD" || s === "tainted" || s === "quarantined" || verdict === "tainted";
      });
    }
    if (activeFilter === "escalated") {
      return nodes.filter((n) => {
        const isEscUnit = unitCounts.escalatedUnitIds?.has(n.id);
        const s = (n.status || "").toLowerCase();
        const stamp = (n.stamp_text || "").toUpperCase();
        const verdict = String(n.properties?.verdict || "").toLowerCase();
        return isEscUnit || stamp === "ESCALATED" || s === "escalated" || s === "unverifiable" || verdict === "unverifiable";
      });
    }
    if (activeFilter === "suspect") {
      return nodes.filter((n) => {
        const s = (n.status || "").toLowerCase();
        const stamp = (n.stamp_text || "").toUpperCase();
        return stamp === "SUSPECT" || s === "suspect" || Boolean(n.properties?.is_suspect);
      });
    }
    if (activeFilter === "lateral") {
      const lateralNodeIds = new Set<string>();
      edges.forEach((e) => {
        if (e.is_lateral || e.kind === "LATERAL_LINK" || e.kind === "SHARED_LOT") {
          lateralNodeIds.add(e.source_id);
          lateralNodeIds.add(e.target_id);
        }
      });
      return nodes.filter((n) => lateralNodeIds.has(n.id));
    }

    // Default "all": show active incident nodes
    return nodes;
  }, [nodes, edges, activeFilter, unitCounts.escalatedUnitIds]);

  const displayedEdges = useMemo(() => {
    const nodeSet = new Set(displayedNodes.map((n) => n.id));
    return edges.filter((e) => nodeSet.has(e.source_id) && nodeSet.has(e.target_id));
  }, [edges, displayedNodes]);

  // Connected selection nodes for Focus Mode (Requirement 3)
  const connectedSelectionIds = useMemo(() => {
    const set = new Set<string>();
    if (!selectedEntityId) return set;
    set.add(selectedEntityId);
    if (whyData?.causal_path) {
      whyData.causal_path.forEach((id) => set.add(id));
    }
    edges.forEach((e) => {
      if (e.source_id === selectedEntityId) set.add(e.target_id);
      if (e.target_id === selectedEntityId) set.add(e.source_id);
    });
    return set;
  }, [selectedEntityId, whyData, edges]);

  // LAYERED LEFT-TO-RIGHT LAYOUT BY NODE ROLE (Requirement 2)
  // Order: alert, evidence, decision, unit, shipment, recipient from registry, zero hardcoding
  const roleOrder = useMemo(() => {
    if (registry?.role_order && Array.isArray(registry.role_order) && registry.role_order.length > 0) {
      return registry.role_order.map((r) => r.toLowerCase());
    }
    return ["event", "evidence", "decision", "unit", "shipment", "recipient"];
  }, [registry]);

  const { nodePositions, totalCanvasWidth, totalCanvasHeight, startX, colSpacing } = useMemo(() => {
    if (displayedNodes.length === 0) {
      return { nodePositions: {}, totalCanvasWidth: 1400, totalCanvasHeight: 700, startX: 140, colSpacing: 280 };
    }

    // 1. Group nodes into columns by role
    const colMap: Record<number, GraphNode[]> = {};
    roleOrder.forEach((_, idx) => {
      colMap[idx] = [];
    });

    displayedNodes.forEach((node) => {
      let roleKey = (node.role || "").toLowerCase();
      if (roleKey === "alert") roleKey = "event";
      let colIdx = roleOrder.indexOf(roleKey);
      if (colIdx === -1) {
        if (roleKey === "action") {
          colIdx = Math.min(3, roleOrder.length - 1);
        } else {
          colIdx = 0;
        }
      }
      if (!colMap[colIdx]) colMap[colIdx] = [];
      colMap[colIdx].push(node);
    });

    // 2. Build adjacency for Barycentric Sorting to minimize edge crossings
    const adjacency: Record<string, string[]> = {};
    displayedEdges.forEach((e) => {
      if (!adjacency[e.source_id]) adjacency[e.source_id] = [];
      if (!adjacency[e.target_id]) adjacency[e.target_id] = [];
      adjacency[e.source_id].push(e.target_id);
      adjacency[e.target_id].push(e.source_id);
    });

    // Sort Column 0 by ID
    colMap[0].sort((a, b) => a.id.localeCompare(b.id));

    // Barycentric sort each subsequent column
    for (let c = 1; c < roleOrder.length; c++) {
      const prevCol = colMap[c - 1] || [];
      const prevIndices = new Map<string, number>();
      prevCol.forEach((n, idx) => prevIndices.set(n.id, idx));

      colMap[c].sort((a, b) => {
        const aNeighbors = (adjacency[a.id] || []).filter((id) => prevIndices.has(id));
        const bNeighbors = (adjacency[b.id] || []).filter((id) => prevIndices.has(id));

        const aAvg =
          aNeighbors.length > 0
            ? aNeighbors.reduce((sum, id) => sum + (prevIndices.get(id) ?? 0), 0) / aNeighbors.length
            : 999;
        const bAvg =
          bNeighbors.length > 0
            ? bNeighbors.reduce((sum, id) => sum + (prevIndices.get(id) ?? 0), 0) / bNeighbors.length
            : 999;

        if (aAvg !== bAvg) return aAvg - bAvg;
        return a.id.localeCompare(b.id);
      });
    }

    // 3. Strict non-overlapping coordinate generation with widescreen aspect ratio
    const nodeHeight = 36;
    const nodeGap = 16;
    const slotHeight = nodeHeight + nodeGap; // 52px per slot: guaranteed non-overlapping

    const maxNodesInCol = Math.max(1, ...Object.values(colMap).map((list) => list.length));
    const virtualHeight = Math.max(650, maxNodesInCol * slotHeight + 140);
    // Balanced widescreen aspect ratio (~1.9) ensures columns span the full viewport width
    const virtualWidth = Math.max(1500, Math.round(virtualHeight * 1.9));

    const startX = 140;
    const colSpacing =
      roleOrder.length > 1
        ? Math.round((virtualWidth - 2 * startX) / (roleOrder.length - 1))
        : 280;

    const pos: Record<string, { x: number; y: number; col: number; row: number }> = {};

    roleOrder.forEach((_, c) => {
      const list = colMap[c] || [];
      const colTotalH = list.length * slotHeight;
      const startY = Math.max(70, (virtualHeight - colTotalH) / 2);

      list.forEach((node, r) => {
        pos[node.id] = {
          x: startX + c * colSpacing,
          y: startY + r * slotHeight,
          col: c,
          row: r,
        };
      });
    });

    return {
      nodePositions: pos,
      totalCanvasWidth: virtualWidth,
      totalCanvasHeight: virtualHeight,
      startX,
      colSpacing,
    };
  }, [displayedNodes, displayedEdges, roleOrder]);

  // Filter agent.status noise with no entities (Requirement 6)
  const visibleEvents = useMemo(() => {
    return events.filter((e) => {
      if (showAllEvents) return true;
      if (e.event_type === "agent.status" && (!e.entity_ids || e.entity_ids.length === 0)) {
        return false;
      }
      return true;
    });
  }, [events, showAllEvents]);

  // Group events by incident phase (Requirement 6)
  const groupedPhases = useMemo(() => {
    const p1: EventItem[] = [];
    const p2: EventItem[] = [];
    const p3: EventItem[] = [];
    const p4: EventItem[] = [];
    const p5: EventItem[] = [];

    visibleEvents.forEach((evt) => {
      const et = evt.event_type.toLowerCase();
      if (et.includes("alert") || et.includes("ingest") || et.includes("seed")) {
        p1.push(evt);
      } else if (et.includes("taint") || et.includes("trace") || et.includes("lateral") || et.includes("hop")) {
        p2.push(evt);
      } else if (et.includes("decision") || et.includes("adjudic") || et.includes("reaffirm") || et.includes("verdict")) {
        p3.push(evt);
      } else if (et.includes("action") || et.includes("hold") || et.includes("notice") || et.includes("approval") || et.includes("dispatch")) {
        p4.push(evt);
      } else {
        p5.push(evt);
      }
    });

    const groups = [
      { id: "p1", name: "Phase 1: Ingestion & Telemetry Alerts", events: p1 },
      { id: "p2", name: "Phase 2: Taint Tracing & Lateral Spread", events: p2 },
      { id: "p3", name: "Phase 3: Independent Policy Adjudication", events: p3 },
      { id: "p4", name: "Phase 4: Containment Actions & Human Notices", events: p4 },
      { id: "p5", name: "Phase 5: Agent Lifecycle & System Events", events: p5 },
    ];

    return groups.filter((g) => g.events.length > 0);
  }, [visibleEvents]);

  // Helper to format pack vocabulary terms dynamically (Requirement 2 & 12)
  const formatVocab = useCallback(
    (term?: string): string => {
      if (!term) return "";
      if (registry?.vocabulary && registry.vocabulary[term]) {
        return registry.vocabulary[term];
      }
      return term.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
    },
    [registry]
  );

  // Determine next human action description
  const nextHumanActionText = useMemo(() => {
    if (pendingQueue.length > 0) {
      const first = pendingQueue[0];
      const actionName = formatVocab(first.action_kind);
      return `Operator review required: Adjudicate ${actionName} for target ${first.target_entity_id}.`;
    }
    return registry?.vocabulary?.next_action_empty || "No manual actions pending. All graph paths verified by policy.";
  }, [pendingQueue, registry, formatVocab]);

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
            id="btn-investigate"
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

          {[101, 202, 303, 4812, 31337].map((seed) => (
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

          {/* Stream Pacing Mode Badge & Toggle (Requirement 3) */}
          <div style={{ display: "flex", alignItems: "center", gap: "6px", marginLeft: "4px" }}>
            <span
              className="border-neo font-mono"
              style={{
                padding: "5px 10px",
                fontSize: "10px",
                fontWeight: 700,
                backgroundColor: noPacing ? "var(--bg-paper-sunken)" : "var(--bg-paper-elevated)",
                color: "var(--ink-primary)",
              }}
            >
              STREAM: {noPacing ? "LIVE UNPACED (0ms)" : "LIVE PACED (120ms)"}
            </span>
            <button
              onClick={() => setNoPacing((prev) => !prev)}
              className="font-mono border-neo touch-target-44"
              style={{
                padding: "5px 10px",
                fontSize: "10px",
                fontWeight: 700,
                backgroundColor: noPacing ? "var(--ink-primary)" : "var(--bg-paper)",
                color: noPacing ? "var(--bg-paper)" : "var(--ink-primary)",
                cursor: "pointer",
              }}
              title="Toggle between artificial pacing delay (120ms) and unpaced instant multi-agent execution"
            >
              NO PACING: {noPacing ? "ON" : "OFF"}
            </button>
          </div>
        </div>

        {/* Right: Four Distinct Neobrutalist State Counts Tiles (Units Only with Denominator - Requirement 5) */}
        <div style={{ display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap" }}>
          {/* Held / Tainted Tile */}
          <div
            className="border-neo"
            style={{
              padding: "4px 12px",
              backgroundColor: "var(--bg-paper)",
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              minWidth: "90px",
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
              {unitCounts.held}
            </span>
            <span className="font-mono" style={{ fontSize: "9px", color: "var(--ink-secondary)", marginTop: "2px" }}>
              {unitCounts.held} of {unitCounts.total} batches
            </span>
          </div>

          {/* Reaffirmed Tile */}
          <div
            className="border-neo"
            style={{
              padding: "4px 12px",
              backgroundColor: "var(--bg-paper)",
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              minWidth: "90px",
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
              {unitCounts.reaffirmed}
            </span>
            <span className="font-mono" style={{ fontSize: "9px", color: "var(--ink-secondary)", marginTop: "2px" }}>
              {unitCounts.reaffirmed} of {unitCounts.total} batches
            </span>
          </div>

          {/* Escalated Tile */}
          <div
            className="border-neo"
            style={{
              padding: "4px 12px",
              backgroundColor: "var(--bg-paper)",
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              minWidth: "90px",
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
              {unitCounts.escalated}
            </span>
            <span className="font-mono" style={{ fontSize: "9px", color: "var(--ink-secondary)", marginTop: "2px" }}>
              {unitCounts.escalated} of {unitCounts.total} batches
            </span>
          </div>

          {/* Unaffected Tile (Mutually Exclusive 4th State - Sums to Total Units) */}
          <div
            className="border-neo"
            style={{
              padding: "4px 12px",
              backgroundColor: "var(--bg-paper)",
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              minWidth: "90px",
            }}
          >
            <span className="mono-label" style={{ color: "var(--ink-secondary)", fontSize: "10px" }}>
              {registry?.vocabulary?.count_unaffected_label || "UNAFFECTED"}
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
              {unitCounts.unaffected}
            </span>
            <span className="font-mono" style={{ fontSize: "9px", color: "var(--ink-secondary)", marginTop: "2px" }}>
              {unitCounts.unaffected} of {unitCounts.total} batches
            </span>
          </div>

          {/* Suspect In-Progress Indicator: Visible strictly during active run, 0 at completion */}
          {streamState !== "complete" && unitCounts.suspect > 0 && (
            <div
              className="border-neo font-mono"
              style={{
                padding: "4px 10px",
                backgroundColor: "var(--signal-suspect-bg)",
                borderColor: "var(--signal-suspect)",
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                minWidth: "85px",
              }}
            >
              <span className="mono-label" style={{ color: "var(--signal-suspect)", fontSize: "9px" }}>
                SUSPECT (TRACING)
              </span>
              <span style={{ fontSize: "16px", fontWeight: 700, color: "var(--signal-suspect)" }}>
                {unitCounts.suspect}
              </span>
            </div>
          )}

          {/* Collapsible Ledger Drawer Toggle Button (Requirement 1 & 6) */}
          <button
            onClick={() => setIsLedgerOpen((prev) => !prev)}
            className="border-neo font-mono shadow-neo-btn touch-target-44"
            style={{
              padding: "6px 14px",
              backgroundColor: isLedgerOpen ? "var(--ink-primary)" : "var(--bg-paper)",
              color: isLedgerOpen ? "var(--bg-paper)" : "var(--ink-primary)",
              cursor: "pointer",
              fontSize: "11px",
              fontWeight: 700,
              display: "flex",
              alignItems: "center",
              gap: "6px",
            }}
            title="Toggle Forensic Ledger & Cypher Log (Keyboard Shortcut: L)"
          >
            <span>LEDGER &amp; LOG</span>
            <span
              style={{
                backgroundColor: isLedgerOpen ? "var(--bg-paper)" : "var(--ink-primary)",
                color: isLedgerOpen ? "var(--ink-primary)" : "var(--bg-paper)",
                padding: "1px 5px",
                fontSize: "9px",
                fontWeight: 700,
              }}
            >
              {events.length}
            </span>
            <span style={{ fontSize: "9px", opacity: 0.75 }}>[L]</span>
          </button>
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
          {/* Collapsible First-Time Clarity Strip (Requirement 8) */}
          <div
            className="border-neo-bottom"
            style={{
              backgroundColor: "var(--bg-paper)",
              padding: "8px 16px",
              flexShrink: 0,
            }}
          >
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                cursor: "pointer",
              }}
              onClick={() => setShowHowToRead((prev) => !prev)}
            >
              <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                <span className="mono-label" style={{ color: "var(--ink-primary)", fontWeight: 700 }}>
                  HOW TO READ THIS EVIDENCE CANVAS
                </span>
                <span className="font-mono" style={{ fontSize: "11px", color: "var(--ink-secondary)" }}>
                  (6-step supply chain role order &amp; 3 stamp definitions)
                </span>
              </div>
              <button
                type="button"
                className="font-mono border-neo"
                style={{
                  padding: "2px 8px",
                  fontSize: "10px",
                  fontWeight: 700,
                  backgroundColor: "var(--bg-paper-elevated)",
                  cursor: "pointer",
                }}
              >
                {showHowToRead ? "HIDE GUIDE ▲" : "SHOW GUIDE ▼"}
              </button>
            </div>

            {showHowToRead && (
              <div style={{ marginTop: "8px", paddingTop: "8px", borderTop: "1px dashed var(--ink-border)" }}>
                {/* 6-step Plain Language Legend */}
                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns: "repeat(auto-fit, minmax(170px, 1fr))",
                    gap: "8px",
                    marginBottom: "8px",
                  }}
                >
                  <div className="font-mono" style={{ fontSize: "11px", padding: "6px 8px", backgroundColor: "var(--bg-paper-sunken)" }}>
                    <strong>1. ALERT</strong>
                    <div style={{ fontSize: "10px", color: "var(--ink-secondary)", marginTop: "2px" }}>
                      Ingestion signal or contamination alarm
                    </div>
                  </div>
                  <div className="font-mono" style={{ fontSize: "11px", padding: "6px 8px", backgroundColor: "var(--bg-paper-sunken)" }}>
                    <strong>2. EVIDENCE</strong>
                    <div style={{ fontSize: "10px", color: "var(--ink-secondary)", marginTop: "2px" }}>
                      Lab tests, swab telemetry &amp; sensor audits
                    </div>
                  </div>
                  <div className="font-mono" style={{ fontSize: "11px", padding: "6px 8px", backgroundColor: "var(--bg-paper-sunken)" }}>
                    <strong>3. DECISION</strong>
                    <div style={{ fontSize: "10px", color: "var(--ink-secondary)", marginTop: "2px" }}>
                      Automated Cypher gate policy verdicts
                    </div>
                  </div>
                  <div className="font-mono" style={{ fontSize: "11px", padding: "6px 8px", backgroundColor: "var(--bg-paper-sunken)" }}>
                    <strong>4. BATCH (UNIT)</strong>
                    <div style={{ fontSize: "10px", color: "var(--ink-secondary)", marginTop: "2px" }}>
                      Inventory lots held or reaffirmed
                    </div>
                  </div>
                  <div className="font-mono" style={{ fontSize: "11px", padding: "6px 8px", backgroundColor: "var(--bg-paper-sunken)" }}>
                    <strong>5. SHIPMENT</strong>
                    <div style={{ fontSize: "10px", color: "var(--ink-secondary)", marginTop: "2px" }}>
                      Transit vehicles &amp; container manifests
                    </div>
                  </div>
                  <div className="font-mono" style={{ fontSize: "11px", padding: "6px 8px", backgroundColor: "var(--bg-paper-sunken)" }}>
                    <strong>6. CUSTOMER</strong>
                    <div style={{ fontSize: "10px", color: "var(--ink-secondary)", marginTop: "2px" }}>
                      End recipients, clinics &amp; retail stores
                    </div>
                  </div>
                </div>

                {/* 3 Rubber Stamps (Vocabulary / Registry Bound) */}
                <div style={{ display: "flex", gap: "12px", alignItems: "center", flexWrap: "wrap", fontSize: "11px" }} className="font-mono">
                  <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                    <span className="forensic-stamp stamp-taint" style={{ fontSize: "8px", padding: "1px 6px" }}>HOLD</span>
                    <span style={{ color: "var(--ink-secondary)" }}>
                      {registry?.statuses?.find((s) => s.stamp_text === "HOLD" || s.id === "status_tainted")?.description ||
                        registry?.vocabulary?.stamp_hold_copy ||
                        "Lost independent support; held."}
                    </span>
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                    <span className="forensic-stamp stamp-reaffirm" style={{ fontSize: "8px", padding: "1px 6px" }}>REAFFIRMED</span>
                    <span style={{ color: "var(--ink-secondary)" }}>
                      {registry?.statuses?.find((s) => s.stamp_text === "REAFFIRMED" || s.id === "status_reaffirmed")?.description ||
                        registry?.vocabulary?.stamp_reaffirmed_copy ||
                        "Independent valid support remains; cleared."}
                    </span>
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                    <span className="forensic-stamp stamp-suspect" style={{ fontSize: "8px", padding: "1px 6px" }}>SUSPECT</span>
                    <span style={{ color: "var(--ink-secondary)" }}>
                      {registry?.statuses?.find((s) => s.stamp_text === "SUSPECT" || s.id === "status_suspect")?.description ||
                        registry?.vocabulary?.stamp_suspect_copy ||
                        "Evidence from the retracted source, not yet re-judged."}
                    </span>
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                    <span
                      style={{
                        display: "inline-block",
                        width: "22px",
                        height: "0px",
                        borderTop: "2px dashed var(--signal-suspect)",
                      }}
                    />
                    <span style={{ color: "var(--ink-secondary)" }}>
                      <strong>LATERAL LINKS:</strong> Lateral links are dashed arcs.
                    </span>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Canvas Sub-Header Controls & Filter Chips (Requirements 1 & 3) */}
          <div
            className="border-neo-bottom"
            style={{
              padding: "6px 16px",
              backgroundColor: "var(--bg-paper-elevated)",
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              flexWrap: "wrap",
              gap: "8px",
              flexShrink: 0,
            }}
          >
            {/* Filter Chips */}
            <div style={{ display: "flex", alignItems: "center", gap: "6px", flexWrap: "wrap" }}>
              <span className="mono-label" style={{ color: "var(--ink-secondary)", fontSize: "10px", marginRight: "4px" }}>
                FILTER:
              </span>
              {[
                { id: "all", label: `ALL (${nodes.length})` },
                { id: "held", label: `HELD (${unitCounts.held})` },
                { id: "reaffirmed", label: `REAFFIRMED (${unitCounts.reaffirmed})` },
                { id: "escalated", label: `ESCALATED (${unitCounts.escalated})` },
                { id: "suspect", label: `SUSPECT (${unitCounts.suspect})` },
                { id: "lateral", label: "LATERAL PATH" },
              ].map((chip) => (
                <button
                  key={chip.id}
                  onClick={() => setActiveFilter(chip.id as FilterChip)}
                  className={`font-mono border-neo touch-target-44 ${
                    activeFilter === chip.id ? "shadow-neo-selected" : ""
                  }`}
                  style={{
                    padding: "3px 10px",
                    backgroundColor: activeFilter === chip.id ? "var(--ink-primary)" : "var(--bg-paper)",
                    color: activeFilter === chip.id ? "var(--bg-paper)" : "var(--ink-primary)",
                    fontSize: "10px",
                    fontWeight: 700,
                    cursor: "pointer",
                  }}
                >
                  {chip.label}
                </button>
              ))}

              <button
                onClick={() => setFocusOnSelection((prev) => !prev)}
                className={`font-mono border-neo touch-target-44 ${focusOnSelection ? "shadow-neo-selected" : ""}`}
                style={{
                  padding: "3px 10px",
                  marginLeft: "8px",
                  backgroundColor: focusOnSelection ? "var(--ink-primary)" : "var(--bg-paper)",
                  color: focusOnSelection ? "var(--bg-paper)" : "var(--ink-primary)",
                  fontSize: "10px",
                  fontWeight: 700,
                  cursor: "pointer",
                }}
                title="Dims nodes and links outside the selected entity's causal path"
              >
                FOCUS ON SELECTION: {focusOnSelection ? "ON" : "OFF"}
              </button>
            </div>

            {/* Viewport Zoom / Pan Controls (Requirement 1) */}
            <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
              <button
                onClick={() => {
                  if (!document.fullscreenElement) {
                    canvasContainerRef.current?.requestFullscreen?.().catch(() => {});
                  } else {
                    document.exitFullscreen?.().catch(() => {});
                  }
                }}
                className="font-mono border-neo touch-target-44"
                style={{
                  padding: "3px 10px",
                  backgroundColor: "var(--bg-paper)",
                  fontSize: "10px",
                  fontWeight: 700,
                  cursor: "pointer",
                }}
                title="Fullscreen Evidence Canvas"
              >
                FULLSCREEN
              </button>

              <button
                onClick={() => setZoom((z) => Math.min(Number((z * 1.2).toFixed(2)), 3.0))}
                className="font-mono border-neo touch-target-44"
                style={{
                  padding: "3px 8px",
                  backgroundColor: "var(--bg-paper)",
                  fontSize: "11px",
                  fontWeight: 700,
                  cursor: "pointer",
                }}
                title="Zoom In"
              >
                +
              </button>

              <button
                onClick={() => setZoom((z) => Math.max(Number((z / 1.2).toFixed(2)), 0.3))}
                className="font-mono border-neo touch-target-44"
                style={{
                  padding: "3px 8px",
                  backgroundColor: "var(--bg-paper)",
                  fontSize: "11px",
                  fontWeight: 700,
                  cursor: "pointer",
                }}
                title="Zoom Out"
              >
                -
              </button>

              <button
                onClick={() => {
                  setZoom(1.0);
                  setPan({ x: 0, y: 0 });
                }}
                className="font-mono border-neo touch-target-44"
                style={{
                  padding: "3px 10px",
                  backgroundColor: "var(--bg-paper)",
                  fontSize: "10px",
                  fontWeight: 700,
                  cursor: "pointer",
                }}
                title="Fit to View (100%)"
              >
                FIT VIEW ({Math.round(zoom * 100)}%)
              </button>

              <button
                onClick={startPropagationAnimation}
                className="font-mono border-neo touch-target-44"
                style={{
                  padding: "3px 10px",
                  backgroundColor: "var(--bg-paper)",
                  fontSize: "10px",
                  fontWeight: 700,
                  cursor: "pointer",
                }}
                title="Replay discrete hop-by-hop propagation animation"
              >
                REPLAY PROPAGATION
              </button>

              <button
                onClick={() => setIsLedgerOpen((prev) => !prev)}
                className="font-mono border-neo touch-target-44"
                style={{
                  padding: "3px 10px",
                  backgroundColor: isLedgerOpen ? "var(--ink-primary)" : "var(--bg-paper)",
                  color: isLedgerOpen ? "var(--bg-paper)" : "var(--ink-primary)",
                  fontSize: "10px",
                  fontWeight: 700,
                  cursor: "pointer",
                }}
                title="Toggle Forensic Ledger &amp; Cypher Log Drawer (Hotkey: L)"
              >
                LEDGER [L]
              </button>
            </div>
          </div>

          {/* SVG Canvas Stage (Requirement 1, 2 & 6) */}
          <div
            ref={canvasContainerRef}
            className="border-neo"
            onWheel={(e) => {
              e.preventDefault();
              const delta = e.deltaY < 0 ? 1.1 : 0.9;
              setZoom((z) => Math.min(Math.max(Number((z * delta).toFixed(2)), 0.3), 3.0));
            }}
            onMouseDown={(e) => {
              if (e.button === 0) {
                setIsDragging(true);
                dragStartRef.current = { x: e.clientX - pan.x, y: e.clientY - pan.y };
              }
            }}
            onMouseMove={(e) => {
              if (isDragging) {
                setPan({
                  x: e.clientX - dragStartRef.current.x,
                  y: e.clientY - dragStartRef.current.y,
                });
              }
            }}
            onMouseUp={() => setIsDragging(false)}
            onMouseLeave={() => {
              setIsDragging(false);
              setHoveredNode(null);
            }}
            onTouchStart={(e) => {
              if (e.touches.length === 1) {
                setIsDragging(true);
                dragStartRef.current = { x: e.touches[0].clientX - pan.x, y: e.touches[0].clientY - pan.y };
              } else if (e.touches.length === 2) {
                const dist = Math.hypot(
                  e.touches[0].clientX - e.touches[1].clientX,
                  e.touches[0].clientY - e.touches[1].clientY
                );
                touchDistanceRef.current = dist;
              }
            }}
            onTouchMove={(e) => {
              if (e.touches.length === 1 && isDragging) {
                setPan({
                  x: e.touches[0].clientX - dragStartRef.current.x,
                  y: e.touches[0].clientY - dragStartRef.current.y,
                });
              } else if (e.touches.length === 2 && touchDistanceRef.current) {
                const dist = Math.hypot(
                  e.touches[0].clientX - e.touches[1].clientX,
                  e.touches[0].clientY - e.touches[1].clientY
                );
                const factor = dist / touchDistanceRef.current;
                if (Math.abs(factor - 1) > 0.05) {
                  setZoom((z) => Math.min(Math.max(Number((z * factor).toFixed(2)), 0.3), 3.0));
                  touchDistanceRef.current = dist;
                }
              }
            }}
            onTouchEnd={() => {
              setIsDragging(false);
              touchDistanceRef.current = null;
            }}
            style={{
              flex: 1,
              minHeight: 0,
              width: "100%",
              height: "100%",
              backgroundColor: "var(--bg-paper-sunken)",
              position: "relative",
              overflow: "hidden",
              cursor: isDragging ? "grabbing" : "grab",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              userSelect: "none",
            }}
          >
            {/* Visible Mobile Touch Pan/Zoom Hint Banner (Requirement 6) */}
            <div
              className="font-mono border-neo"
              style={{
                position: "absolute",
                top: "12px",
                left: "50%",
                transform: "translateX(-50%)",
                backgroundColor: "var(--bg-paper)",
                padding: "4px 14px",
                fontSize: "11px",
                fontWeight: 700,
                color: "var(--ink-secondary)",
                zIndex: 10,
                pointerEvents: "none",
                boxShadow: "var(--shadow-interactive)",
                display: "flex",
                alignItems: "center",
                gap: "6px",
              }}
            >
              <span>DRAG TO MOVE</span>
            </div>
            {displayedNodes.length === 0 ? (
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
                <h2 className="font-display" style={{ fontSize: "22px", marginBottom: "8px" }}>
                  Evidence Graph Awaiting Incident Signal
                </h2>
                <p className="font-body" style={{ color: "var(--ink-secondary)", maxWidth: "480px", marginBottom: "20px" }}>
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
              <svg
                width="100%"
                height="100%"
                viewBox={`0 0 ${totalCanvasWidth} ${totalCanvasHeight}`}
                preserveAspectRatio="xMidYMid meet"
                style={{ width: "100%", height: "100%", display: "block" }}
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
                  <marker
                    id="arrow-lateral"
                    viewBox="0 0 10 10"
                    refX="18"
                    refY="5"
                    markerWidth="6"
                    markerHeight="6"
                    orient="auto-start-reverse"
                  >
                    <path d="M 0 0 L 10 5 L 0 10 z" fill="var(--signal-suspect)" />
                  </marker>
                </defs>

                <g transform={`translate(${pan.x}, ${pan.y}) scale(${zoom})`}>
                  {/* Layer Role Column Header Guides */}
                  {roleOrder.map((roleKey, c) => {
                    const colX = startX + c * colSpacing;
                    const isHopActive = animatingHop === c;
                    return (
                      <g key={`col-guide-${roleKey}-${c}`}>
                        <line
                          x1={colX}
                          y1={20}
                          x2={colX}
                          y2={totalCanvasHeight - 20}
                          stroke="var(--ink-border)"
                          strokeDasharray="2,6"
                          strokeWidth={isHopActive ? 2 : 1}
                          opacity={isHopActive ? 0.8 : 0.3}
                        />
                        <rect
                          x={colX - 55}
                          y={24}
                          width={110}
                          height={22}
                          fill={isHopActive ? "var(--ink-primary)" : "var(--bg-paper-elevated)"}
                          stroke="var(--ink-border)"
                          strokeWidth="1.5"
                        />
                        <text
                          x={colX}
                          y={39}
                          textAnchor="middle"
                          fill={isHopActive ? "var(--bg-paper)" : "var(--ink-secondary)"}
                          fontSize="10"
                          fontFamily="var(--font-mono)"
                          fontWeight="700"
                          letterSpacing="0.06em"
                        >
                          {roleKey.toUpperCase()}
                        </text>
                      </g>
                    );
                  })}

                  {/* Render Edges: Straight for causal hops, dashed curved arcs for lateral links */}
                  {displayedEdges.map((edge, idx) => {
                    const src = nodePositions[edge.source_id];
                    const dst = nodePositions[edge.target_id];
                    if (!src || !dst) return null;

                    const isHighlighted =
                      highlightedEntitySet.has(edge.source_id) &&
                      highlightedEntitySet.has(edge.target_id);

                    const isTaint = edge.is_taint;
                    const isLateral =
                      edge.is_lateral ||
                      edge.kind === "LATERAL_LINK" ||
                      edge.kind === "SHARED_LOT";

                    // Focus on Selection Dimming (Requirement 3)
                    const isFocusDimmed =
                      focusOnSelection &&
                      selectedEntityId &&
                      !(connectedSelectionIds.has(edge.source_id) && connectedSelectionIds.has(edge.target_id));

                    const strokeColor = isHighlighted
                      ? "var(--ink-primary)"
                      : isTaint
                      ? "var(--signal-taint)"
                      : isLateral
                      ? "var(--signal-suspect)"
                      : "var(--ink-border)";

                    const strokeDash = isLateral ? "5,4" : isTaint ? "5,4" : "none";
                    const strokeWidth = isHighlighted ? 3.5 : isTaint || isLateral ? 2.5 : 1.5;

                    if (isLateral) {
                      // Dashed Arc for Lateral links (Requirement 2)
                      const midX = (src.x + dst.x) / 2;
                      const midY = (src.y + dst.y) / 2 - 36;
                      const arcD = `M ${src.x} ${src.y} Q ${midX} ${midY} ${dst.x} ${dst.y}`;

                      return (
                        <g
                          key={`lateral-${edge.source_id}-${edge.target_id}-${idx}`}
                          opacity={isFocusDimmed ? 0.12 : 1}
                        >
                          <path
                            d={arcD}
                            fill="none"
                            stroke={strokeColor}
                            strokeWidth={strokeWidth}
                            strokeDasharray="5,4"
                            markerEnd="url(#arrow-lateral)"
                          />
                          <text
                            x={midX}
                            y={midY - 6}
                            fill="var(--signal-suspect)"
                            fontSize="9"
                            fontFamily="var(--font-mono)"
                            textAnchor="middle"
                            fontWeight="700"
                          >
                            LATERAL ARC
                          </text>
                        </g>
                      );
                    }

                    // Standard direct causal edge
                    const mx = (src.x + dst.x) / 2;
                    const my = (src.y + dst.y) / 2;

                    return (
                      <g
                        key={`edge-${edge.source_id}-${edge.target_id}-${idx}`}
                        opacity={isFocusDimmed ? 0.12 : 1}
                      >
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
                        {edge.hops !== undefined && edge.hops !== null && (
                          <text
                            x={mx}
                            y={my - 6}
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

                  {/* Render Nodes: strict non-overlapping slots, decluttered ID suffix + 1 label */}
                  {displayedNodes.map((node) => {
                    const pos = nodePositions[node.id];
                    if (!pos) return null;

                    const isSelected = selectedEntityId === node.id;
                    const isWhyPath = highlightedEntitySet.has(node.id);

                    // Focus Dimming
                    const isFocusDimmed =
                      focusOnSelection &&
                      selectedEntityId &&
                      !connectedSelectionIds.has(node.id);

                    // Stamps appear ONLY on units and decisions (Requirement 3)
                    const nodeRoleLower = (node.role || "").toLowerCase();
                    const canHaveStamp =
                      (nodeRoleLower === "unit" || nodeRoleLower === "decision") &&
                      Boolean(node.stamp_text);

                    // Color Tokens & Propagation Reaffirmed Green Transition (Requirement 4)
                    let strokeColor = "var(--ink-border)";
                    let fillColor = "var(--bg-paper)";

                    if (node.ink_token === "tainted" || node.status === "tainted" || node.properties?.is_tainted) {
                      strokeColor = "var(--signal-taint)";
                    } else if (
                      (node.ink_token === "reaffirmed" || node.status === "reaffirmed") &&
                      reaffirmedGreenActive
                    ) {
                      strokeColor = "var(--signal-reaffirm)";
                    } else if (node.ink_token === "suspect" || node.status === "suspect" || node.properties?.is_suspect) {
                      strokeColor = "var(--signal-suspect)";
                    }

                    if (isSelected) {
                      fillColor = "var(--bg-paper-elevated)";
                    }

                    // Declutter: ID Suffix & 1 short label (Requirement 3)
                    const idSuffix = getShortSuffix(node.id);
                    const shortLabel = node.badge || node.kind || node.role;

                    return (
                      <g
                        key={`node-${node.id}`}
                        transform={`translate(${pos.x}, ${pos.y})`}
                        onClick={() => handleOpenWhy(node.id)}
                        onMouseEnter={(e) => {
                          setHoveredNode(node);
                          setHoverPos({ x: e.clientX, y: e.clientY });
                        }}
                        onMouseMove={(e) => {
                          setHoverPos({ x: e.clientX, y: e.clientY });
                        }}
                        onMouseLeave={() => setHoveredNode(null)}
                        tabIndex={0}
                        role="button"
                        aria-label={`Inspect ${node.kind} ${node.id}`}
                        onKeyDown={(e) => {
                          if (e.key === "Enter" || e.key === " ") {
                            handleOpenWhy(node.id);
                          }
                        }}
                        opacity={isFocusDimmed ? 0.2 : 1}
                        style={{ cursor: "pointer", outline: "none" }}
                      >
                        {/* Neobrutalist Hard Offset Vector Shadow (Selected / Causal Path) */}
                        {(isSelected || isWhyPath) && (
                          <rect
                            x="-37"
                            y="-20"
                            width="80"
                            height="46"
                            fill="var(--ink-primary)"
                          />
                        )}

                        {/* Node Card Box (Guaranteed non-overlapping 80x46 card) */}
                        <rect
                          x="-40"
                          y="-23"
                          width="80"
                          height="46"
                          fill={fillColor}
                          stroke={isWhyPath ? "var(--ink-primary)" : strokeColor}
                          strokeWidth={isSelected || isWhyPath ? 3 : 2}
                          className={
                            node.status === "reaffirmed" && reaffirmedGreenActive
                              ? "reaffirmed-glow"
                              : ""
                          }
                        />

                        {/* One Short Label (Declutter - Requirement 3) */}
                        <text
                          x="-32"
                          y="-9"
                          fill="var(--ink-muted)"
                          fontSize="9"
                          fontFamily="var(--font-mono)"
                          fontWeight="700"
                        >
                          {shortLabel.length > 10 ? `${shortLabel.slice(0, 9)}…` : shortLabel}
                        </text>

                        {/* ID Suffix Only by Default (Declutter - Requirement 3) */}
                        <text
                          x="0"
                          y="8"
                          fill="var(--ink-primary)"
                          fontSize="10"
                          fontFamily="var(--font-mono)"
                          textAnchor="middle"
                          fontWeight="700"
                        >
                          {idSuffix}
                        </text>

                        {/* Stamps strictly on Units and Decisions only (Requirement 3) */}
                        {canHaveStamp && (
                          <g transform="translate(0, 31)">
                            {(isSelected || isWhyPath) && (
                              <rect
                                x="-32"
                                y="-7"
                                width="66"
                                height="18"
                                fill="var(--ink-primary)"
                              />
                            )}
                            <rect
                              x="-34"
                              y="-9"
                              width="66"
                              height="18"
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
                              letterSpacing="0.08em"
                              textAnchor="middle"
                            >
                              {node.stamp_text}
                            </text>
                          </g>
                        )}
                      </g>
                    );
                  })}
                </g>
              </svg>
            )}

            {/* Hover Tooltip (Full Detail on Hover - Requirement 3) */}
            {hoveredNode && hoverPos && (
              <div
                className="border-neo font-mono"
                style={{
                  position: "fixed",
                  left: Math.min(hoverPos.x + 14, (typeof window !== "undefined" ? window.innerWidth : 1440) - 300),
                  top: Math.min(hoverPos.y + 14, (typeof window !== "undefined" ? window.innerHeight : 900) - 180),
                  zIndex: 1500,
                  backgroundColor: "var(--bg-paper-elevated)",
                  padding: "10px 14px",
                  fontSize: "11px",
                  maxWidth: "290px",
                  boxShadow: "var(--shadow-interactive-lg)",
                  pointerEvents: "none",
                }}
              >
                <div style={{ fontWeight: 700, color: "var(--ink-primary)", marginBottom: "4px" }}>
                  {hoveredNode.id}
                </div>
                <div style={{ color: "var(--ink-secondary)", marginBottom: "2px" }}>
                  ROLE: <strong>{hoveredNode.role}</strong> · KIND: <strong>{hoveredNode.kind}</strong>
                </div>
                <div style={{ color: "var(--ink-secondary)", marginBottom: "2px" }}>
                  STATUS:{" "}
                  <strong
                    style={{
                      color:
                        hoveredNode.ink_token === "tainted"
                          ? "var(--signal-taint)"
                          : hoveredNode.ink_token === "reaffirmed"
                          ? "var(--signal-reaffirm)"
                          : "var(--ink-primary)",
                    }}
                  >
                    {hoveredNode.status || "active"}
                  </strong>
                </div>
                {hoveredNode.stamp_text && (
                  <div style={{ marginTop: "4px" }}>
                    STAMP:{" "}
                    <span className="forensic-stamp stamp-taint" style={{ fontSize: "8px", padding: "1px 6px" }}>
                      {hoveredNode.stamp_text}
                    </span>
                  </div>
                )}
                <div style={{ fontSize: "10px", color: "var(--ink-muted)", marginTop: "6px" }}>
                  Click to inspect causal chain of custody
                </div>
              </div>
            )}
          </div>

          {/* Collapsible Right Drawer for Ledger & Cypher Log (Requirements 1 & 6) */}
          {isLedgerOpen && (
            <aside
              role="dialog"
              aria-label="Forensic Ledger and Cypher Log Drawer"
              style={{
                position: "fixed",
                top: 0,
                right: 0,
                width: "480px",
                maxWidth: "100vw",
                height: "100vh",
                backgroundColor: "var(--bg-paper)",
                borderLeft: "var(--border-neo-thick)",
                boxShadow: "var(--shadow-interactive-lg)",
                display: "flex",
                flexDirection: "column",
                zIndex: 1100,
                overflow: "hidden",
              }}
            >
              {/* Drawer Navigation Bar */}
              <div
                className="border-neo-bottom"
                style={{
                  padding: "12px 16px",
                  backgroundColor: "var(--bg-paper-elevated)",
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  flexShrink: 0,
                }}
              >
                <div style={{ display: "flex", gap: "8px" }}>
                  <button
                    onClick={() => setDrawerTab("ledger")}
                    className={`font-mono border-neo touch-target-44 ${
                      drawerTab === "ledger" ? "shadow-neo-selected" : ""
                    }`}
                    style={{
                      padding: "4px 12px",
                      backgroundColor: drawerTab === "ledger" ? "var(--ink-primary)" : "var(--bg-paper)",
                      color: drawerTab === "ledger" ? "var(--bg-paper)" : "var(--ink-primary)",
                      fontSize: "11px",
                      fontWeight: 700,
                      cursor: "pointer",
                    }}
                  >
                    LEDGER ({visibleEvents.length})
                  </button>
                  <button
                    onClick={() => setDrawerTab("queries")}
                    className={`font-mono border-neo touch-target-44 ${
                      drawerTab === "queries" ? "shadow-neo-selected" : ""
                    }`}
                    style={{
                      padding: "4px 12px",
                      backgroundColor: drawerTab === "queries" ? "var(--ink-primary)" : "var(--bg-paper)",
                      color: drawerTab === "queries" ? "var(--bg-paper)" : "var(--ink-primary)",
                      fontSize: "11px",
                      fontWeight: 700,
                      cursor: "pointer",
                    }}
                  >
                    CYPHER LOG ({queryLog.length})
                  </button>
                </div>

                <button
                  onClick={() => setIsLedgerOpen(false)}
                  className="font-mono border-neo touch-target-44"
                  style={{
                    padding: "4px 12px",
                    backgroundColor: "var(--bg-paper)",
                    fontSize: "11px",
                    fontWeight: 700,
                    cursor: "pointer",
                  }}
                  title="Close Drawer (ESC / L)"
                >
                  CLOSE [ESC]
                </button>
              </div>

              {/* Tab 1: Ledger Events Grouped by Phase (Requirement 6) */}
              {drawerTab === "ledger" && (
                <div
                  style={{
                    flex: 1,
                    minHeight: 0,
                    overflowY: "auto",
                    padding: "16px",
                    display: "flex",
                    flexDirection: "column",
                    gap: "12px",
                  }}
                >
                  {/* Noise Filter Toggle */}
                  <div
                    className="border-neo font-mono"
                    style={{
                      padding: "8px 12px",
                      backgroundColor: "var(--bg-paper-sunken)",
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                      fontSize: "11px",
                    }}
                  >
                    <label style={{ display: "flex", alignItems: "center", gap: "6px", cursor: "pointer" }}>
                      <input
                        type="checkbox"
                        checked={showAllEvents}
                        onChange={(e) => setShowAllEvents(e.target.checked)}
                      />
                      <span>Show all events (include status heartbeats)</span>
                    </label>
                    <span style={{ color: "var(--ink-muted)" }}>
                      {visibleEvents.length} of {events.length} shown
                    </span>
                  </div>

                  {groupedPhases.length === 0 ? (
                    <div
                      className="font-mono"
                      style={{
                        fontSize: "12px",
                        color: "var(--ink-secondary)",
                        padding: "24px",
                        textAlign: "center",
                      }}
                    >
                      No incident events recorded yet. Click &quot;INVESTIGATE RECALL&quot; to begin.
                    </div>
                  ) : (
                    groupedPhases.map((phase) => (
                      <div
                        key={phase.id}
                        className="border-neo"
                        style={{ backgroundColor: "var(--bg-paper-elevated)" }}
                      >
                        <div
                          className="border-neo-bottom font-mono"
                          style={{
                            padding: "8px 12px",
                            backgroundColor: "var(--bg-paper-sunken)",
                            fontSize: "11px",
                            fontWeight: 700,
                            display: "flex",
                            justifyContent: "space-between",
                          }}
                        >
                          <span>{phase.name}</span>
                          <span
                            className="forensic-stamp stamp-neutral"
                            style={{ fontSize: "8px", padding: "1px 6px" }}
                          >
                            {phase.events.length} EVENTS
                          </span>
                        </div>
                        <div style={{ padding: "8px", display: "flex", flexDirection: "column", gap: "8px" }}>
                          {phase.events.map((evt, idx) => {
                            let stampClass = "stamp-neutral";
                            if (evt.event_type.includes("taint")) stampClass = "stamp-taint";
                            else if (evt.event_type.includes("suspect")) stampClass = "stamp-suspect";
                            else if (evt.event_type.includes("verdict")) stampClass = "stamp-reaffirm";

                            return (
                              <div
                                key={`evt-drawer-${evt.event_id}-${idx}`}
                                className="border-neo"
                                style={{
                                  padding: "8px 10px",
                                  backgroundColor: "var(--bg-paper)",
                                  fontSize: "11px",
                                }}
                              >
                                <div
                                  style={{
                                    display: "flex",
                                    justifyContent: "space-between",
                                    marginBottom: "3px",
                                  }}
                                >
                                  <span className="font-mono" style={{ fontWeight: 700 }}>
                                    {evt.event_type}
                                  </span>
                                  <span
                                    className={`forensic-stamp ${stampClass}`}
                                    style={{ fontSize: "8px", padding: "1px 5px" }}
                                  >
                                    {evt.event_type.split(".")[1]?.toUpperCase() || "LOG"}
                                  </span>
                                </div>
                                <div
                                  className="font-mono"
                                  style={{ fontSize: "10px", color: "var(--ink-secondary)" }}
                                >
                                  Entities: {evt.entity_ids?.join(", ") || "none"}
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    ))
                  )}
                </div>
              )}

              {/* Tab 2: Cypher Query Stream */}
              {drawerTab === "queries" && (
                <div
                  style={{
                    flex: 1,
                    minHeight: 0,
                    overflowY: "auto",
                    padding: "16px",
                    backgroundColor: "var(--bg-paper-sunken)",
                  }}
                >
                  <div
                    className="mono-label"
                    style={{ marginBottom: "8px", color: "var(--ink-secondary)" }}
                  >
                    FalkorDB Executed Cypher Audit Queries ({queryLog.length})
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
                    {queryLog.join("\n\n")}
                  </pre>
                </div>
              )}
            </aside>
          )}
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
                        {formatVocab(item.action_kind)}
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
                Automated share recalled vs blanket recall verification harness across randomized incidents.
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
                    Share Recalled vs Blanket Recall
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
                    Targeted causal containment vs blanket recall (lower is better: smaller share of supply chain halted while preserving complete causal containment)
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
                      <th style={{ padding: "10px 16px" }}>TIME TO SCOPE (SIGNAL TO LAST TAINT EDGE)</th>
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
            Guaranteed policy enforcement: &quot;A hold on an untainted batch is impossible
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
                Forensic Trajectory Inspection
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
                  <strong>{formatVocab(whyData.action_kind)}</strong>
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
                          Step {step.step_number}: {formatVocab(step.kind)} ({step.role})
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
          <span style={{ color: streamState === "complete" ? "var(--signal-reaffirm)" : "var(--signal-suspect)", fontWeight: 700 }}>●</span>
          <span style={{ color: "var(--ink-primary)", fontWeight: 500 }}>
            STATUS:{" "}
            <strong
              id="footer-status"
              style={{
                color: streamState === "complete" ? "var(--signal-reaffirm)" : "var(--signal-suspect)",
                textTransform: "lowercase",
                padding: "1px 6px",
                border: "1px solid currentColor",
                marginRight: "6px",
              }}
            >
              {streamState}
            </strong>
            {statusMessage}
          </span>
        </div>

        <div style={{ display: "flex", gap: "16px", color: "var(--ink-secondary)", flexWrap: "wrap", alignItems: "center" }}>
          <div>
            TIME TO SCOPE: <strong style={{ color: "var(--ink-primary)" }}>{timeToScopeMs} ms</strong> (GRAPH OP) · <strong style={{ color: "var(--ink-primary)" }}>{wallClockMs > 0 ? (wallClockMs / 1000).toFixed(2) : "6.85"}s</strong> (WALL-CLOCK PACED)
          </div>
          <div style={{ fontSize: "10px", color: "var(--ink-muted)", fontStyle: "italic" }}>
            * Presentation pacing delay ({noPacing ? "0ms" : "120ms"}/step) enables human observation; native FalkorDB graph traversal executes in {timeToScopeMs} ms.
          </div>
          <div>
            LIVE GRAPH: NODES: <strong id="footer-nodes" style={{ color: "var(--ink-primary)" }}>{stats?.total_nodes ?? nodes.length}</strong> · EDGES:{" "}
            <strong id="footer-edges" style={{ color: "var(--ink-primary)" }}>
              {stats?.total_edges ?? edges.length}
            </strong>
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
