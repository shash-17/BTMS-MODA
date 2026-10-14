import { useState, useEffect, useRef } from "react";

const SERVICES = [
  {
    id: "ai-engine",
    name: "AI CFD Engine",
    port: 8000,
    url: "http://localhost:8000/health",
    tag: "FASTAPI",
    desc: "Thermal optimizer",
  },
  {
    id: "auth-service",
    name: "Auth Service",
    port: 9000,
    url: "http://localhost:9000/auth/health",
    tag: "SQLITE+JWT",
    desc: "Operator auth",
  },
  {
    id: "ingestion",
    name: "Ingestion Service",
    port: 5001,
    url: "http://localhost:5001/health",
    tag: "FLASK",
    desc: "Sensor ingest",
  },
  {
    id: "message-broker",
    name: "Message Broker",
    port: 9092,
    // Kafka has no HTTP endpoint — infer from AI engine kafka flag
    url: null,
    tag: "KAFKA",
    desc: "Event streaming (KRaft)",
  },
  {
    id: "spark-streaming",
    name: "Spark Streaming",
    port: "—",
    // Spark has no HTTP endpoint — infer from analytics API lake_ready flag
    url: null,
    tag: "SPARK",
    desc: "Kafka → Parquet lake",
  },
  {
    id: "analytics-api",
    name: "Analytics API",
    port: 8100,
    url: "http://localhost:8100/health",
    tag: "PYARROW",
    desc: "Data lake analytics",
  },
  {
    id: "alert-service",
    name: "Alert Service",
    port: 8200,
    url: "http://localhost:8200/health",
    tag: "KAFKA+SQLITE",
    desc: "Anomaly alert store",
  },
  {
    id: "dashboard",
    name: "Dashboard",
    port: typeof window !== "undefined" ? window.location.port || 5173 : 5173,
    url: typeof window !== "undefined" ? window.location.origin : "http://localhost:5173",
    tag: "REACT+THREE",
    desc: "Digital twin UI",
  },
];

const PING_INTERVAL_MS = 5000;

function StatusDot({ status }) {
  if (status === "up")   return <span style={{ width: 8, height: 8, borderRadius: "50%", background: "var(--ok)",  display: "inline-block", boxShadow: "0 0 6px var(--ok)" }} />;
  if (status === "down") return <span style={{ width: 8, height: 8, borderRadius: "50%", background: "var(--crit)", display: "inline-block", boxShadow: "0 0 6px var(--crit)" }} />;
  return <span style={{ width: 8, height: 8, borderRadius: "50%", background: "var(--bw-300)", display: "inline-block", animation: "blink 1.1s ease infinite" }} />;
}

function LatencyBar({ latency }) {
  if (!latency) return null;
  // Good < 50ms, ok < 200ms, slow > 200ms
  const pct = Math.min(100, (latency / 300) * 100);
  const color = latency < 50 ? "var(--ok)" : latency < 200 ? "var(--warn)" : "var(--crit)";
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 4 }}>
      <div style={{ flex: 1, height: 2, background: "rgba(255,255,255,0.07)", borderRadius: 2, overflow: "hidden" }}>
        <div style={{ width: `${pct}%`, height: "100%", background: color, borderRadius: 2, transition: "width 0.4s ease" }} />
      </div>
      <span style={{ fontSize: 9, fontFamily: "var(--font-mono)", color: "var(--bw-400)", minWidth: 32, textAlign: "right" }}>
        {latency}ms
      </span>
    </div>
  );
}

async function pingService(service) {
  if (service.id === "dashboard") {
    return { status: "up", latency: 1 };
  }
  if (!service.url) return { status: "unknown", latency: null };
  const t0 = performance.now();
  try {
    const res = await fetch(service.url, { method: "GET", mode: "cors", signal: AbortSignal.timeout(3000) });
    const latency = Math.round(performance.now() - t0);
    return { status: res.ok ? "up" : "down", latency };
  } catch {
    return { status: "down", latency: null };
  }
}

export default function ServiceHealthMonitor({ compact = false }) {
  const [statuses, setStatuses] = useState(() =>
    Object.fromEntries(SERVICES.map((s) => [s.id, { status: "checking", latency: null }]))
  );
  const [lastChecked, setLastChecked] = useState(null);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => { mountedRef.current = false; };
  }, []);

  const checkAll = async () => {
    // Check all pingable services in parallel
    const results = await Promise.all(
      SERVICES.map(async (s) => {
        if (s.id === "message-broker" || s.id === "spark-streaming") {
          // Inferred below from AI engine / analytics API health payloads
          return [s.id, { status: "unknown", latency: null }];
        }
        const result = await pingService(s);
        return [s.id, result];
      })
    );
    if (!mountedRef.current) return;

    const map = Object.fromEntries(results);

    // Infer Kafka from AI engine health if available
    if (map["ai-engine"]?.status === "up") {
      try {
        const r = await fetch("http://localhost:8000/health");
        const j = await r.json();
        map["message-broker"] = {
          status: j.kafka === undefined ? "unknown" : j.kafka ? "up" : "down",
          latency: null,
        };
      } catch {
        map["message-broker"] = { status: "unknown", latency: null };
      }
    }

    // Infer Spark from analytics API: lake_ready means Spark has written the raw layer
    if (map["analytics-api"]?.status === "up") {
      try {
        const r = await fetch("http://localhost:8100/health");
        const j = await r.json();
        map["spark-streaming"] = { status: j.lake_ready ? "up" : "down", latency: null };
      } catch {
        map["spark-streaming"] = { status: "unknown", latency: null };
      }
    } else {
      map["spark-streaming"] = { status: "unknown", latency: null };
    }

    setStatuses(map);
    setLastChecked(new Date());
  };

  useEffect(() => {
    checkAll();
    const interval = setInterval(checkAll, PING_INTERVAL_MS);
    return () => clearInterval(interval);
  }, []);

  const upCount = Object.values(statuses).filter((s) => s.status === "up").length;
  const total = SERVICES.length;
  const allOk = upCount === total;

  if (compact) {
    // Compact inline badges for use in navbar/footer
    return (
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        {SERVICES.map((s) => {
          const st = statuses[s.id];
          return (
            <div
              key={s.id}
              title={`${s.name} :${s.port} — ${st.status}${st.latency ? ` (${st.latency}ms)` : ""}`}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 4,
                padding: "2px 7px",
                borderRadius: 3,
                fontSize: 9,
                fontWeight: 700,
                fontFamily: "var(--font-mono)",
                letterSpacing: "0.06em",
                border: "1px solid var(--glass-border)",
                background: "var(--glass-1)",
                color: st.status === "up" ? "var(--ok)" : st.status === "down" ? "var(--crit)" : "var(--bw-400)",
              }}
            >
              <StatusDot status={st.status} />
              {s.tag}
            </div>
          );
        })}
      </div>
    );
  }

  return (
    <div
      style={{
        background: "var(--glass-1)",
        border: "1.5px solid var(--glass-border-bright)",
        borderRadius: "var(--r-xl)",
        overflow: "hidden",
        boxShadow: "var(--neo-shadow-lg)",
      }}
    >
      {/* Header */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "14px 20px",
          borderBottom: "1px solid var(--glass-border)",
          background: "var(--glass-2)",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span style={{ fontSize: 10, fontWeight: 800, letterSpacing: "0.14em", textTransform: "uppercase", color: "var(--bw-500)" }}>
            Service Health
          </span>
          <span
            style={{
              padding: "2px 8px",
              borderRadius: 3,
              fontSize: 9,
              fontWeight: 700,
              fontFamily: "var(--font-mono)",
              background: allOk ? "var(--ok-bg)" : "var(--warn-bg)",
              border: `1px solid ${allOk ? "var(--ok-border)" : "var(--warn-border)"}`,
              color: allOk ? "var(--ok)" : "var(--warn)",
            }}
          >
            {upCount}/{total} UP
          </span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          {lastChecked && (
            <span style={{ fontSize: 9, color: "var(--bw-400)", fontFamily: "var(--font-mono)" }}>
              {lastChecked.toLocaleTimeString()}
            </span>
          )}
          <button
            onClick={checkAll}
            style={{
              background: "var(--glass-2)",
              border: "1px solid var(--glass-border-bright)",
              borderRadius: "var(--r-sm)",
              color: "var(--bw-500)",
              fontSize: 10,
              fontWeight: 700,
              padding: "3px 8px",
              cursor: "pointer",
              letterSpacing: "0.06em",
            }}
          >
            ↺ Refresh
          </button>
        </div>
      </div>

      {/* Service rows */}
      <div style={{ display: "flex", flexDirection: "column" }}>
        {SERVICES.map((s, idx) => {
          const st = statuses[s.id];
          return (
            <div
              key={s.id}
              style={{
                display: "grid",
                gridTemplateColumns: "24px 1fr auto",
                alignItems: "center",
                gap: 12,
                padding: "12px 20px",
                borderBottom: idx < SERVICES.length - 1 ? "1px solid rgba(255,255,255,0.04)" : "none",
                transition: "background 0.15s ease",
              }}
              onMouseEnter={(e) => { e.currentTarget.style.background = "rgba(255,255,255,0.02)"; }}
              onMouseLeave={(e) => { e.currentTarget.style.background = "transparent"; }}
            >
              {/* Status dot */}
              <div style={{ display: "flex", justifyContent: "center" }}>
                <StatusDot status={st.status} />
              </div>

              {/* Service info */}
              <div style={{ minWidth: 0 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 3 }}>
                  <span style={{ fontSize: 12, fontWeight: 700, color: "var(--bw-800)" }}>{s.name}</span>
                  <span
                    style={{
                      fontSize: 9,
                      fontWeight: 700,
                      padding: "1px 6px",
                      borderRadius: 2,
                      background: "rgba(255,255,255,0.06)",
                      border: "1px solid var(--glass-border)",
                      color: "var(--bw-400)",
                      fontFamily: "var(--font-mono)",
                      letterSpacing: "0.06em",
                    }}
                  >
                    {s.tag}
                  </span>
                </div>
                <div style={{ fontSize: 10, color: "var(--bw-400)", fontFamily: "var(--font-mono)", display: "flex", alignItems: "center", gap: 6 }}>
                  <span>{s.port === "—" ? "no port" : `:${s.port}`}</span>
                  <span style={{ color: "var(--bw-200)" }}>·</span>
                  <span>{s.desc}</span>
                </div>
                {st.latency !== null && <LatencyBar latency={st.latency} />}
              </div>

              {/* Status chip */}
              <div
                style={{
                  fontSize: 9,
                  fontWeight: 800,
                  letterSpacing: "0.12em",
                  textTransform: "uppercase",
                  padding: "3px 8px",
                  borderRadius: 3,
                  fontFamily: "var(--font-mono)",
                  color: st.status === "up" ? "var(--ok)" : st.status === "down" ? "var(--crit)" : "var(--bw-400)",
                  background: st.status === "up" ? "var(--ok-bg)" : st.status === "down" ? "var(--crit-bg)" : "var(--glass-1)",
                  border: `1px solid ${st.status === "up" ? "var(--ok-border)" : st.status === "down" ? "var(--crit-border)" : "var(--glass-border)"}`,
                  whiteSpace: "nowrap",
                }}
              >
                {st.status === "checking" ? "..." : st.status}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
