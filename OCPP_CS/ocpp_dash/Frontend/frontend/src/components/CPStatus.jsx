import React, { useEffect, useState } from "react";
import api from "../api";

export default function CPStatus({ cpId="CP_9000", compact=false }) {
  const [st, setSt] = useState({ status: "Unknown", last_seen: null, online: false });

  const load = () =>
    api.get(`/cps/${encodeURIComponent(cpId)}/status/`)
      .then(r => setSt(r.data))
      .catch(() => setSt(s => ({ ...s, online: false })));

  useEffect(() => {
    load();
    const t = setInterval(load, 2000); // 2초마다 새로고침
    return () => clearInterval(t);
  }, [cpId]);

  const badgeStyle = {
    display:"inline-block", padding:"2px 8px", borderRadius:12,
    background: st.online ? "#e6ffed" : "#ffecec",
    color: st.online ? "#065f46" : "#991b1b", border: `1px solid ${st.online ? "#10b981" : "#f87171"}`
  };

  return (
    <div style={{display:"flex", alignItems:"center", gap:8}}>
      <span style={badgeStyle}>{st.online ? "online" : "offline"}</span>
      <span><b>{cpId}</b></span>
      {!compact && (
        <>
          <span>· 상태: <b>{st.status}</b></span>
          <span>· 최근: {st.last_seen ? new Date(st.last_seen).toLocaleTimeString() : "-"}</span>
        </>
      )}
    </div>
  );
}
