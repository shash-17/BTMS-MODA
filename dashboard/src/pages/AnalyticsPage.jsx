import { useEffect, useState, useCallback } from "react";
import { Link } from "react-router-dom";

const BASE = "/analytics-api";
const RANGES = [5, 15, 60];

const card = { background: "#0d0d0d", border: "1px solid #262626", borderRadius: 8, padding: 16 };
const title = { fontSize: 11, fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase", color: "#888", marginBottom: 12 };

async function get(path) {
  const r = await fetch(`${BASE}${path}`);
  if (!r.ok) throw new Error(path);
  return r.json();
}

function Kpi({ label, value, unit }) {
  return (
    <div style={card}>
      <div style={title}>{label}</div>
      <span style={{ fontSize: 28, fontWeight: 800, color: "#fff" }}>{value ?? "—"}</span>
      {unit && <span style={{ fontSize: 12, color: "#777", marginLeft: 4 }}>{unit}</span>}
    </div>
  );
}

function TrendChart({ data }) {
  if (!data.length) return <Empty />;
  const W = 640, H = 160, P = 6;
  const all = data.flatMap((d) => [d.max_temp, d.min_temp]);
  const lo = Math.min(...all) - 1, hi = Math.max(...all) + 1;
  const x = (i) => P + (i * (W - 2 * P)) / Math.max(1, data.length - 1);
  const y = (v) => H - P - ((v - lo) / (hi - lo)) * (H - 2 * P);
  const line = (k) => data.map((d, i) => `${i ? "L" : "M"}${x(i).toFixed(1)} ${y(d[k]).toFixed(1)}`).join(" ");
  const limitY = y(45);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", height: 160 }}>
      {limitY > 0 && limitY < H && (
        <line x1="0" x2={W} y1={limitY} y2={limitY} stroke="#f87171" strokeDasharray="4 4" strokeWidth="1" />
      )}
      <path d={line("max_temp")} fill="none" stroke="#fff" strokeWidth="1.8" />
      <path d={line("avg_temp")} fill="none" stroke="#999" strokeWidth="1.4" />
      <path d={line("min_temp")} fill="none" stroke="#555" strokeWidth="1.2" />
    </svg>
  );
}

function Histogram({ dist }) {
  if (!dist.counts?.length) return <Empty />;
  const max = Math.max(...dist.counts, 1);
  return (
    <div style={{ display: "flex", alignItems: "flex-end", gap: 3, height: 140 }}>
      {dist.counts.map((c, i) => {
        const hot = dist.bins[i] >= 45;
        return (
          <div key={i} title={`${dist.bins[i]}°C: ${c}`} style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "flex-end", height: "100%" }}>
            <div style={{ width: "100%", height: `${(c / max) * 100}%`, background: hot ? "#f87171" : "#d4d4d4", borderRadius: "2px 2px 0 0", transition: "height .4s" }} />
            <span style={{ fontSize: 8, color: "#666", marginTop: 3 }}>{Math.round(dist.bins[i])}</span>
          </div>
        );
      })}
    </div>
  );
}

function Heatmap({ corr }) {
  if (!corr.matrix?.length) return <Empty />;
  const short = { temperature: "Temp", voltage: "Volt", current: "Curr", soc: "SoC" };
  return (
    <div style={{ display: "grid", gridTemplateColumns: `60px repeat(${corr.columns.length}, 1fr)`, gap: 3, fontSize: 11 }}>
      <span />
      {corr.columns.map((c) => <span key={c} style={{ color: "#888", textAlign: "center" }}>{short[c]}</span>)}
      {corr.matrix.map((row, i) => [
        <span key={`l${i}`} style={{ color: "#888" }}>{short[corr.columns[i]]}</span>,
        ...row.map((v, j) => (
          <div key={`${i}-${j}`} style={{ background: `rgba(${v >= 0 ? "255,255,255" : "248,113,113"},${Math.min(1, Math.abs(v)) * 0.85 + 0.05})`, color: Math.abs(v) > 0.5 ? "#000" : "#ddd", textAlign: "center", padding: "8px 0", borderRadius: 3, fontWeight: 600 }}>
            {v.toFixed(2)}
          </div>
        )),
      ])}
    </div>
  );
}

function Empty() {
  return <div style={{ color: "#666", fontSize: 12, padding: "24px 0", textAlign: "center" }}>Waiting for Spark to write the first windows (≈30 s)…</div>;
}

const th = { textAlign: "left", color: "#777", fontWeight: 600, padding: "6px 8px", borderBottom: "1px solid #262626" };
const td = { padding: "6px 8px", borderBottom: "1px solid #1a1a1a", color: "#ddd" };

export default function AnalyticsPage() {
  const [minutes, setMinutes] = useState(15);
  const [data, setData] = useState({});
  const [online, setOnline] = useState(true);

  const load = useCallback(async () => {
    try {
      const q = `?minutes=${minutes}`;
      const [summary, trend, cells, corr, dist, anomalies, health] = await Promise.all([
        get(`/summary${q}`), get(`/pack-trend${q}`), get(`/cells${q}`), get(`/correlation${q}`),
        get(`/distribution${q}`), get("/anomalies?limit=10"), get("/health"),
      ]);
      setData({ summary, trend, cells, corr, dist, anomalies, health });
      setOnline(true);
    } catch {
      setOnline(false);
    }
  }, [minutes]);

  useEffect(() => {
    load();
    const id = setInterval(load, 5000);
    return () => clearInterval(id);
  }, [load]);

  const s = data.summary || {};
  const files = data.health?.lake_files || {};

  return (
    <div style={{ minHeight: "100vh", background: "#000", color: "#fff", padding: "20px 28px", fontFamily: "Inter, system-ui, sans-serif" }}>
      <header style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 20, flexWrap: "wrap", gap: 12 }}>
        <div>
          <h1 style={{ fontSize: 20, margin: 0 }}>Big Data Analytics</h1>
          <div style={{ fontSize: 12, color: "#777", marginTop: 4 }}>
            Kafka → Spark Structured Streaming → Parquet data lake
            <span style={{ marginLeft: 10, color: online ? "#4ade80" : "#f87171" }}>● {online ? "live" : "analytics API offline"}</span>
          </div>
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          {RANGES.map((m) => (
            <button key={m} onClick={() => setMinutes(m)} style={{ background: m === minutes ? "#fff" : "transparent", color: m === minutes ? "#000" : "#aaa", border: "1px solid #333", borderRadius: 4, padding: "4px 10px", fontSize: 12, fontWeight: 700, cursor: "pointer" }}>
              {m}m
            </button>
          ))}
          <Link to="/dashboard" style={{ color: "#aaa", fontSize: 12, textDecoration: "none", padding: "4px 8px", border: "1px solid #333", borderRadius: 4, fontWeight: 600 }}>← Dashboard</Link>
        </div>
      </header>

      <section style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(170px, 1fr))", gap: 12, marginBottom: 12 }}>
        <Kpi label="Readings analysed" value={s.readings?.toLocaleString()} />
        <Kpi label="Spike rate" value={s.spike_rate_pct} unit="%" />
        <Kpi label="Temp P95 / P99" value={s.ready ? `${s.temp_p95} / ${s.temp_p99}` : null} unit="°C" />
        <Kpi label="Mean ΔT" value={s.delta_t_mean} unit="°C" />
        <Kpi label="ΔT < 5°C compliance" value={s.uniformity_compliance_pct} unit="%" />
        <Kpi label="Hottest cell" value={s.hottest_cell !== undefined ? `#${s.hottest_cell}` : null} />
      </section>

      <section style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(380px, 1fr))", gap: 12, marginBottom: 12 }}>
        <div style={card}>
          <div style={title}>Pack temperature — 10 s windows (max / avg / min)</div>
          <TrendChart data={data.trend || []} />
        </div>
        <div style={card}>
          <div style={title}>Temperature distribution</div>
          <Histogram dist={data.dist || {}} />
        </div>
      </section>

      <section style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: 12, marginBottom: 12 }}>
        <div style={card}>
          <div style={title}>Cell thermal-risk ranking</div>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
            <thead>
              <tr>{["#", "Cell", "Mean °C", "P95 °C", "σ", "Spike %", "Risk"].map((h) => <th key={h} style={th}>{h}</th>)}</tr>
            </thead>
            <tbody>
              {(data.cells || []).map((c) => (
                <tr key={c.cell_id}>
                  <td style={td}>{c.rank}</td>
                  <td style={td}>#{c.cell_id}</td>
                  <td style={td}>{c.mean_temp}</td>
                  <td style={td}>{c.p95_temp}</td>
                  <td style={td}>{c.std_temp}</td>
                  <td style={td}>{c.spike_rate_pct}</td>
                  <td style={td}>
                    <div style={{ background: "#222", borderRadius: 3, height: 8, width: 80, display: "inline-block", verticalAlign: "middle" }}>
                      <div style={{ width: `${Math.min(100, c.risk_score)}%`, height: "100%", background: c.risk_score > 50 ? "#f87171" : "#d4d4d4", borderRadius: 3 }} />
                    </div>
                    <span style={{ marginLeft: 6 }}>{c.risk_score}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {!(data.cells || []).length && <Empty />}
        </div>
        <div style={card}>
          <div style={title}>Sensor correlation (Pearson)</div>
          <Heatmap corr={data.corr || {}} />
        </div>
      </section>

      <section style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: 12 }}>
        <div style={card}>
          <div style={title}>Recent anomalous windows</div>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
            <thead>
              <tr>{["Window start (UTC)", "Tmax", "ΔT", "Spiking cells"].map((h) => <th key={h} style={th}>{h}</th>)}</tr>
            </thead>
            <tbody>
              {(data.anomalies || []).map((a) => (
                <tr key={a.window_start}>
                  <td style={td}>{a.window_start}</td>
                  <td style={td}>{a.max_temp}</td>
                  <td style={td}>{a.delta_t}</td>
                  <td style={td}>{a.spiking_cells}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {!(data.anomalies || []).length && <Empty />}
        </div>
        <div style={card}>
          <div style={title}>Data lake</div>
          {[["raw (bronze)", files.raw], ["cell_metrics (silver)", files.cell_metrics], ["pack_metrics (gold)", files.pack_metrics]].map(([k, v]) => (
            <div key={k} style={{ display: "flex", justifyContent: "space-between", fontSize: 12, padding: "5px 0", borderBottom: "1px solid #1a1a1a" }}>
              <span style={{ color: "#aaa" }}>{k}</span>
              <span style={{ fontWeight: 700 }}>{v ?? 0} parquet files</span>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
