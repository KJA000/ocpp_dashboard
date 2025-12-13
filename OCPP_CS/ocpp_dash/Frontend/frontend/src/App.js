import React, { useEffect, useState } from "react";
import "./App.css";
import api from "./api";
import LogConsole from "./LogConsole";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid
} from "recharts";
import FuzzConsole from "./FuzzConsole";

/* ------------------------- 제어 패널 ------------------------- */
function ControlPanel() {
  const [scenario, setScenario] = useState("format_error");

  return (
    <div className="controls">
      <strong>Start/Stop Fuzzing</strong>
      <div className="row">
        <label>
          Scenario&nbsp;
          <select
            value={scenario}
            onChange={(e) => setScenario(e.target.value)}
          >
            <option value="format_error">형식 오류</option>
            <option value="logic_error">논리 오류</option>
            <option value="order_disrupt">순서 교란</option>
            <option value="timing_mutate">타이밍 변조</option>
          </select>
        </label>

        <button
          onClick={async () => {
            try {
              await api.post("/fuzz/", { scenario, status: "idle" });
              alert(`Fuzz Job 생성 완료 (scenario=${scenario})`);
            } catch (err) {
              console.error(err);
              alert("Fuzz Job 생성 실패");
            }
          }}
        >
          생성하기
        </button>
      </div>
    </div>
  );
}

/* ------------------------- Job 상태 패널 (여러 Job 표시 지원) ------------------------- */
function JobStatus({ cpId = "CP_9000" }) {
  const [cpStatus, setCpStatus] = useState({
    status: "Unknown",
    last_seen: null,
    online: false
  });
  const [jobs, setJobs] = useState([]);

  /* ========= CP 상태 업데이트 ========= */
  useEffect(() => {
    const API_BASE = process.env.REACT_APP_API_BASE;
    const params = new URLSearchParams();
    params.set("cp_id", cpId);
    params.set("action", "StatusNotification");

    const es = new EventSource(`${API_BASE}/events/stream/?${params.toString()}`);

    es.addEventListener("eventlog", (e) => {
      try {
        const data = JSON.parse(e.data);
        if (data?.action === "StatusNotification" && data?.cp_id === cpId) {
          const st = data?.payload?.status || "Unknown";
          setCpStatus({
            status: st,
            last_seen: new Date().toISOString(),
            online: true
          });
        }
      } catch {}
    });

    return () => es.close();
  }, [cpId]);

  const fetchCpStatus = () =>
    api
      .get(`/cps/${cpId}/status/`)
      .then((r) => setCpStatus(r.data))
      .catch(() => setCpStatus((s) => ({ ...s, online: false })));

  useEffect(() => {
    fetchCpStatus();
    const t = setInterval(fetchCpStatus, 5000);
    return () => clearInterval(t);
  }, [cpId]);

  /* ========= Fuzz Job 리스트 여러 개 가져오기 ========= */
  const loadJobs = () =>
    api
      .get("/fuzz/?page_size=50")
      .then((r) => {
        const list = r.data.results || r.data || [];
        setJobs(list);
      })
      .catch(console.error);

  useEffect(() => {
    loadJobs();
    const t = setInterval(loadJobs, 2000);
    return () => clearInterval(t);
  }, []);

  const badgeStyle = {
    display: "inline-block",
    padding: "2px 8px",
    borderRadius: 12,
    background: cpStatus.online ? "#e6ffed" : "#ffecec",
    color: cpStatus.online ? "#065f46" : "#991b1b",
    border: `1px solid ${cpStatus.online ? "#10b981" : "#f87171"}`
  };

  return (
    <div className="scroll">
      <table className="table">
        <thead>
          <tr>
            <th colSpan={5} style={{ background: "#fafafa", textAlign: "left" }}>
              <div className="cp-inline">
                <span><b>CP:</b> {cpId}</span>
                <span><b>상태:</b> {cpStatus.status}</span>
                <span>
                  <b>최근:</b>{" "}
                  {cpStatus.last_seen
                    ? new Date(cpStatus.last_seen).toLocaleTimeString()
                    : "-"}
                </span>
                <span>
                  <b>연결:</b> <span style={badgeStyle}>{cpStatus.online ? "online" : "offline"}</span>
                </span>
              </div>
            </th>
          </tr>

          <tr>
            <th>ID</th>
            <th>Scenario</th>
            <th>Status</th>
            <th>시작</th>
            <th>종료</th>
          </tr>
        </thead>

        <tbody>
          {jobs.length === 0 ? (
            <tr>
              <td colSpan={5} style={{ textAlign: "center", color: "#666" }}>
                Job 없음
              </td>
            </tr>
          ) : (
            jobs.map((j) => (
              <tr
                key={j.id}
                style={{
                  background: j.status === "running" ? "#e0f2fe" : "transparent"
                }}
              >
                <td>{j.id}</td>
                <td>{j.scenario}</td>
                <td>{j.status}</td>
                <td>{j.started_at || "-"}</td>
                <td>{j.ended_at || "-"}</td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}

/* ------------------------- MeterValues 패널 ------------------------- */
function MeterPanel({ cpId = "CP_9000" }) {
  const [rows, setRows] = useState([]);

  const normalize = (r) => {
    const out = { ...r };
    const svs =
      r.raw?.meter_value?.sampledValue ||
      r.raw?.sampledValue ||
      r.sampledValue ||
      [];

    const pickNum = (pred) => {
      const it = svs.find(pred);
      if (!it) return null;
      const v = typeof it.value === "string" ? parseFloat(it.value) : it.value;
      return Number.isFinite(v) ? v : null;
    };

    out.power_W = out.power_W ?? pickNum((s) => /Power/i.test(s.measurand));
    out.voltage_V = out.voltage_V ?? pickNum((s) => /Voltage/i.test(s.measurand));
    out.current_A = out.current_A ?? pickNum((s) => /Current/i.test(s.measurand));
    out.energy_Wh = out.energy_Wh ?? pickNum((s) => /Energy/i.test(s.measurand));
    out.soc_percent = out.soc_percent ?? pickNum((s) => /SoC/i.test(s.measurand));
    out.ts_label = new Date(out.ts).toLocaleTimeString();

    return out;
  };

  const load = () =>
    api
      .get(`/mv/?search=${encodeURIComponent(cpId)}&page_size=200`)
      .then((r) => {
        const list = (r.data.results || r.data || []).map(normalize);
        setRows(list.slice().reverse());
      })
      .catch(console.error);

  useEffect(() => {
    load();
    const t = setInterval(load, 2000);
    return () => clearInterval(t);
  }, [cpId]);

  return (
    <div className="scroll">
      <LineChart width={900} height={280} data={rows}>
        <CartesianGrid strokeDasharray="4 4" />
        <XAxis dataKey="ts_label" />
        <YAxis />
        <Tooltip />
        <Line type="monotone" dataKey="power_W" dot={false} />
        <Line type="monotone" dataKey="voltage_V" dot={false} />
        <Line type="monotone" dataKey="current_A" dot={false} />
      </LineChart>

      <div className="table-wrap" style={{ marginTop: 10 }}>
        <table className="table">
          <thead>
            <tr>
              <th>Time</th>
              <th>Power(W)</th>
              <th>Energy(Wh)</th>
              <th>Current(A)</th>
              <th>Voltage(V)</th>
              <th>SoC(%)</th>
            </tr>
          </thead>

          <tbody>
            {rows.slice(-15).map((r) => (
              <tr key={r.id}>
                <td>{new Date(r.ts).toLocaleString()}</td>
                <td>{r.power_W ?? "-"}</td>
                <td>{r.energy_Wh ?? "-"}</td>
                <td>{r.current_A ?? "-"}</td>
                <td>{r.voltage_V ?? "-"}</td>
                <td>{r.soc_percent ?? "-"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/* ------------------------- 세션 테이블 ------------------------- */
function SessionTable() {
  const [rows, setRows] = useState([]);

  const load = () =>
    api
      .get("/tx/?page_size=50")
      .then((r) => setRows(r.data.results || r.data))
      .catch(console.error);

  useEffect(() => {
    load();
    const t = setInterval(load, 3000);
    return () => clearInterval(t);
  }, []);

  return (
    <div className="scroll">
      <table className="table">
        <thead>
          <tr>
            <th>TxID</th>
            <th>CP</th>
            <th>Conn</th>
            <th>Start</th>
            <th>Stop</th>
            <th>Energy(Wh)</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((s) => (
            <tr key={s.id}>
              <td>{s.transaction_id}</td>
              <td>{s.cp_id}</td>
              <td>{s.connector_id}</td>
              <td>{s.started_at ? new Date(s.started_at).toLocaleString() : "-"}</td>
              <td>{s.stopped_at ? new Date(s.stopped_at).toLocaleString() : "-"}</td>
              <td>{s.energy_Wh ?? "-"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ------------------------- 퍼징 패널 ------------------------- */
function FuzzPanel() {
  const [jobs, setJobs] = useState([]);

  const load = () =>
    api
      .get("/fuzz/?page_size=20")
      .then((r) => setJobs(r.data.results || r.data))
      .catch(console.error);

  useEffect(() => {
    load();
    const t = setInterval(load, 2000);
    return () => clearInterval(t);
  }, []);

  const start = (id) => api.post(`/fuzz/${id}/start/`).then(load);
  const stop = (id) => api.post(`/fuzz/${id}/stop/`).then(load);

  return (
    <div className="scroll">
      <table className="table">
        <thead>
          <tr>
            <th>ID</th><th>Scenario</th><th>Status</th><th>시작</th><th>종료</th><th>제어</th>
          </tr>
        </thead>
        <tbody>
          {jobs.map((j) => (
            <tr key={j.id}>
              <td>{j.id}</td>
              <td>{j.scenario}</td>
              <td>{j.status}</td>
              <td>{j.started_at || "-"}</td>
              <td>{j.ended_at || "-"}</td>
              <td>
                <button onClick={() => start(j.id)}>Start</button>
                <button onClick={() => stop(j.id)}>Stop</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ------------------------- 전체 페이지 레이아웃 ------------------------- */
export default function App() {
  const defaultCpId = "CP_9000";

  return (
    <div className="page">
      <header className="header">
        <h1>Dashboard for Verifying SECC–CSMS Communication based on OCPP 1.6</h1>
      </header>

      {/* ⭐ 3-열 레이아웃 적용 */}
      <div className="columns">

        {/* ========== 왼쪽 세로 스택 ========== */}
        <div className="left-col">
          <section className="card"><h2>제어 패널</h2><ControlPanel /></section>
          <section className="card"><h2>퍼징 패널</h2><FuzzPanel /></section>
          <section className="card"><h2>Job 상태</h2><JobStatus cpId={defaultCpId} /></section>
        </div>

        {/* ========== 중앙 세로 스택 ========== */}
        <div className="center-col">
          <section className="card"><h2>MeterValues</h2><MeterPanel cpId={defaultCpId} /></section>
          <section className="card"><h2>세션 테이블</h2><SessionTable /></section>
        </div>

        {/* ========== 오른쪽 전체 세로 ========== */}
        <div className="right-col">
          <section className="card"><h2>이벤트 로그</h2><LogConsole cpId={defaultCpId} /></section>
        </div>

      </div>

      {/* ====================== 하단 전체폭 로그 ====================== */}
      <section className="card fuzzlogs">
        <h2>Fuzzing 실시간 로그</h2>
        <FuzzConsole />
      </section>

    </div>
  );
}
