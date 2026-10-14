import { useState, useEffect } from "react";

const MICROSERVICES = [
  {
    id: "ingestion",
    name: "Sensor Ingestion Service",
    port: "5001",
    tech: "Python Flask",
    role: "Sensor Telemetry Ingest & Validation",
    statusEndpoint: null,
    defaultStatus: "Active (Producer)",
    description:
      "High-throughput HTTP ingestion gateway receiving 10-cell battery packet telemetry (voltage, current, temperature, state-of-charge). Validates payload schemas and produces batches to the Kafka battery_stream topic.",
    inputs: "JSON Telemetry from BMS / CAN bus emulator",
    outputs: "Kafka message on topic `battery_stream` (key: btms-pack)",
    docker: {
      image: "python:3.11-slim",
      portMapping: "5001:5000",
      env: ["KAFKA_BOOTSTRAP_SERVERS=message-broker:19092", "KAFKA_TOPIC=battery_stream"],
    },
    codeSample: `{
  "pack_id": "BTMS-PACK-001",
  "tick": 2341,
  "cells": [
    { "cell_id": 0, "voltage": 3.42, "current": 2.59, "temperature": 21.3, "soc": 73.2 }
  ]
}`,
  },
  {
    id: "broker",
    name: "Message Broker",
    port: "9092",
    tech: "Apache Kafka",
    role: "Distributed Event Streaming",
    statusEndpoint: null,
    defaultStatus: "Running (KRaft)",
    description:
      "Apache Kafka 3.8.0 in KRaft mode (no Zookeeper) decoupling ingestion from the AI engine and the Spark analytics pipeline. Independent consumer groups each receive every message from a durable, replayable log.",
    inputs: "Produced JSON telemetry from Ingestion Service",
    outputs: "battery_stream consumed by AI Engine and Spark; btms_alerts consumed by Alert Service",
    docker: {
      image: "apache/kafka:3.8.0",
      portMapping: "9092:9092",
      env: ["KAFKA_PROCESS_ROLES=broker,controller", "KAFKA_LOG_RETENTION_MS=600000"],
    },
    codeSample: `# Topics
battery_stream         raw telemetry
btms_recommendations   per-tick cooling directives
btms_alerts            anomaly events

# Consumer groups
btms-ai-engine, btms-alert-service, spark`,
  },
  {
    id: "ai_engine",
    name: "AI CFD Optimization Engine",
    port: "8000",
    tech: "FastAPI + Uvicorn",
    role: "CFD Thermal Boundary Heuristics",
    statusEndpoint: "http://localhost:8000/health",
    defaultStatus: "Online (Solver)",
    description:
      "Continuous computational fluid dynamics optimizer. Solves Dittus-Boelter & Graetz Nusselt correlations, determines optimal Reynolds numbers (400–700), flow velocities, and Al₂O₃ nanofluid volume dosing.",
    inputs: "Real-time 10-cell temperatures & gradient history",
    outputs: "Optimal Re target, Al₂O₃ vol%, flow rate (mL/min), HTC (W/m²·K)",
    docker: {
      image: "python:3.11-slim",
      portMapping: "8000:8000",
      env: ["KAFKA_BOOTSTRAP_SERVERS=message-broker:19092", "KAFKA_GROUP_ID=btms-ai-engine"],
    },
    codeSample: `{
  "severity": "critical",
  "target_re": 680.0,
  "al2o3_vol_percent": 3.0,
  "flow_velocity_m_s": 0.6007,
  "heat_transfer_coeff_W_m2K": 3621.76,
  "nusselt_number": 5.474
}`,
  },
  {
    id: "auth_service",
    name: "Auth & User Store Service",
    port: "9000",
    tech: "FastAPI + SQLite 3",
    role: "JWT Identity & Audit Logging",
    statusEndpoint: "http://localhost:9000/auth/health",
    defaultStatus: "Online (SQLite)",
    description:
      "Dedicated authentication microservice connected to an embedded SQLite database (btms_users.db). Implements bcrypt password hashing, HS256 JWT access tokens, and access audit logging.",
    inputs: "Operator credentials (register / login)",
    outputs: "Signed JWT Bearer tokens & user session profiles",
    docker: {
      image: "python:3.11-slim",
      portMapping: "9000:9000",
      env: ["DB_PATH=/data/btms_users.db", "JWT_SECRET=***"],
    },
    codeSample: `-- SQLite Schema (btms_users.db)
CREATE TABLE users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  username TEXT UNIQUE NOT NULL,
  email TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  role TEXT DEFAULT 'operator',
  last_login TEXT
);`,
  },
  {
    id: "dashboard",
    name: "Digital Twin Web Surface",
    port: "5174 / 3000",
    tech: "React 19 + Three.js + Vite",
    role: "WebGL 3D Twin & Telemetry HUD",
    statusEndpoint: null,
    defaultStatus: "Connected (Client)",
    description:
      "Monochromatic neobrutalist operator control console. Renders 60 FPS Three.js 3D cylindrical lithium pack, per-cell sparklines, live telemetry curves, and CFD actuation controls.",
    inputs: "REST polling / SSE from AI Engine (:8000) and Auth (:9000)",
    outputs: "Operator interactions, cooling overrides, visual analytics",
    docker: {
      image: "nginx:alpine",
      portMapping: "3000:80",
      env: ["VITE_AI_ENGINE_URL=/api", "VITE_AUTH_URL=/auth"],
    },
    codeSample: `// Vite Dev Proxy:
proxy: {
  "/api":  { target: "http://localhost:8000" },
  "/auth": { target: "http://localhost:9000" }
}`,
  },
];

export default function MicroservicesExplorer() {
  const [selectedService, setSelectedService] = useState(MICROSERVICES[2]); // Default AI Engine
  const [healthStatus, setHealthStatus] = useState({
    ai_engine: "checking",
    auth_service: "checking",
  });

  // Probe live endpoints
  useEffect(() => {
    let mounted = true;
    async function checkHealth() {
      // AI Engine
      try {
        const res = await fetch("http://localhost:8000/health", { method: "GET" });
        if (mounted) {
          setHealthStatus((prev) => ({ ...prev, ai_engine: res.ok ? "healthy" : "offline" }));
        }
      } catch {
        if (mounted) setHealthStatus((prev) => ({ ...prev, ai_engine: "offline" }));
      }

      // Auth Service
      try {
        const res = await fetch("http://localhost:9000/auth/health", { method: "GET" });
        if (mounted) {
          setHealthStatus((prev) => ({ ...prev, auth_service: res.ok ? "healthy" : "offline" }));
        }
      } catch {
        if (mounted) setHealthStatus((prev) => ({ ...prev, auth_service: "offline" }));
      }
    }

    checkHealth();
    const timer = setInterval(checkHealth, 5000);
    return () => {
      mounted = false;
      clearInterval(timer);
    };
  }, []);

  return (
    <div style={{ background: "#0c0c0c", border: "1px solid #242424", borderRadius: "12px", overflow: "hidden" }}>
      {/* ── Header Strip ────────────────────────────────────────────────────────── */}
      <div
        style={{
          padding: "18px 24px",
          borderBottom: "1px solid #202020",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          flexWrap: "wrap",
          gap: "12px",
          background: "#111",
        }}
      >
        <div>
          <div style={{ fontSize: "11px", fontWeight: "700", color: "#888", letterSpacing: "0.08em" }}>
            DECOUPLED ARCHITECTURAL TOPOLOGY
          </div>
          <h3 style={{ fontSize: "18px", fontWeight: "800", color: "#fff", margin: "4px 0 0" }}>
            BTMS Microservices Pipeline
          </h3>
        </div>

        <div style={{ display: "flex", gap: "10px", alignItems: "center" }}>
          <div
            style={{
              padding: "4px 10px",
              background: "#181818",
              border: "1px solid #333",
              borderRadius: "4px",
              fontSize: "11px",
              display: "flex",
              alignItems: "center",
              gap: "6px",
            }}
          >
            <span
              style={{
                width: "6px",
                height: "6px",
                borderRadius: "50%",
                background: healthStatus.ai_engine === "healthy" ? "#4ade80" : "#ef4444",
              }}
            />
            <span style={{ color: "#aaa" }}>AI Engine :8000</span>
          </div>

          <div
            style={{
              padding: "4px 10px",
              background: "#181818",
              border: "1px solid #333",
              borderRadius: "4px",
              fontSize: "11px",
              display: "flex",
              alignItems: "center",
              gap: "6px",
            }}
          >
            <span
              style={{
                width: "6px",
                height: "6px",
                borderRadius: "50%",
                background: healthStatus.auth_service === "healthy" ? "#4ade80" : "#ef4444",
              }}
            />
            <span style={{ color: "#aaa" }}>Auth & SQLite :9000</span>
          </div>

          <div
            style={{
              padding: "4px 10px",
              background: "#181818",
              border: "1px solid #333",
              borderRadius: "4px",
              fontSize: "11px",
              color: "#aaa",
            }}
          >
            Network: <code>btms-net</code>
          </div>
        </div>
      </div>

      {/* ── Pipeline Flow Schematic ─────────────────────────────────────────────── */}
      <div
        style={{
          padding: "20px 24px",
          background: "#080808",
          borderBottom: "1px solid #1f1f1f",
          overflowX: "auto",
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            minWidth: "750px",
            position: "relative",
          }}
        >
          {MICROSERVICES.map((s, idx) => {
            const isSelected = selectedService.id === s.id;
            return (
              <div key={s.id} style={{ display: "flex", alignItems: "center", flex: 1 }}>
                <button
                  type="button"
                  onClick={() => setSelectedService(s)}
                  style={{
                    background: isSelected ? "#fff" : "#141414",
                    color: isSelected ? "#000" : "#eee",
                    border: isSelected ? "2px solid #fff" : "1px solid #333",
                    padding: "12px 14px",
                    borderRadius: "6px",
                    cursor: "pointer",
                    textAlign: "left",
                    flex: 1,
                    transition: "all 0.15s ease",
                    boxShadow: isSelected ? "0 4px 16px rgba(255,255,255,0.2)" : "none",
                  }}
                >
                  <div
                    style={{
                      fontSize: "10px",
                      fontWeight: "800",
                      color: isSelected ? "#444" : "#777",
                      marginBottom: "4px",
                      display: "flex",
                      justifyContent: "space-between",
                    }}
                  >
                    <span>PORT {s.port}</span>
                    <span>{s.tech.split(" ")[0]}</span>
                  </div>
                  <div style={{ fontSize: "12px", fontWeight: "800", whiteSpace: "nowrap" }}>
                    {s.name.replace(" Service", "")}
                  </div>
                  <div
                    style={{
                      fontSize: "10px",
                      color: isSelected ? "#222" : "#888",
                      marginTop: "3px",
                      whiteSpace: "nowrap",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                    }}
                  >
                    {s.role.split("&")[0]}
                  </div>
                </button>

                {idx < MICROSERVICES.length - 1 && (
                  <div
                    style={{
                      padding: "0 10px",
                      color: "#444",
                      fontSize: "14px",
                      fontWeight: "800",
                      userSelect: "none",
                    }}
                  >
                    →
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* ── Selected Service Detail View ────────────────────────────────────────── */}
      <div
        style={{
          padding: "24px",
          display: "grid",
          gridTemplateColumns: "1.2fr 1fr",
          gap: "24px",
        }}
      >
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: "10px", marginBottom: "8px" }}>
            <span
              style={{
                background: "#222",
                border: "1px solid #444",
                padding: "2px 8px",
                fontSize: "11px",
                fontWeight: "700",
                borderRadius: "4px",
                color: "#fff",
              }}
            >
              PORT {selectedService.port}
            </span>
            <span style={{ fontSize: "12px", color: "#888" }}>Stack: {selectedService.tech}</span>
          </div>

          <h4 style={{ fontSize: "22px", fontWeight: "900", margin: "0 0 12px 0", color: "#fff" }}>
            {selectedService.name}
          </h4>

          <p style={{ color: "#aaa", fontSize: "13px", lineHeight: 1.6, margin: "0 0 20px 0" }}>
            {selectedService.description}
          </p>

          <div
            style={{
              display: "grid",
              gridTemplateColumns: "1fr 1fr",
              gap: "12px",
              background: "#080808",
              border: "1px solid #202020",
              padding: "14px",
              borderRadius: "6px",
              marginBottom: "16px",
            }}
          >
            <div>
              <span style={{ fontSize: "10px", color: "#666", fontWeight: "700", textTransform: "uppercase", display: "block" }}>
                INCOMING CONTRACT
              </span>
              <span style={{ fontSize: "12px", color: "#ddd", fontWeight: "600" }}>
                {selectedService.inputs}
              </span>
            </div>
            <div>
              <span style={{ fontSize: "10px", color: "#666", fontWeight: "700", textTransform: "uppercase", display: "block" }}>
                OUTGOING CONTRACT
              </span>
              <span style={{ fontSize: "12px", color: "#ddd", fontWeight: "600" }}>
                {selectedService.outputs}
              </span>
            </div>
          </div>

          <div style={{ fontSize: "12px", color: "#777" }}>
            Docker Container: <code>{selectedService.docker.image}</code> • Ports:{" "}
            <code>{selectedService.docker.portMapping}</code>
          </div>
        </div>

        {/* Code / Payload Sample */}
        <div>
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              marginBottom: "8px",
            }}
          >
            <span style={{ fontSize: "11px", color: "#777", fontWeight: "700", letterSpacing: "0.05em" }}>
              PAYLOAD / CONFIG SPECIFICATION
            </span>
            <span style={{ fontSize: "10px", background: "#1a1a1a", padding: "2px 6px", borderRadius: "3px", color: "#888" }}>
              LIVE SPEC
            </span>
          </div>

          <pre
            style={{
              background: "#060606",
              border: "1px solid #222",
              padding: "16px",
              borderRadius: "6px",
              fontSize: "11px",
              fontFamily: "monospace",
              color: "#4ade80",
              overflowX: "auto",
              maxHeight: "220px",
              margin: 0,
              lineHeight: 1.5,
            }}
          >
            {selectedService.codeSample}
          </pre>
        </div>
      </div>
    </div>
  );
}
