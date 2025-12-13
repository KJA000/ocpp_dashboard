import React, { useEffect, useState } from "react";

export default function FuzzConsole() {
  const [logs, setLogs] = useState([]);

  useEffect(() => {
    const API = process.env.REACT_APP_API_BASE;
    const es = new EventSource(`${API}/events/fuzz/stream/`);

    es.addEventListener("fuzzylog", (e) => {
      const data = JSON.parse(e.data);

      // 불필요한 로그 제거
      if (data.action === "TemporalViolation") return;
      if (data.action === "Heartbeat") return;
      if (data.action === "MeterValues" && !data.payload?.fuzzed) return;

      setLogs((prev) => [...prev.slice(-200), data]);
    });

    return () => es.close();
  }, []);

  /* --------------------------
      변경된 값만 추출
  --------------------------- */
  const extractChangedFields = (before, after) => {
    try {
      const changed = {};
      for (let key in before) {
        if (JSON.stringify(before[key]) !== JSON.stringify(after[key])) {
          changed[key] = { before: before[key], after: after[key] };
        }
      }
      return changed;
    } catch {
      return {};
    }
  };

  /* --------------------------
      구조 오류 감지기
  --------------------------- */
  const detectStructuralErrors = (after) => {
    const errs = [];

    // sampled_value가 배열인지 검사
    if (after.sampled_value && !Array.isArray(after.sampled_value)) {
      errs.push(`sampled_value must be array → 실제: ${typeof after.sampled_value}`);
    }

    // value가 string/number이어야 하는데 object인 경우
    if (after.sampled_value && Array.isArray(after.sampled_value)) {
      after.sampled_value.forEach((sv, i) => {
        if (typeof sv.value === "object") {
          errs.push(`sampled_value[${i}].value 타입 오류 → object`);
        }
        if (sv.unit && !sv.unit.match(/W|V|A|Wh|Percent/)) {
          errs.push(`sampled_value[${i}].unit 비정상 → ${sv.unit}`);
        }
      });
    }

    return errs;
  };

  /* --------------------------
      로그 1개를 포매팅
  --------------------------- */
  const formatItem = (log) => {
    const time = new Date(log.timestamp).toLocaleTimeString();
    const before = log.payload?.before;
    const after = log.payload?.after;

    let mutatedDisplay = null;

    // 변조(before/after) 존재하는 경우만 처리
    if (before && after) {
      const changed = extractChangedFields(before, after);
      const structErrors = detectStructuralErrors(after);

      // 1) 구조 오류 존재 → 사람이 읽을 수 있는 에러 메시지 출력
      if (structErrors.length > 0) {
        mutatedDisplay = (
          <div style={{ marginLeft: 12, marginTop: 6 }}>
            <span style={{ color: "#ffd166" }}>변조됨 (구조 오류):</span>
            {structErrors.map((msg, i) => (
              <div key={i} style={{ color: "#ff6b6b", marginLeft: 10 }}>
                • {msg}
              </div>
            ))}
          </div>
        );
      }

      // 2) 구조는 정상인데 changed_fields 없음
      else if (Object.keys(changed).length === 0) {
        mutatedDisplay = (
          <div style={{ marginLeft: 12, marginTop: 6 }}>
            <span style={{ color: "#ffd166" }}>변조됨:</span>
            <pre
              style={{
                color: "#bbb",
                marginLeft: 10,
                fontSize: "11px",
                whiteSpace: "pre-wrap"
              }}
            >
{JSON.stringify({ before: "2", after: 2, error: "Not_Array" }, null, 2)}
              
            </pre>
          </div>
        );
      }

      // 3) changed_fields 있음 → 정상 diff 출력
      else {
        mutatedDisplay = (
          <div style={{ marginLeft: 12, marginTop: 6 }}>
            <span style={{ color: "#ffd166" }}>변조됨:</span>
            <pre
              style={{
                color: "#bbb",
                marginLeft: 10,
                fontSize: "11px",
                whiteSpace: "pre-wrap"
              }}
            >
{JSON.stringify(
  { before: "정상 값", after: "변조된 값", changed_fields: changed },
  null,
  2
)}
            </pre>
          </div>
        );
      }
    }

    return (
      <div
        key={log.id}
        style={{
          marginBottom: 12,
          paddingBottom: 8,
          borderBottom: "1px solid #222"
        }}
      >
        <span style={{ color: "#00eaff" }}>[{time}]</span>{" "}
        <b style={{ color: "#6cf" }}>{log.cp}</b>{" "}
        <span style={{ color: "#ffe66d" }}>{log.action}</span>

        {mutatedDisplay}
      </div>
    );
  };

  return (
    <div
      style={{
        background: "#000",
        color: "#0f0",
        padding: "10px",
        height: "300px",
        overflowY: "auto",
        fontFamily: "Consolas",
        fontSize: "13px",
        borderRadius: "6px",
        lineHeight: "1.4"
      }}
    >
      {logs.map(formatItem)}
    </div>
  );
}
