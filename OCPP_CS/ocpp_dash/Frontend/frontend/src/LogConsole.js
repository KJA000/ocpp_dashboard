import React, { useEffect, useRef, useState } from "react";

const API_BASE = process.env.REACT_APP_API_BASE; // e.g. http://localhost:8000/api
const STREAM_URL = `${API_BASE}/events/stream/`;

export default function LogConsole({ cpId, action, direction, autoScroll=true, maxLines=500 }) {
  const [lines, setLines] = useState([]);
  const [paused, setPaused] = useState(false);
  const [status, setStatus] = useState("disconnected");
  const lastIdRef = useRef(0);
  const viewRef = useRef(null);
  const esRef = useRef(null);

  useEffect(() => {
    const params = new URLSearchParams();
    if (lastIdRef.current) params.set("last_id", String(lastIdRef.current));
    if (cpId) params.set("cp_id", cpId);
    if (action) params.set("action", action);
    if (direction) params.set("direction", direction);

    const url = `${STREAM_URL}?${params.toString()}`;
    const es = new EventSource(url, { withCredentials: false });
    esRef.current = es;
    setStatus("connecting");

    es.addEventListener("open", () => setStatus("connected"));
    es.addEventListener("error", () => setStatus("error"));

    es.addEventListener("eventlog", (e) => {
      if (paused) return;
      try {
        const data = JSON.parse(e.data);
        lastIdRef.current = data.id;
        const line = `[${new Date(data.created_at).toLocaleTimeString()}] ${data.cp_id} ${data.direction} ${data.action} :: ${JSON.stringify(data.payload)}`;
        setLines(prev => {
          const next = [...prev, line];
          if (next.length > maxLines) next.splice(0, next.length - maxLines);
          return next;
        });
      } catch (err) {
        console.error("parse error", err);
      }
    });

    return () => {
      es.close();
      esRef.current = null;
      setStatus("disconnected");
    };
  }, [cpId, action, direction, paused]); // 필터 변경 시 재연결

  // 자동 스크롤
  useEffect(() => {
    if (!autoScroll || paused) return;
    const el = viewRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [lines, autoScroll, paused]);

  return (
    <div style={{display:"flex", flexDirection:"column", height: 700}}>
      <div style={{marginBottom:8, display:"flex", gap:8, alignItems:"center"}}>
        <strong>실시간 이벤트 로그</strong>
        <span style={{fontSize:12, color:"#666"}}>({status})</span>
        <button onClick={() => setPaused(p => !p)}>{paused ? "▶ 재생" : "⏸ 일시정지"}</button>
        <button onClick={() => setLines([])}>🧹 지우기</button>
      </div>
      <div
        ref={viewRef}
        style={{
          flex: 1,
          overflow: "auto",
          background: "#0d1117",
          color: "#d1d5db",
          fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace",
          fontSize: 13,
          lineHeight: 1.4,
          padding: 12,
          borderRadius: 8,
          border: "1px solid #30363d",
          whiteSpace: "pre-wrap",
        }}
      >
        {lines.length === 0 ? "대기 중..." : lines.join("\n")}
      </div>
    </div>
  );
}
