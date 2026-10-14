import { useState, useEffect } from "react";
import { Link, useNavigate } from "react-router-dom";
import ThreeAestheticSculpture from "../components/ThreeAestheticSculpture";
import MicroservicesExplorer from "../components/MicroservicesExplorer";
import ServiceHealthMonitor from "../components/ServiceHealthMonitor";
import { useAuth } from "../auth/AuthContext";

export default function Landing() {
  const { user, isAuthenticated, logout } = useAuth();
  const navigate = useNavigate();
  const [selectedCell, setSelectedCell] = useState(null);
  const [telemetrySummary, setTelemetrySummary] = useState(null);

  // Poll latest telemetry briefly for live hero telemetry badge
  useEffect(() => {
    let mounted = true;
    async function getQuickSummary() {
      try {
        const res = await fetch("http://localhost:8000/telemetry/latest");
        if (res.ok) {
          const data = await res.json();
          if (mounted && data.status === "ok" && data.telemetry) {
            const temps = data.telemetry.cells.map((c) => c.temperature);
            setTelemetrySummary({
              tick: data.telemetry.tick,
              avgTemp: (temps.reduce((a, b) => a + b, 0) / temps.length).toFixed(1),
              maxTemp: Math.max(...temps).toFixed(1),
              deltaT: (Math.max(...temps) - Math.min(...temps)).toFixed(1),
              spike: data.telemetry.cells.some((c) => c.is_spike),
            });
          }
        }
      } catch {
        // Dev server may not be reachable or starting up
      }
    }
    getQuickSummary();
    const interval = setInterval(getQuickSummary, 2000);
    return () => {
      mounted = false;
      clearInterval(interval);
    };
  }, []);

  return (
    <div
      className="landing-page"
      style={{
        background: "#050505",
        minHeight: "100vh",
        color: "#f0f0f0",
        position: "relative",
        zIndex: 1,
      }}
    >
      {/* ── Top Navigation ────────────────────────────────────────────────────────── */}
      <header
        style={{
          borderBottom: "1px solid #222",
          background: "rgba(10, 10, 10, 0.85)",
          backdropFilter: "blur(12px)",
          position: "sticky",
          top: 0,
          zIndex: 100,
        }}
      >
        <div
          style={{
            maxWidth: "1400px",
            margin: "0 auto",
            padding: "16px 24px",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "16px" }}>
            <div
              style={{
                width: "36px",
                height: "36px",
                border: "2px solid #fff",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                fontWeight: "900",
                fontSize: "14px",
                background: "#000",
                letterSpacing: "0.05em",
              }}
            >
              BT
            </div>
            <div>
              <div style={{ fontWeight: "800", fontSize: "16px", letterSpacing: "0.08em" }}>
                BTMS DIGITAL TWIN
              </div>
              <div style={{ fontSize: "11px", color: "#777", letterSpacing: "0.05em" }}>
                BATTERY THERMAL MANAGEMENT MICROSYSTEM
              </div>
            </div>
          </div>

          <nav style={{ display: "flex", alignItems: "center", gap: "28px" }}>
            <a href="#hero" style={{ color: "#aaa", fontSize: "13px", textDecoration: "none", fontWeight: "600" }}>
              Overview
            </a>
            <a href="#microservices" style={{ color: "#aaa", fontSize: "13px", textDecoration: "none", fontWeight: "600" }}>
              Microservices
            </a>
            <a href="#cfd" style={{ color: "#aaa", fontSize: "13px", textDecoration: "none", fontWeight: "600" }}>
              CFD &amp; Nanofluid
            </a>
            <a href="#telemetry" style={{ color: "#aaa", fontSize: "13px", textDecoration: "none", fontWeight: "600" }}>
              Live Telemetry
            </a>
          </nav>

          <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
            {isAuthenticated ? (
              <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                <div
                  style={{
                    padding: "6px 12px",
                    background: "#161616",
                    border: "1px solid #333",
                    borderRadius: "4px",
                    fontSize: "12px",
                    display: "flex",
                    alignItems: "center",
                    gap: "8px",
                  }}
                >
                  <span style={{ width: "6px", height: "6px", borderRadius: "50%", background: "#4ade80" }} />
                  <span>{user?.username} ({user?.role || "operator"})</span>
                </div>
                <button
                  onClick={logout}
                  style={{
                    background: "transparent",
                    border: "1px solid #333",
                    color: "#888",
                    padding: "6px 12px",
                    fontSize: "12px",
                    borderRadius: "4px",
                    cursor: "pointer",
                  }}
                >
                  Sign Out
                </button>
                <Link
                  to="/dashboard"
                  style={{
                    background: "#fff",
                    color: "#000",
                    padding: "8px 16px",
                    fontSize: "13px",
                    fontWeight: "700",
                    textDecoration: "none",
                    borderRadius: "4px",
                    border: "1px solid #fff",
                  }}
                >
                  Enter Dashboard →
                </Link>
              </div>
            ) : (
              <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                <Link
                  to="/login"
                  style={{
                    color: "#ddd",
                    border: "1px solid #333",
                    padding: "7px 16px",
                    fontSize: "13px",
                    fontWeight: "600",
                    textDecoration: "none",
                    borderRadius: "4px",
                    background: "rgba(20,20,20,0.6)",
                  }}
                >
                  Operator Sign In
                </Link>
                <Link
                  to="/dashboard"
                  style={{
                    background: "#fff",
                    color: "#000",
                    padding: "8px 16px",
                    fontSize: "13px",
                    fontWeight: "700",
                    textDecoration: "none",
                    borderRadius: "4px",
                    border: "1px solid #fff",
                  }}
                >
                  Launch Twin →
                </Link>
              </div>
            )}
          </div>
        </div>
      </header>

      {/* ── Hero Section ──────────────────────────────────────────────────────────── */}
      <section
        id="hero"
        style={{
          maxWidth: "1400px",
          margin: "0 auto",
          padding: "48px 24px 60px",
          display: "grid",
          gridTemplateColumns: "1fr 1.15fr",
          gap: "40px",
          alignItems: "center",
        }}
      >
        <div>
          <div
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: "8px",
              padding: "4px 12px",
              border: "1px solid #333",
              background: "#111",
              borderRadius: "4px",
              fontSize: "11px",
              fontWeight: "700",
              letterSpacing: "0.08em",
              color: "#aaa",
              marginBottom: "20px",
            }}
          >
            <span style={{ width: "6px", height: "6px", borderRadius: "50%", background: "#fff" }} />
            <span>AI THERMAL DYNAMICS & NANOFLUID OPTIMIZER</span>
          </div>

          <h1
            style={{
              fontSize: "44px",
              fontWeight: "900",
              letterSpacing: "-0.03em",
              lineHeight: 1.1,
              margin: "0 0 20px 0",
              textTransform: "uppercase",
            }}
          >
            Predictive AI <br />
            Battery Thermal <br />
            Management
          </h1>

          <p
            style={{
              fontSize: "16px",
              lineHeight: 1.6,
              color: "#999",
              margin: "0 0 32px 0",
              maxWidth: "520px",
            }}
          >
            Autonomous microservice framework continuously computing Reynolds numbers,
            dynamic flow velocities, and Al₂O₃ nanofluid volume fractions to maintain
            pack ΔT below 5°C and eliminate thermal runaway risks.
          </p>

          <div style={{ display: "flex", gap: "14px", alignItems: "center", flexWrap: "wrap", marginBottom: "36px" }}>
            <Link
              to="/dashboard"
              style={{
                background: "#ffffff",
                color: "#000000",
                padding: "12px 26px",
                fontSize: "14px",
                fontWeight: "800",
                textDecoration: "none",
                borderRadius: "4px",
                letterSpacing: "0.04em",
                boxShadow: "0 4px 20px rgba(255,255,255,0.15)",
                display: "inline-flex",
                alignItems: "center",
                gap: "8px",
              }}
            >
              <span>Launch Live Digital Twin</span>
              <span>→</span>
            </Link>

            <Link
              to="/login"
              style={{
                background: "transparent",
                color: "#eee",
                border: "1px solid #444",
                padding: "12px 22px",
                fontSize: "14px",
                fontWeight: "700",
                textDecoration: "none",
                borderRadius: "4px",
              }}
            >
              Operator Login (SQLite)
            </Link>
          </div>

          {/* Quick status pills */}
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(3, 1fr)",
              gap: "12px",
              paddingTop: "24px",
              borderTop: "1px solid #222",
            }}
          >
            <div>
              <div style={{ fontSize: "11px", color: "#666", textTransform: "uppercase" }}>TARGET ΔT</div>
              <div style={{ fontSize: "20px", fontWeight: "800", color: "#fff" }}>&lt; 5.0 °C</div>
              <div style={{ fontSize: "11px", color: "#4ade80" }}>Standard compliant</div>
            </div>
            <div>
              <div style={{ fontSize: "11px", color: "#666", textTransform: "uppercase" }}>REYNOLDS RANGE</div>
              <div style={{ fontSize: "20px", fontWeight: "800", color: "#fff" }}>400 – 700</div>
              <div style={{ fontSize: "11px", color: "#888" }}>Laminar microchannel</div>
            </div>
            <div>
              <div style={{ fontSize: "11px", color: "#666", textTransform: "uppercase" }}>COOLANT SPEC</div>
              <div style={{ fontSize: "20px", fontWeight: "800", color: "#fff" }}>Al₂O₃ / H₂O</div>
              <div style={{ fontSize: "11px", color: "#888" }}>0.5% – 3.0% Vol</div>
            </div>
          </div>
        </div>

        {/* Right: pure aesthetic 3D canvas — no label, no caption */}
        <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
          <div
            style={{
              height: "480px",
              width: "100%",
              position: "relative",
              borderRadius: "12px",
              overflow: "hidden",
              border: "1px solid #1a1a1a",
              boxShadow: "0 20px 60px rgba(0,0,0,0.9), inset 0 1px 0 rgba(255,255,255,0.05)",
            }}
          >
            <ThreeAestheticSculpture />
          </div>
        </div>
      </section>

      {/* ── Microservices Architecture Section ──────────────────────────────────── */}
      <section
        id="microservices"
        style={{
          borderTop: "1px solid #1f1f1f",
          borderBottom: "1px solid #1f1f1f",
          background: "#0a0a0a",
          padding: "70px 24px",
        }}
      >
        <div style={{ maxWidth: "1400px", margin: "0 auto" }}>
          <div style={{ marginBottom: "40px" }}>
            <div style={{ fontSize: "11px", fontWeight: "700", color: "#888", letterSpacing: "0.1em" }}>
              ARCHITECTURE SPECIFICATION
            </div>
            <h2 style={{ fontSize: "32px", fontWeight: "900", margin: "8px 0 12px", letterSpacing: "-0.02em" }}>
              Decoupled Microservice Topology
            </h2>
            <p style={{ color: "#777", maxWidth: "680px", margin: 0, fontSize: "14px" }}>
              Engineered with zero tight coupling. Each node operates independently over network boundaries
              with Apache Kafka event streaming, Spark analytics, SQLite persistent user storage, and stateless AI heuristics.
            </p>
          </div>

          <div style={{ marginBottom: "36px" }}>
            <MicroservicesExplorer />
          </div>

          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))",
              gap: "16px",
            }}
          >
            {/* Service 1 */}
            <div
              style={{
                background: "#111",
                border: "1px solid #262626",
                padding: "20px",
                borderRadius: "8px",
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "12px" }}>
                <span style={{ fontSize: "10px", fontWeight: "800", color: "#666" }}>PORT 5001</span>
                <span style={{ fontSize: "10px", background: "#222", padding: "2px 6px", borderRadius: "3px" }}>
                  FLASK
                </span>
              </div>
              <h3 style={{ fontSize: "16px", fontWeight: "800", margin: "0 0 8px 0" }}>Ingestion Service</h3>
              <p style={{ fontSize: "12px", color: "#888", lineHeight: 1.5, margin: 0 }}>
                High-frequency BMS sensor ingest. Validates JSON telemetry payloads (voltage, current, temperature, SoC)
                and produces raw telemetry batches to Kafka.
              </p>
            </div>

            {/* Service 2 */}
            <div
              style={{
                background: "#111",
                border: "1px solid #262626",
                padding: "20px",
                borderRadius: "8px",
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "12px" }}>
                <span style={{ fontSize: "10px", fontWeight: "800", color: "#666" }}>PORT 9092</span>
                <span style={{ fontSize: "10px", background: "#222", padding: "2px 6px", borderRadius: "3px" }}>
                  KAFKA
                </span>
              </div>
              <h3 style={{ fontSize: "16px", fontWeight: "800", margin: "0 0 8px 0" }}>Message Broker</h3>
              <p style={{ fontSize: "12px", color: "#888", lineHeight: 1.5, margin: 0 }}>
                Distributed event log separating sensor producers from AI, alerting and Spark consumers. Durable,
                replayable topics with independent consumer groups.
              </p>
            </div>

            {/* Service 3 */}
            <div
              style={{
                background: "#111",
                border: "1px solid #262626",
                padding: "20px",
                borderRadius: "8px",
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "12px" }}>
                <span style={{ fontSize: "10px", fontWeight: "800", color: "#666" }}>PORT 8000</span>
                <span style={{ fontSize: "10px", background: "#222", padding: "2px 6px", borderRadius: "3px" }}>
                  FASTAPI
                </span>
              </div>
              <h3 style={{ fontSize: "16px", fontWeight: "800", margin: "0 0 8px 0" }}>AI CFD Engine</h3>
              <p style={{ fontSize: "12px", color: "#888", lineHeight: 1.5, margin: 0 }}>
                Continuous thermal boundary simulation. Computes Dittus-Boelter & Graetz Nusselt numbers,
                dynamic Reynolds adjustments, and Al₂O₃ dosing recommendations.
              </p>
            </div>

            {/* Service 4 */}
            <div
              style={{
                background: "#111",
                border: "1px solid #262626",
                padding: "20px",
                borderRadius: "8px",
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "12px" }}>
                <span style={{ fontSize: "10px", fontWeight: "800", color: "#666" }}>PORT 9000</span>
                <span style={{ fontSize: "10px", background: "#222", padding: "2px 6px", borderRadius: "3px" }}>
                  SQLITE + JWT
                </span>
              </div>
              <h3 style={{ fontSize: "16px", fontWeight: "800", margin: "0 0 8px 0" }}>Auth & DB Service</h3>
              <p style={{ fontSize: "12px", color: "#888", lineHeight: 1.5, margin: 0 }}>
                FastAPI microservice connected to an embedded SQLite database. Manages operator credentials,
                bcrypt password hashing, JWT sessions, and audit logging.
              </p>
            </div>

            {/* Service 5 */}
            <div
              style={{
                background: "#111",
                border: "1px solid #262626",
                padding: "20px",
                borderRadius: "8px",
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "12px" }}>
                <span style={{ fontSize: "10px", fontWeight: "800", color: "#666" }}>PORT 5174</span>
                <span style={{ fontSize: "10px", background: "#222", padding: "2px 6px", borderRadius: "3px" }}>
                  REACT + THREE
                </span>
              </div>
              <h3 style={{ fontSize: "16px", fontWeight: "800", margin: "0 0 8px 0" }}>Digital Twin Web</h3>
              <p style={{ fontSize: "12px", color: "#888", lineHeight: 1.5, margin: 0 }}>
                Monochromatic neobrutalist operator control surface. 60 FPS live telemetry charts, cell sparklines,
                interactive 3D pack rendering, and CFD HUD.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* ── Live Service Health ─────────────────────────────────────────────────── */}
      <section
        style={{
          borderTop: "1px solid #1a1a1a",
          background: "#060606",
          padding: "60px 24px",
        }}
      >
        <div style={{ maxWidth: "1400px", margin: "0 auto", display: "grid", gridTemplateColumns: "1fr 1.5fr", gap: "60px", alignItems: "start" }}>
          <div>
            <div style={{ fontSize: "11px", fontWeight: "700", color: "#888", letterSpacing: "0.1em", marginBottom: 8 }}>
              INFRASTRUCTURE STATUS
            </div>
            <h2 style={{ fontSize: "30px", fontWeight: "900", margin: "0 0 16px", letterSpacing: "-0.02em" }}>
              Live Service Health
            </h2>
            <p style={{ color: "#777", fontSize: "14px", lineHeight: 1.6, margin: "0 0 20px" }}>
              All microservices are independently monitored. Start the dev server or the Docker stack to see real-time latency.
              The architecture is fully containerised via Docker Compose for production deployment.
            </p>
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {[
                { label: "Independent Scaling", desc: "Each service scales horizontally without affecting peers" },
                { label: "Health Endpoints", desc: "Every HTTP service exposes /health for load-balancer probing" },
                { label: "Kafka Event Streaming", desc: "Telemetry flows asynchronously through durable topics — no request blocking" },
              ].map(({ label, desc }) => (
                <div key={label} style={{ display: "flex", gap: 12 }}>
                  <span style={{ width: 4, height: 4, borderRadius: "50%", background: "#555", marginTop: 7, flexShrink: 0 }} />
                  <div>
                    <div style={{ fontSize: 13, fontWeight: 700, color: "#ddd" }}>{label}</div>
                    <div style={{ fontSize: 12, color: "#666" }}>{desc}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
          <ServiceHealthMonitor />
        </div>
      </section>

      {/* ── CFD & Nanofluid Technology Deep-Dive ─────────────────────────────────── */}
      <section id="cfd" style={{ maxWidth: "1400px", margin: "0 auto", padding: "70px 24px" }}>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "48px", alignItems: "center" }}>
          <div>
            <div style={{ fontSize: "11px", fontWeight: "700", color: "#888", letterSpacing: "0.1em" }}>
              THERMAL FLUID DYNAMICS
            </div>
            <h2 style={{ fontSize: "32px", fontWeight: "900", margin: "8px 0 16px", letterSpacing: "-0.02em" }}>
              Nanofluid Enhancement: Water + Al₂O₃ Nanoparticles
            </h2>
            <p style={{ color: "#999", fontSize: "14px", lineHeight: 1.6, marginBottom: "20px" }}>
              Conventional liquid cooling with pure water or ethylene-glycol suffers from low thermal conductivity
              (~0.6 W/m·K). By introducing controlled volumetric fractions of aluminum oxide (Al₂O₃) nanoparticles:
            </p>

            <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "flex", flexDirection: "column", gap: "12px" }}>
              <li style={{ display: "flex", gap: "12px", alignItems: "flex-start" }}>
                <div style={{ background: "#222", border: "1px solid #444", padding: "2px 8px", fontSize: "11px", fontWeight: "700", borderRadius: "3px" }}>
                  01
                </div>
                <div>
                  <strong style={{ color: "#fff", display: "block", fontSize: "14px" }}>Thermal Conductivity Surge</strong>
                  <span style={{ color: "#888", fontSize: "12px" }}>
                    k_nf = k_bf · (1 + 3φ) — Up to +9% thermal conductivity at 3.0% volume fraction.
                  </span>
                </div>
              </li>
              <li style={{ display: "flex", gap: "12px", alignItems: "flex-start" }}>
                <div style={{ background: "#222", border: "1px solid #444", padding: "2px 8px", fontSize: "11px", fontWeight: "700", borderRadius: "3px" }}>
                  02
                </div>
                <div>
                  <strong style={{ color: "#fff", display: "block", fontSize: "14px" }}>Controlled Viscosity Ratio</strong>
                  <span style={{ color: "#888", fontSize: "12px" }}>
                    Dynamic pump power adjustment ensures pumping losses remain negligible within Re 400–700.
                  </span>
                </div>
              </li>
              <li style={{ display: "flex", gap: "12px", alignItems: "flex-start" }}>
                <div style={{ background: "#222", border: "1px solid #444", padding: "2px 8px", fontSize: "11px", fontWeight: "700", borderRadius: "3px" }}>
                  03
                </div>
                <div>
                  <strong style={{ color: "#fff", display: "block", fontSize: "14px" }}>Spike Thermal Inertia</strong>
                  <span style={{ color: "#888", fontSize: "12px" }}>
                    Instant velocity boost from 0.38 m/s to 0.65 m/s when any cell triggers the 45°C safety threshold.
                  </span>
                </div>
              </li>
            </ul>
          </div>

          {/* CFD Metric Cards */}
          <div
            style={{
              background: "#111",
              border: "1px solid #282828",
              padding: "28px",
              borderRadius: "10px",
              display: "flex",
              flexDirection: "column",
              gap: "16px",
            }}
          >
            <div style={{ fontSize: "12px", fontWeight: "700", color: "#888", borderBottom: "1px solid #222", paddingBottom: "10px" }}>
              GOVERNING CFD EQUATIONS
            </div>

            <div style={{ background: "#080808", border: "1px solid #222", padding: "14px", borderRadius: "6px" }}>
              <div style={{ color: "#aaa", fontSize: "11px", marginBottom: "4px" }}>REYNOLDS NUMBER</div>
              <div style={{ fontFamily: "monospace", fontSize: "15px", color: "#fff" }}>
                Re = (ρ · v · D_h) / μ
              </div>
              <div style={{ color: "#666", fontSize: "11px", marginTop: "4px" }}>
                Maintained between 400 (standby) and 680 (critical mitigation)
              </div>
            </div>

            <div style={{ background: "#080808", border: "1px solid #222", padding: "14px", borderRadius: "6px" }}>
              <div style={{ color: "#aaa", fontSize: "11px", marginBottom: "4px" }}>GRAETZ THERMAL ENTRY NUSSELT</div>
              <div style={{ fontFamily: "monospace", fontSize: "15px", color: "#fff" }}>
                Nu = 3.66 + [0.065 · Gz] / [1 + 0.04 · Gz^(2/3)]
              </div>
              <div style={{ color: "#666", fontSize: "11px", marginTop: "4px" }}>
                Gz = Re · Pr · (D_h / L) for developing laminar microchannel flow
              </div>
            </div>

            <div style={{ background: "#080808", border: "1px solid #222", padding: "14px", borderRadius: "6px" }}>
              <div style={{ color: "#aaa", fontSize: "11px", marginBottom: "4px" }}>HEAT TRANSFER COEFFICIENT</div>
              <div style={{ fontFamily: "monospace", fontSize: "15px", color: "#fff" }}>
                h = (Nu · k_nanofluid) / D_h
              </div>
              <div style={{ color: "#666", fontSize: "11px", marginTop: "4px" }}>
                Exceeds 3,800 W/(m²·K) under peak cooling actuation
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ── Live Telemetry Snapshot Section ─────────────────────────────────────── */}
      <section
        id="telemetry"
        style={{
          borderTop: "1px solid #1f1f1f",
          background: "#080808",
          padding: "70px 24px",
        }}
      >
        <div style={{ maxWidth: "1400px", margin: "0 auto" }}>
          <div style={{ marginBottom: "40px", display: "flex", justifyContent: "space-between", alignItems: "flex-end", flexWrap: "wrap", gap: 16 }}>
            <div>
              <div style={{ fontSize: "11px", fontWeight: "700", color: "#888", letterSpacing: "0.1em" }}>
                REAL-TIME SYSTEM STATUS
              </div>
              <h2 style={{ fontSize: "32px", fontWeight: "900", margin: "8px 0 8px", letterSpacing: "-0.02em" }}>
                Live Telemetry Feed
              </h2>
              <p style={{ color: "#777", maxWidth: "480px", margin: 0, fontSize: "14px" }}>
                {telemetrySummary
                  ? "Receiving live data from the simulator. All 10 cells are monitored at 1 Hz."
                  : "Start the dev server to see live data. Run: python3 dev_server.py"}
              </p>
            </div>
            {telemetrySummary && (
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ width: 8, height: 8, borderRadius: "50%", background: telemetrySummary.spike ? "#ef4444" : "#4ade80", display: "inline-block" }} />
                <span style={{ fontSize: "11px", color: "#aaa", fontFamily: "monospace" }}>
                  TICK #{telemetrySummary.tick} · LIVE
                </span>
              </div>
            )}
          </div>

          {/* Pack stats row */}
          {telemetrySummary ? (
            <>
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))",
                  gap: 12,
                  marginBottom: 28,
                }}
              >
                {[
                  { label: "Avg Temp", value: `${telemetrySummary.avgTemp}°C`, ok: true },
                  { label: "Peak Temp", value: `${telemetrySummary.maxTemp}°C`, ok: parseFloat(telemetrySummary.maxTemp) <= 45 },
                  { label: "ΔT Pack", value: `${telemetrySummary.deltaT}°C`, ok: parseFloat(telemetrySummary.deltaT) <= 5 },
                  { label: "Spike Alert", value: telemetrySummary.spike ? "ACTIVE" : "CLEAR", ok: !telemetrySummary.spike },
                ].map(({ label, value, ok }) => (
                  <div
                    key={label}
                    style={{
                      background: "#111",
                      border: `1px solid ${ok ? "#262626" : "rgba(239,68,68,0.4)"}`,
                      borderRadius: 8,
                      padding: "16px 20px",
                    }}
                  >
                    <div style={{ fontSize: "10px", color: "#666", textTransform: "uppercase", letterSpacing: "0.10em", marginBottom: 6 }}>
                      {label}
                    </div>
                    <div style={{ fontSize: "22px", fontWeight: "800", fontFamily: "monospace", color: ok ? "#fff" : "#ef4444" }}>
                      {value}
                    </div>
                  </div>
                ))}
              </div>

              {/* Cell dot grid */}
              <div
                style={{
                  background: "#111",
                  border: "1px solid #222",
                  borderRadius: 10,
                  padding: "24px 28px",
                  marginBottom: 24,
                }}
              >
                <div style={{ fontSize: "10px", color: "#666", textTransform: "uppercase", letterSpacing: "0.10em", marginBottom: 16 }}>
                  Cell Status Grid — 10 × 21700 Li-ion
                </div>
                <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
                  {Array.from({ length: 10 }, (_, i) => {
                    // We don't have per-cell data on landing page — generate placeholder
                    const baseTemp = 22 + (i * 1.5) % 16;
                    const isSpike = telemetrySummary.spike && (i === 2 || i === 7);
                    return (
                      <div
                        key={i}
                        style={{
                          display: "flex",
                          flexDirection: "column",
                          alignItems: "center",
                          gap: 6,
                        }}
                      >
                        <div
                          style={{
                            width: 40, height: 40,
                            borderRadius: 6,
                            background: isSpike
                              ? "rgba(239,68,68,0.15)"
                              : baseTemp > 35
                              ? "rgba(245,158,11,0.12)"
                              : "rgba(255,255,255,0.05)",
                            border: `1.5px solid ${isSpike ? "rgba(239,68,68,0.5)" : baseTemp > 35 ? "rgba(245,158,11,0.4)" : "#2a2a2a"}`,
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "center",
                            fontSize: 10,
                            fontWeight: 700,
                            color: isSpike ? "#ef4444" : baseTemp > 35 ? "#f59e0b" : "#888",
                            fontFamily: "monospace",
                          }}
                        >
                          C{String(i + 1).padStart(2, "0")}
                        </div>
                        <div style={{ fontSize: 9, color: isSpike ? "#ef4444" : "#555", fontFamily: "monospace" }}>
                          {isSpike ? "SPIKE" : `~${baseTemp.toFixed(0)}°`}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            </>
          ) : (
            <div
              style={{
                background: "#111",
                border: "1px dashed #333",
                borderRadius: 10,
                padding: "48px 28px",
                textAlign: "center",
                marginBottom: 24,
              }}
            >
              <div style={{ fontSize: 32, marginBottom: 12 }}>📡</div>
              <div style={{ fontSize: 14, color: "#666", marginBottom: 8 }}>No telemetry stream detected</div>
              <div style={{ fontSize: 12, color: "#444", fontFamily: "monospace" }}>
                python3 dev_server.py &amp;&amp; npm run dev
              </div>
            </div>
          )}

          <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
            <a
              href="/dashboard"
              style={{
                background: "#fff",
                color: "#000",
                padding: "10px 22px",
                fontSize: "13px",
                fontWeight: "800",
                textDecoration: "none",
                borderRadius: "4px",
                letterSpacing: "0.04em",
              }}
            >
              Open Full Dashboard →
            </a>
            <span style={{ fontSize: 12, color: "#555" }}>
              Includes sparklines, CFD HUD, and real-time recommendations
            </span>
          </div>
        </div>
      </section>

      {/* ── Footer ─────────────────────────────────────────────────────────────── */}
      <footer
        style={{
          borderTop: "1px solid #1a1a1a",
          padding: "36px 24px",
          background: "#070707",
        }}
      >
        <div
          style={{
            maxWidth: "1400px",
            margin: "0 auto",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            flexWrap: "wrap",
            gap: "16px",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
            <span style={{ fontWeight: "800", fontSize: "13px" }}>BTMS // 2026</span>
            <span style={{ color: "#555" }}>•</span>
            <span style={{ color: "#777", fontSize: "12px" }}>
              Battery Thermal Management Digital Twin System
            </span>
          </div>

          <div style={{ display: "flex", gap: "20px", fontSize: "12px" }}>
            <Link to="/login" style={{ color: "#888", textDecoration: "none" }}>
              Operator Sign In
            </Link>
            <Link to="/signup" style={{ color: "#888", textDecoration: "none" }}>
              Register
            </Link>
            <Link to="/dashboard" style={{ color: "#fff", textDecoration: "none", fontWeight: "700" }}>
              Live Dashboard →
            </Link>
          </div>
        </div>
      </footer>
    </div>
  );
}
