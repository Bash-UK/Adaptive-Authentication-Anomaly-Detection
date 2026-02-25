import React, { useEffect, useMemo, useState } from "react";
import { MapContainer, Marker, TileLayer, useMapEvents } from "react-leaflet";
import L from "leaflet";

const defaults = {
  apiBase: "http://localhost:9091",
  userId: "u-1001",
  deviceId: "dev-home-01",
  countryCode: "DE",
  loginHour: 23,
  loginStatus: "Success",
  deviceChanged: "yes",
  ipAddress: "185.220.101.5",
  failedAttemptsLastHour: 6
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

function derivePayload(raw, previousPoint, currentPoint, previousCountryCode, currentCountryCode) {
  const currentCode = toCountryCode(currentCountryCode || raw.countryCode) || "US";
  const previousCode = toCountryCode(previousCountryCode);
  const loginHourNormalized = clamp01(Number(raw.loginHour) / 23);
  const newDeviceFlag = raw.deviceChanged === "yes" ? 1 : 0;
  const km = haversineKm(previousPoint.lat, previousPoint.lon, currentPoint.lat, currentPoint.lon);
  const countryChangeFlag = previousCode && currentCode ? (previousCode === currentCode ? 0 : 1) : 0;
  const geoDistanceNormalized = clamp01(km / 20015);

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
  const [activePage, setActivePage] = useState("dashboard");
  const [form, setForm] = useState(defaults);
  const [previousPoint, setPreviousPoint] = useState({ lat: 37.09, lon: -95.71 });
  const [currentPoint, setCurrentPoint] = useState({ lat: 51.16, lon: 10.45 });
  const [mapTarget, setMapTarget] = useState("current");
  const [loading, setLoading] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [response, setResponse] = useState(null);
  const [history, setHistory] = useState([]);
  const [error, setError] = useState("");
  const [historyError, setHistoryError] = useState("");
  const [hoveredIndex, setHoveredIndex] = useState(-1);
  const [knownUsers, setKnownUsers] = useState([]);
  const [graphUserQuery, setGraphUserQuery] = useState(defaults.userId);
  const [userSearchFocused, setUserSearchFocused] = useState(false);
  const [usersLoading, setUsersLoading] = useState(false);
  const [usersError, setUsersError] = useState("");
  const [geoLookupState, setGeoLookupState] = useState({
    loadingPrevious: false,
    loadingCurrent: false,
    previousCountryCode: "US",
    currentCountryCode: defaults.countryCode
  });

  const payloadPreview = useMemo(
    () =>
      derivePayload(
        form,
        previousPoint,
        currentPoint,
        geoLookupState.previousCountryCode,
        geoLookupState.currentCountryCode
      ),
    [form, previousPoint, currentPoint, geoLookupState.previousCountryCode, geoLookupState.currentCountryCode]
  );
  const selectedDistanceKm = useMemo(
    () => haversineKm(previousPoint.lat, previousPoint.lon, currentPoint.lat, currentPoint.lon),
    [previousPoint, currentPoint]
  );
  const maxRisk = useMemo(() => history.reduce((m, x) => Math.max(m, Number(x.risk || 0)), 0), [history]);
  const geoLookupPending = geoLookupState.loadingPrevious || geoLookupState.loadingCurrent;
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

  useEffect(() => {
    setGraphUserQuery(form.userId || "");
  }, [form.userId]);

  useEffect(() => {
    const controller = new AbortController();
    const reverseCountry = async (point, loadingKey, codeKey, fallbackCode) => {
      setGeoLookupState((prev) => ({ ...prev, [loadingKey]: true }));
      try {
        const url = `https://nominatim.openstreetmap.org/reverse?format=jsonv2&zoom=3&addressdetails=1&lat=${encodeURIComponent(
          point.lat
        )}&lon=${encodeURIComponent(point.lon)}`;
        const res = await fetch(url, { signal: controller.signal });
        const body = await res.json();
        const detected = String(body?.address?.country_code || "").trim().toUpperCase().slice(0, 2) || fallbackCode;
        setGeoLookupState((prev) => ({ ...prev, [loadingKey]: false, [codeKey]: detected }));
      } catch {
        if (!controller.signal.aborted) {
          setGeoLookupState((prev) => ({ ...prev, [loadingKey]: false }));
        }
      }
    };
    reverseCountry(previousPoint, "loadingPrevious", "previousCountryCode", "US");
    reverseCountry(currentPoint, "loadingCurrent", "currentCountryCode", "US");
    return () => controller.abort();
  }, [previousPoint.lat, previousPoint.lon, currentPoint.lat, currentPoint.lon]);

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
  const activeIndex = hoveredIndex >= 0 ? hoveredIndex : -1;
  const activePoint = activeIndex >= 0 ? history[activeIndex] : null;
  const activeXY = activePoint ? chartPointAt(activeIndex, activePoint.risk, history.length, width, height, pad) : null;
  const tooltipWidth = 150;
  const tooltipHeight = 54;
  const tooltipX = activeXY ? Math.max(pad + 2, Math.min(activeXY.x + 10, width - tooltipWidth - 4)) : 0;
  const tooltipY = activeXY ? Math.max(pad + 2, Math.min(activeXY.y - 62, height - tooltipHeight - 4)) : 0;
  const yTicks = [1, 0.75, 0.5, 0.25, 0];
  const filteredGraphUsers = useMemo(() => {
    const q = String(graphUserQuery || "").trim().toLowerCase();
    if (!q) return knownUsers;
    return knownUsers.filter((u) => String(u).toLowerCase().includes(q));
  }, [knownUsers, graphUserQuery]);
  const pageMeta = {
    dashboard: {
      title: "Behavioral Anomaly Workbench",
      subtitle: "Real-time adaptive authentication simulation"
    },
    simulation: {
      title: "Simulation",
      subtitle: "Run events and inspect adaptive-auth decisions"
    },
    "user-graphs": {
      title: "User Graphs",
      subtitle: "Visual trend analysis of user risk history"
    },
    "risk-events": {
      title: "Risk Events",
      subtitle: "Latest evaluated events and anomaly outcomes"
    }
  };
  const meta = pageMeta[activePage] || pageMeta.dashboard;
  const loadGraphForUser = (candidate) => {
    const query = String(candidate || "").trim();
    if (!query) return;
    const exact = knownUsers.find((u) => String(u).toLowerCase() === query.toLowerCase());
    const selected = exact || filteredGraphUsers[0] || query;
    setGraphUserQuery(selected);
    onChange("userId", selected);
    loadHistory(selected);
  };

  return (
    <main className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">A</div>
          <div>
            <h1>Adaptive Auth</h1>
            <p>Anomaly Console</p>
          </div>
        </div>
        <nav className="menu">
          <button type="button" className={`menu-item ${activePage === "dashboard" ? "active" : ""}`} onClick={() => setActivePage("dashboard")}>
            <span className="menu-icon">[]</span>
            <span className="menu-label">Dashboard</span>
          </button>
          <div className="menu-section-title">Configure</div>
          <button type="button" className={`menu-item ${activePage === "simulation" ? "active" : ""}`} onClick={() => setActivePage("simulation")}>
            <span className="menu-icon">[]</span>
            <span className="menu-label">Simulation</span>
          </button>
          <button type="button" className={`menu-item ${activePage === "user-graphs" ? "active" : ""}`} onClick={() => setActivePage("user-graphs")}>
            <span className="menu-icon">##</span>
            <span className="menu-label">User Graphs</span>
          </button>
          <button type="button" className={`menu-item ${activePage === "risk-events" ? "active" : ""}`} onClick={() => setActivePage("risk-events")}>
            <span className="menu-icon">!!</span>
            <span className="menu-label">Risk Events</span>
            <span className="menu-badge">Live</span>
            <span className="menu-chevron">{">"}</span>
          </button>
        </nav>
      </aside>

      <div className="content">
        <header className="topbar">
          <div>
            <h2>{meta.title}</h2>
            <p>{meta.subtitle}</p>
          </div>
          <div className="avatar">UK</div>
        </header>

        <div className="page">
          {activePage === "dashboard" && (
            <section className="panel chart-panel">
              <div className="panel-head">
                <h2>Overview</h2>
                <div className="toolbar-actions">
                  <button type="button" onClick={() => setActivePage("simulation")}>Open Simulation</button>
                  <button type="button" onClick={() => setActivePage("user-graphs")}>Open User Graphs</button>
                </div>
              </div>
              <p className="muted">
                Adaptive authentication overview for current runtime. These metrics summarize recent behavior risk signals
                and model outcomes without exposing detailed event payloads.
              </p>
              <div className="dashboard-card-grid">
                <article className="dashboard-card">
                  <span className="card-kicker">Telemetry</span>
                  <strong>{history.length}</strong>
                  <p>Total Events In View</p>
                </article>
                <article className="dashboard-card">
                  <span className="card-kicker">Risk</span>
                  <strong>{averageRisk.toFixed(3)}</strong>
                  <p>Average Risk Score</p>
                </article>
                <article className="dashboard-card">
                  <span className="card-kicker">Risk Peak</span>
                  <strong>{maxRisk.toFixed(3)}</strong>
                  <p>Maximum Observed Risk</p>
                </article>
                <article className="dashboard-card">
                  <span className="card-kicker">Threshold</span>
                  <strong>{overThresholdCount}</strong>
                  <p>Events Above 0.75</p>
                </article>
                <article className="dashboard-card">
                  <span className="card-kicker">Trend</span>
                  <strong className={`trend ${trendLabel}`}>{trendLabel}</strong>
                  <p>Current Direction</p>
                </article>
                <article className="dashboard-card">
                  <span className="card-kicker">Decision</span>
                  <strong>{response?.action || "Not evaluated"}</strong>
                  <p>Most Recent Action</p>
                </article>
              </div>
              <div className="dashboard-panels">
                <div className="dashboard-block">
                  <h3>Quick Start</h3>
                  <div className="quickstart-grid">
                    <div className="quickstep"><span>1</span><p>Open Simulation</p></div>
                    <div className="quickstep"><span>2</span><p>Run Risk Evaluation</p></div>
                    <div className="quickstep"><span>3</span><p>Inspect User Graphs</p></div>
                    <div className="quickstep"><span>4</span><p>Review Risk Events</p></div>
                  </div>
                </div>
              </div>
            </section>
          )}

          {activePage === "simulation" && (
            <>
          <section className="panel input-panel">
            <div className="panel-head">
              <h2>Simulation Console</h2>
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
          <Field label="Device Changed?">
            <select value={form.deviceChanged} onChange={(e) => onChange("deviceChanged", e.target.value)}>
              <option value="yes">Yes</option>
              <option value="no">No</option>
            </select>
          </Field>
          <Field label="IP Address">
            <input value={form.ipAddress} onChange={(e) => onChange("ipAddress", e.target.value)} />
          </Field>
          <Field label="Location Simulation (Map Click)" className="map-field">
            <MapLocationPicker
              previousPoint={previousPoint}
              currentPoint={currentPoint}
              mapTarget={mapTarget}
              onTargetChange={setMapTarget}
              onSelectPoint={(target, point) => {
                if (target === "previous") {
                  setPreviousPoint(point);
                } else {
                  setCurrentPoint(point);
                }
              }}
            />
            <div className="map-stats">
              <span>Previous: {previousPoint.lat.toFixed(2)}, {previousPoint.lon.toFixed(2)}</span>
              <span>Current: {currentPoint.lat.toFixed(2)}, {currentPoint.lon.toFixed(2)}</span>
              <span>Geo distance: {selectedDistanceKm.toFixed(1)} km</span>
              <span>
                Previous country code: {geoLookupState.previousCountryCode || "US"}
                {geoLookupState.loadingPrevious ? " (detecting...)" : ""}
              </span>
              <span>
                Current country code: {geoLookupState.currentCountryCode || form.countryCode || "US"}
                {geoLookupState.loadingCurrent ? " (detecting...)" : ""}
              </span>
              <span>
                Derived countryChangeFlag:{" "}
                {toCountryCode(geoLookupState.previousCountryCode) && toCountryCode(geoLookupState.currentCountryCode)
                  ? (toCountryCode(geoLookupState.previousCountryCode) === toCountryCode(geoLookupState.currentCountryCode) ? 0 : 1)
                  : 0}
              </span>
            </div>
          </Field>

              <button type="submit" disabled={loading || geoLookupPending}>
                {loading ? "Evaluating..." : geoLookupPending ? "Detecting Countries..." : "Run Risk Evaluation"}
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
            </>
          )}

          {activePage === "user-graphs" && (
          <section className="panel chart-panel">
            <div className="panel-head">
              <h2>User Risk Timeline</h2>
              <p>Tracked user: <strong>{form.userId}</strong></p>
            </div>
            <div className="chart-toolbar">
              <div className="chart-user-select">
                <label htmlFor="graph-user-select">Graph User</label>
                <input
                  id="graph-user-select"
                  type="search"
                  value={graphUserQuery}
                  placeholder="Search user and press Enter"
                  onChange={(e) => {
                    setGraphUserQuery(e.target.value);
                  }}
                  onFocus={() => setUserSearchFocused(true)}
                  onBlur={() => {
                    setTimeout(() => setUserSearchFocused(false), 120);
                  }}
                  onKeyDown={(e) => {
                    if (e.key !== "Enter") return;
                    e.preventDefault();
                    loadGraphForUser(graphUserQuery);
                  }}
                />
                {userSearchFocused && !!String(graphUserQuery || "").trim() && (
                  <div className="user-match-list">
                    {filteredGraphUsers.slice(0, 8).map((userId) => (
                      <button
                        key={userId}
                        type="button"
                        className="user-match-item"
                        onClick={() => loadGraphForUser(userId)}
                      >
                        {userId}
                      </button>
                    ))}
                    {!filteredGraphUsers.length && (
                      <div className="user-match-empty">No matching users</div>
                    )}
                  </div>
                )}
              </div>
              <div className="toolbar-actions">
                <button
                  type="button"
                  className="graph-load-btn"
                  onClick={() => loadGraphForUser(graphUserQuery)}
                  disabled={!String(graphUserQuery || "").trim() || historyLoading}
                >
                  {historyLoading ? "Loading Graph..." : "Load User Graph"}
                </button>
              </div>
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
                          onMouseMove={() => setHoveredIndex(idx)}
                        />
                      </g>
                    );
                  })}
                  {activeXY && (
                    <line x1={activeXY.x} y1={pad} x2={activeXY.x} y2={height - pad} className="focus-line" />
                  )}
                  {activePoint && activeXY && (
                    <g className="chart-tooltip" pointerEvents="none">
                      <rect x={tooltipX} y={tooltipY} width={tooltipWidth} height={tooltipHeight} rx="8" />
                      <text x={tooltipX + 8} y={tooltipY + 16}>{formatTs(activePoint.timestamp)}</text>
                      <text x={tooltipX + 8} y={tooltipY + 32}>Risk: {Number(activePoint.risk || 0).toFixed(3)}</text>
                      <text x={tooltipX + 8} y={tooltipY + 46}>Conf: {Number(activePoint.confidence || 0).toFixed(3)}</text>
                    </g>
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
          )}

          {activePage === "risk-events" && (
            <section className="panel chart-panel">
              <div className="panel-head">
                <h2>Recent Risk Events</h2>
                <button type="button" className="secondary-btn" onClick={() => loadHistory()} disabled={historyLoading}>
                  {historyLoading ? "Refreshing..." : "Refresh Events"}
                </button>
              </div>
              {!history.length ? (
                <p className="hint">No events available. Run simulation first.</p>
              ) : (
                <div className="history-table">
                  {history.slice().reverse().map((x, idx) => (
                    <div key={`${x.timestamp}-${idx}`} className="history-row">
                      <span>{formatTs(x.timestamp)}</span>
                      <span>risk {Number(x.risk || 0).toFixed(3)}</span>
                      <span>conf {Number(x.confidence || 0).toFixed(3)}</span>
                    </div>
                  ))}
                </div>
              )}
            </section>
          )}

        </div>
      </div>
    </main>
  );
}

function Field({ label, children, className = "" }) {
  return (
    <label className={`field ${className}`.trim()}>
      <span>{label}</span>
      {children}
    </label>
  );
}

function MapLocationPicker({ previousPoint, currentPoint, mapTarget, onTargetChange, onSelectPoint }) {
  const center = useMemo(
    () => ({
      lat: (previousPoint.lat + currentPoint.lat) / 2,
      lng: (previousPoint.lon + currentPoint.lon) / 2
    }),
    [previousPoint, currentPoint]
  );

  const previousIcon = useMemo(
    () =>
      L.divIcon({
        className: "map-pin-shell",
        html: '<div class="map-pin previous">P</div>',
        iconSize: [28, 28],
        iconAnchor: [14, 14]
      }),
    []
  );

  const currentIcon = useMemo(
    () =>
      L.divIcon({
        className: "map-pin-shell",
        html: '<div class="map-pin current">C</div>',
        iconSize: [28, 28],
        iconAnchor: [14, 14]
      }),
    []
  );

  return (
    <div className="map-picker">
      <div className="map-toggle">
        <button
          type="button"
          className={`target-previous ${mapTarget === "previous" ? "active" : ""}`.trim()}
          onClick={() => onTargetChange("previous")}
        >
          Set Previous Location
        </button>
        <button
          type="button"
          className={`target-current ${mapTarget === "current" ? "active" : ""}`.trim()}
          onClick={() => onTargetChange("current")}
        >
          Set Current Location
        </button>
      </div>
      <div className="map-help">
        Click map to set <strong>{mapTarget}</strong> location. You can also drag pins.
      </div>
      <MapContainer center={center} zoom={2} minZoom={2} className="world-map" scrollWheelZoom>
        <TileLayer
          attribution='&copy; OpenStreetMap contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        <MapClickSelector
          target={mapTarget}
          onSelect={(point) => onSelectPoint(mapTarget, point)}
        />
        <Marker
          position={[previousPoint.lat, previousPoint.lon]}
          icon={previousIcon}
          draggable
          eventHandlers={{
            dragend: (event) => {
              const marker = event.target;
              const { lat, lng } = marker.getLatLng();
              onSelectPoint("previous", { lat: Number(lat.toFixed(5)), lon: Number(lng.toFixed(5)) });
            }
          }}
        />
        <Marker
          position={[currentPoint.lat, currentPoint.lon]}
          icon={currentIcon}
          draggable
          eventHandlers={{
            dragend: (event) => {
              const marker = event.target;
              const { lat, lng } = marker.getLatLng();
              onSelectPoint("current", { lat: Number(lat.toFixed(5)), lon: Number(lng.toFixed(5)) });
            }
          }}
        />
      </MapContainer>
    </div>
  );
}

function MapClickSelector({ target, onSelect }) {
  useMapEvents({
    click(event) {
      const { lat, lng } = event.latlng;
      onSelect({
        lat: Number(lat.toFixed(5)),
        lon: Number(lng.toFixed(5))
      });
    }
  });
  return null;
}
