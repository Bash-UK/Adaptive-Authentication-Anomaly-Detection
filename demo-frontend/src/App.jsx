import React, { useEffect, useMemo, useState } from "react";

const defaults = {
  apiBase: "http://localhost:9091",
  userId: "u-1001",
  deviceId: "dev-home-01",
  previousCountry: "US",
  currentCountry: "DE",
  loginHour: 23,
  loginStatus: "Success",
  deviceChanged: "yes",
  ipAddress: "185.220.101.5",
  failedAttemptsLastHour: 6
};

const countryCoords = {
  US: [37.0902, -95.7129],
  CA: [56.1304, -106.3468],
  DE: [51.1657, 10.4515],
  IN: [20.5937, 78.9629],
  GB: [55.3781, -3.4360],
  FR: [46.2276, 2.2137],
  JP: [36.2048, 138.2529],
  BR: [-14.235, -51.9253],
  AU: [-25.2744, 133.7751]
};

function clamp01(value) {
  return Math.max(0, Math.min(1, value));
}

function toCountryCode(input) {
  return String(input || "").trim().toUpperCase().slice(0, 2);
}

function toRadians(degree) {
  return degree * (Math.PI / 180);
}

function haversineKm(lat1, lon1, lat2, lon2) {
  const earthKm = 6371;
  const dLat = toRadians(lat2 - lat1);
  const dLon = toRadians(lon2 - lon1);
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRadians(lat1)) * Math.cos(toRadians(lat2)) * Math.sin(dLon / 2) ** 2;
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  return earthKm * c;
}

function privateIp(ip) {
  const octets = ip.split(".").map((x) => Number(x));
  if (octets.length !== 4 || octets.some((x) => Number.isNaN(x) || x < 0 || x > 255)) {
    return false;
  }
  if (octets[0] === 10) return true;
  if (octets[0] === 172 && octets[1] >= 16 && octets[1] <= 31) return true;
  if (octets[0] === 192 && octets[1] === 168) return true;
  if (octets[0] === 127) return true;
  return false;
}

function derivePayload(raw) {
  const previousCode = toCountryCode(raw.previousCountry);
  const currentCode = toCountryCode(raw.currentCountry);

  const loginHourNormalized = clamp01(Number(raw.loginHour) / 23);
  const newDeviceFlag = raw.deviceChanged === "yes" ? 1 : 0;

  const countryChangeFlag = previousCode && currentCode && previousCode !== currentCode ? 1 : 0;

  let geoDistanceNormalized = countryChangeFlag;
  const c1 = countryCoords[previousCode];
  const c2 = countryCoords[currentCode];
  if (c1 && c2) {
    const km = haversineKm(c1[0], c1[1], c2[0], c2[1]);
    geoDistanceNormalized = clamp01(km / 20015);
  } else if (!countryChangeFlag) {
    geoDistanceNormalized = 0.0;
  } else {
    geoDistanceNormalized = 0.65;
  }

  const failedNorm = clamp01(Number(raw.failedAttemptsLastHour) / 6);
  const loginFailed = raw.loginStatus === "Fail" ? 1 : 0;
  const ip = String(raw.ipAddress || "").trim();
  const octets = ip.split(".").map((x) => Number(x));
  const validIpv4 = octets.length === 4 && octets.every((x) => Number.isInteger(x) && x >= 0 && x <= 255);

  let ipRiskScore = 0.2 + (0.45 * failedNorm) + (0.25 * loginFailed);
  if (!validIpv4) {
    ipRiskScore += 0.25;
  } else {
    const trailingOctetRisk = clamp01(octets[3] / 255);
    ipRiskScore += 0.2 * trailingOctetRisk;
    if (privateIp(ip)) {
      ipRiskScore -= 0.2;
    }
  }
  ipRiskScore = clamp01(ipRiskScore);

  return {
    userId: raw.userId,
    deviceId: raw.deviceId,
    countryCode: currentCode,
    loginStatus: raw.loginStatus,
    loginHour: Number(raw.loginHour),
    ipAddress: ip,
    loginHourNormalized,
    newDeviceFlag,
    countryChangeFlag,
    geoDistanceNormalized,
    ipRiskScore,
    failedAttemptsLastHour: Number(raw.failedAttemptsLastHour)
  };
}

function sparklinePoints(data, key, width, height, pad) {
  if (!data.length) return "";
  return data
    .map((p, i) => {
      const x = pad + (i * (width - pad * 2)) / Math.max(1, data.length - 1);
      const y = pad + (1 - clamp01(Number(p[key] ?? 0))) * (height - pad * 2);
      return `${x},${y}`;
    })
    .join(" ");
}

function withMovingAverage(data, key, outKey, windowSize = 5) {
  const safeWindow = Math.max(2, windowSize);
  return data.map((point, idx) => {
    const start = Math.max(0, idx - safeWindow + 1);
    const slice = data.slice(start, idx + 1);
    const avg = slice.reduce((sum, item) => sum + Number(item[key] || 0), 0) / Math.max(1, slice.length);
    return { ...point, [outKey]: avg };
  });
}

function chartPointAt(index, value, count, width, height, pad) {
  const x = pad + (index * (width - pad * 2)) / Math.max(1, count - 1);
  const y = pad + (1 - clamp01(Number(value ?? 0))) * (height - pad * 2);
  return { x, y };
}

function buildAreaPath(data, key, width, height, pad) {
  if (!data.length) return "";
  const first = chartPointAt(0, data[0][key], data.length, width, height, pad);
  const last = chartPointAt(data.length - 1, data[data.length - 1][key], data.length, width, height, pad);
  const line = data
    .map((point, i) => {
      const xy = chartPointAt(i, point[key], data.length, width, height, pad);
      return `${xy.x},${xy.y}`;
    })
    .join(" L ");
  return `M ${pad},${height - pad} L ${first.x},${first.y} L ${line} L ${last.x},${height - pad} Z`;
}

function formatTs(value) {
  try {
    return new Date(value).toLocaleTimeString();
  } catch {
    return value;
  }
}

export default function App() {
  const [form, setForm] = useState(defaults);
  const [loading, setLoading] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [response, setResponse] = useState(null);
  const [history, setHistory] = useState([]);
  const [error, setError] = useState("");
  const [historyError, setHistoryError] = useState("");
  const [hoveredIndex, setHoveredIndex] = useState(-1);
  const [knownUsers, setKnownUsers] = useState([]);
  const [usersLoading, setUsersLoading] = useState(false);
  const [usersError, setUsersError] = useState("");

  const payloadPreview = useMemo(() => derivePayload(form), [form]);
  const maxRisk = useMemo(() => history.reduce((m, x) => Math.max(m, Number(x.risk || 0)), 0), [history]);
  const averageRisk = useMemo(() => {
    if (!history.length) return 0;
    const total = history.reduce((sum, item) => sum + Number(item.risk || 0), 0);
    return total / history.length;
  }, [history]);
  const overThresholdCount = useMemo(
    () => history.filter((item) => Number(item.risk || 0) >= 0.75).length,
    [history]
  );
  const historyWithAverage = useMemo(
    () => withMovingAverage(history, "risk", "riskAvg", 5),
    [history]
  );
  const trendLabel = useMemo(() => {
    if (history.length < 2) return "insufficient data";
    const last = Number(history[history.length - 1]?.risk || 0);
    const prev = Number(history[history.length - 2]?.risk || 0);
    if (last > prev + 0.02) return "rising";
    if (last < prev - 0.02) return "falling";
    return "stable";
  }, [history]);

  const actionClass = useMemo(() => {
    const action = response?.action || "";
    if (action === "ALLOW") return "allow";
    if (action === "MFA_CHALLENGE") return "mfa";
    if (action === "BLOCK") return "block";
    return "";
  }, [response]);

  const onChange = (key, value) => {
    setForm((prev) => ({ ...prev, [key]: value }));
  };

  const loadUsers = async () => {
    setUsersLoading(true);
    setUsersError("");
    try {
      const url = `${form.apiBase.replace(/\/+$/, "")}/enterprise/users?limit=300`;
      const res = await fetch(url);
      const body = await res.json();
      if (!res.ok) {
        throw new Error(body.message || `Users request failed (${res.status})`);
      }
      setKnownUsers(Array.isArray(body.users) ? body.users : []);
    } catch (err) {
      setUsersError(String(err?.message || err));
    } finally {
      setUsersLoading(false);
    }
  };

  useEffect(() => {
    loadUsers();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [form.apiBase]);

  const loadHistory = async (forcedUserId) => {
    setHistoryLoading(true);
    setHistoryError("");
    try {
      const effectiveUserId = String(forcedUserId ?? form.userId ?? "").trim();
      if (!effectiveUserId) {
        throw new Error("User ID is required to load graph history.");
      }
      const url = `${form.apiBase.replace(/\/+$/, "")}/enterprise/user/${encodeURIComponent(effectiveUserId)}/history?limit=70`;
      const res = await fetch(url);
      const body = await res.json();
      if (!res.ok) {
        throw new Error(body.message || `History request failed (${res.status})`);
      }
      setHistory(Array.isArray(body.points) ? body.points : []);
      setHoveredIndex(-1);
    } catch (err) {
      setHistoryError(String(err?.message || err));
    } finally {
      setHistoryLoading(false);
    }
  };

  const submit = async (event) => {
    event.preventDefault();
    setLoading(true);
    setError("");
    setResponse(null);

    try {
      const res = await fetch(`${form.apiBase.replace(/\/+$/, "")}/enterprise/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payloadPreview)
      });

      const body = await res.json();
      if (!res.ok) {
        const details = Array.isArray(body.errors) ? `\n${body.errors.join("\n")}` : "";
        throw new Error(`${body.message || "Request failed."}${details}`);
      }
      setResponse(body);
      if (form.userId && !knownUsers.includes(form.userId)) {
        setKnownUsers((prev) => [form.userId, ...prev.filter((x) => x !== form.userId)]);
      }
      await loadHistory();
    } catch (err) {
      setError(String(err?.message || err));
    } finally {
      setLoading(false);
    }
  };

  const width = 680;
  const height = 240;
  const pad = 22;
  const riskLine = sparklinePoints(history, "risk", width, height, pad);
  const confidenceLine = sparklinePoints(history, "confidence", width, height, pad);
  const movingAvgLine = sparklinePoints(historyWithAverage, "riskAvg", width, height, pad);
  const riskArea = buildAreaPath(history, "risk", width, height, pad);
  const activeIndex = hoveredIndex >= 0 ? hoveredIndex : Math.max(0, history.length - 1);
  const activePoint = history[activeIndex];
  const activeXY = activePoint ? chartPointAt(activeIndex, activePoint.risk, history.length, width, height, pad) : null;
  const yTicks = [1, 0.75, 0.5, 0.25, 0];

  return (
    <main className="page">
      <header className="hero">
        <h1>Behavioral Anomaly Workbench</h1>
        <p>Live adaptive-auth simulation with per-user anomaly trend tracking from PostgreSQL-backed history.</p>
      </header>

      <section className="panel input-panel">
        <div className="panel-head">
          <h2>Simulation Console</h2>
          <button type="button" onClick={() => loadHistory()} disabled={historyLoading}>
            {historyLoading ? "Refreshing..." : "Refresh User Graph"}
          </button>
        </div>

        <form className="grid" onSubmit={submit}>
          <Field label="Backend URL">
            <input value={form.apiBase} onChange={(e) => onChange("apiBase", e.target.value)} />
          </Field>
          <Field label="User ID">
            <input
              value={form.userId}
              placeholder="Enter user ID"
              onChange={(e) => onChange("userId", e.target.value)}
            />
          </Field>
          <Field label="Device ID">
            <input value={form.deviceId} onChange={(e) => onChange("deviceId", e.target.value)} />
          </Field>
          <Field label="Login Status">
            <select value={form.loginStatus} onChange={(e) => onChange("loginStatus", e.target.value)}>
              <option value="Success">Success</option>
              <option value="Fail">Fail</option>
            </select>
          </Field>
          <Field label="Current Login Hour (0-23)">
            <input type="number" min="0" max="23" step="1" value={form.loginHour} onChange={(e) => onChange("loginHour", e.target.value)} />
          </Field>
          <Field label="Failed Attempts (Last Hour)">
            <input type="number" min="0" step="1" value={form.failedAttemptsLastHour} onChange={(e) => onChange("failedAttemptsLastHour", e.target.value)} />
          </Field>
          <Field label="Previous Country (2-letter)">
            <input value={form.previousCountry} onChange={(e) => onChange("previousCountry", e.target.value)} />
          </Field>
          <Field label="Current Country (2-letter)">
            <input value={form.currentCountry} onChange={(e) => onChange("currentCountry", e.target.value)} />
          </Field>
          <Field label="Device Changed?">
            <select value={form.deviceChanged} onChange={(e) => onChange("deviceChanged", e.target.value)}>
              <option value="yes">Yes</option>
              <option value="no">No</option>
            </select>
          </Field>
          <Field label="IP Address">
            <input value={form.ipAddress} onChange={(e) => onChange("ipAddress", e.target.value)} />
          </Field>

          <button type="submit" disabled={loading}>
            {loading ? "Evaluating..." : "Run Risk Evaluation"}
          </button>
        </form>
      </section>

      <section className="panel output-panel">
        <h2>Decision Panel</h2>
        {!response && !error && <p className="hint">Run an event to get an adaptive decision.</p>}
        {error && <pre className="error">{error}</pre>}
        {response && (
          <div className="result">
            <div className={`action ${actionClass}`}>Action: {response.action}</div>
            <div>finalRisk: <strong>{Number(response.finalRisk || 0).toFixed(4)}</strong></div>
            <div>modelRisk: <strong>{Number(response.modelRisk || 0).toFixed(4)}</strong></div>
            <div>confidence: <strong>{Number(response.confidence || 0).toFixed(4)}</strong></div>
            <div>message: {response.message}</div>
            <div className="reasons">
              {(response.reasons || []).map((reason) => (
                <span key={reason} className="chip">{reason}</span>
              ))}
            </div>
          </div>
        )}

        <p className="muted">Derived payload sent to backend</p>
        <pre className="payload-preview">{JSON.stringify(payloadPreview, null, 2)}</pre>
      </section>

      <section className="panel chart-panel">
        <div className="panel-head">
          <h2>User Risk Timeline</h2>
          <p>Tracked user: <strong>{form.userId}</strong></p>
        </div>
        <div className="chart-toolbar">
          <div className="chart-user-select">
            <label htmlFor="graph-user-select">Graph User</label>
            <select
              id="graph-user-select"
              value={knownUsers.includes(form.userId) ? form.userId : ""}
              onChange={(e) => {
                const selected = e.target.value;
                if (!selected) return;
                onChange("userId", selected);
                loadHistory(selected);
              }}
            >
              <option value="">{usersLoading ? "Loading users..." : "Select tracked user"}</option>
              {knownUsers.map((userId) => (
                <option key={userId} value={userId}>{userId}</option>
              ))}
            </select>
          </div>
          <button type="button" className="secondary-btn" onClick={loadUsers} disabled={usersLoading}>
            {usersLoading ? "Refreshing users..." : "Refresh Users"}
          </button>
        </div>
        {usersError && <pre className="error">{usersError}</pre>}
        {historyError && <pre className="error">{historyError}</pre>}
        {!history.length && !historyError && <p className="hint">No history yet. Submit events for this user.</p>}
        {!!history.length && (
          <>
            <div className="chart-metrics">
              <div className="metric-card">
                <span>Latest risk</span>
                <strong>{Number(history[history.length - 1]?.risk || 0).toFixed(3)}</strong>
              </div>
              <div className="metric-card">
                <span>Average risk</span>
                <strong>{averageRisk.toFixed(3)}</strong>
              </div>
              <div className="metric-card">
                <span>Above threshold</span>
                <strong>{overThresholdCount}</strong>
              </div>
              <div className="metric-card">
                <span>Trend</span>
                <strong className={`trend ${trendLabel}`}>{trendLabel}</strong>
              </div>
            </div>
            <div className="chart-legend">
              <span><i className="dot risk" /> risk</span>
              <span><i className="dot avg" /> moving average</span>
              <span><i className="dot confidence" /> confidence</span>
              <span><i className="dot threshold" /> policy threshold (0.75)</span>
              <span><i className="dot anomaly" /> anomalies</span>
              <span>max risk in view: <strong>{maxRisk.toFixed(3)}</strong></span>
            </div>
            <svg className="chart" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" onMouseLeave={() => setHoveredIndex(-1)}>
              <rect x="0" y="0" width={width} height={height} rx="12" className="chart-bg" />
              <rect x={pad} y={pad} width={width - pad * 2} height={(height - pad * 2) * 0.25} className="zone-high" />
              <rect x={pad} y={pad + (height - pad * 2) * 0.25} width={width - pad * 2} height={(height - pad * 2) * 0.25} className="zone-mid" />
              <rect x={pad} y={pad + (height - pad * 2) * 0.5} width={width - pad * 2} height={(height - pad * 2) * 0.5} className="zone-low" />
              {yTicks.map((tick) => {
                const y = pad + (1 - tick) * (height - pad * 2);
                return (
                  <g key={`tick-${tick}`}>
                    <line x1={pad} y1={y} x2={width - pad} y2={y} className="grid-line" />
                    <text x={pad - 6} y={y + 3} className="tick-label">{tick.toFixed(2)}</text>
                  </g>
                );
              })}
              <line x1={pad} y1={height - pad} x2={width - pad} y2={height - pad} className="axis" />
              <line x1={pad} y1={pad} x2={pad} y2={height - pad} className="axis" />
              <line x1={pad} y1={pad + (1 - 0.75) * (height - pad * 2)} x2={width - pad} y2={pad + (1 - 0.75) * (height - pad * 2)} className="threshold-line" />
              <path d={riskArea} className="risk-area" />
              <polyline points={confidenceLine} className="confidence-line" />
              <polyline points={movingAvgLine} className="avg-line" />
              <polyline points={riskLine} className="risk-line" />
              {history.map((item, idx) => {
                const xy = chartPointAt(idx, item.risk, history.length, width, height, pad);
                const active = idx === activeIndex;
                const anomaly = Number(item.risk || 0) >= 0.75;
                return (
                  <g key={`${item.timestamp}-${idx}`}>
                    {anomaly && <circle cx={xy.x} cy={xy.y} r={6.5} className="anomaly-point" />}
                    <circle
                      cx={xy.x}
                      cy={xy.y}
                      r={active ? 4.4 : 3.2}
                      className={`risk-point ${active ? "active" : ""}`}
                      onMouseEnter={() => setHoveredIndex(idx)}
                    />
                  </g>
                );
              })}
              {activeXY && (
                <line x1={activeXY.x} y1={pad} x2={activeXY.x} y2={height - pad} className="focus-line" />
              )}
            </svg>
            <div className="chart-footer">
              <span>{formatTs(history[0]?.timestamp)}</span>
              <span>{formatTs(history[Math.floor(history.length / 2)]?.timestamp)}</span>
              <span>{formatTs(history[history.length - 1]?.timestamp)}</span>
            </div>
            {activePoint && (
              <div className="hover-card">
                <div><span>Time</span><strong>{formatTs(activePoint.timestamp)}</strong></div>
                <div><span>Risk</span><strong>{Number(activePoint.risk || 0).toFixed(3)}</strong></div>
                <div><span>Confidence</span><strong>{Number(activePoint.confidence || 0).toFixed(3)}</strong></div>
              </div>
            )}
            <div className="history-table">
              {history.slice(-8).reverse().map((x, idx) => (
                <div key={`${x.timestamp}-${idx}`} className="history-row">
                  <span>{formatTs(x.timestamp)}</span>
                  <span>risk {Number(x.risk).toFixed(3)}</span>
                  <span>conf {Number(x.confidence).toFixed(3)}</span>
                </div>
              ))}
            </div>
          </>
        )}
      </section>
    </main>
  );
}

function Field({ label, children }) {
  return (
    <label className="field">
      <span>{label}</span>
      {children}
    </label>
  );
}
