import { useState, useEffect } from "react";
import axios from "axios";
import ConnectButton from "./components/ConnectButton";
import StatusCard from "./components/StatusCard";
import "./App.css";

const API = import.meta.env.VITE_API_URL || "http://localhost:8000";
const DEFAULT_STATUS = { phone: null, google: false, canvas: false, slack: false, slack_workspaces: [] };

const ALL_SERVICES = [
  { key: "calendar", label: "Google Calendar", icon: "🗓️", group: "google" },
  { key: "gmail",    label: "Gmail",           icon: "✉️", group: "google" },
  { key: "canvas",   label: "Canvas",          icon: "📚", group: "canvas" },
  { key: "slack",    label: "Slack",           icon: "💬", group: "slack"  },
];

export default function App() {
  const [phone, setPhone] = useState("");
  const [registered, setRegistered] = useState(false);
  const [selected, setSelected] = useState(() => {
    try {
      const saved = localStorage.getItem("wl_selected");
      return saved ? JSON.parse(saved) : { calendar: true, gmail: true, canvas: true, slack: true };
    } catch { return { calendar: true, gmail: true, canvas: true, slack: true }; }
  });
  const [servicesConfirmed, setServicesConfirmed] = useState(() => {
    return localStorage.getItem("wl_confirmed") === "true";
  });
  const [status, setStatus] = useState(DEFAULT_STATUS);
  const [canvasDomain, setCanvasDomain] = useState(() => localStorage.getItem("wl_canvas_domain") || "");
  const [canvasDomainLocked, setCanvasDomainLocked] = useState(() => !!localStorage.getItem("wl_canvas_domain"));
  const [canvasToken, setCanvasToken] = useState("");
  const [canvasError, setCanvasError] = useState("");
  const [canvasLoading, setCanvasLoading] = useState(false);
  const [toast, setToast] = useState(null);

  useEffect(() => {
    if (localStorage.getItem("wl_canvas_domain_cleared") === "true") return;
    axios.get(`${API}/api/config`).then(({ data }) => {
      if (data.canvas_domain) {
        setCanvasDomain((prev) => prev || data.canvas_domain);
        setCanvasDomainLocked(true);
        localStorage.setItem("wl_canvas_domain", data.canvas_domain);
      }
    }).catch(() => {});
  }, []);

  const fetchStatus = async (phone) => {
    try {
      const { data } = await axios.get(`${API}/api/status`, { withCredentials: true });
      // Only use session status if it matches the phone we registered with
      if (data.phone && data.phone === (phone || localStorage.getItem("wl_phone"))) {
        setStatus(data);
      } else if (phone || localStorage.getItem("wl_phone")) {
        // Re-register with our known phone to refresh status
        const knownPhone = phone || localStorage.getItem("wl_phone");
        await axios.post(`${API}/api/register`, { phone: knownPhone }, { withCredentials: true });
        const { data: data2 } = await axios.get(`${API}/api/status`, { withCredentials: true });
        setStatus(data2);
      }
    } catch {}
  };

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const connected = params.get("connected");
    const error = params.get("error");

    if (connected || error) {
      // Returning from OAuth — restore session from localStorage
      const savedPhone = localStorage.getItem("wl_phone");
      if (savedPhone) {
        setRegistered(true);
        fetchStatus(savedPhone);
      }
      if (connected) showToast(`${connected.charAt(0).toUpperCase() + connected.slice(1)} connected!`);
      if (error) showToast(`Error: ${error}`, true);
      window.history.replaceState({}, "", "/");
    } else {
      // Fresh page load — only restore if we have a saved phone
      const savedPhone = localStorage.getItem("wl_phone");
      if (savedPhone) {
        setRegistered(true);
        fetchStatus(savedPhone);
      }
      // Otherwise show registration form (don't auto-restore from someone else's session)
    }
  }, []);

  const showToast = (msg, isError = false) => {
    setToast({ msg, isError });
    setTimeout(() => setToast(null), 3500);
  };

  useEffect(() => {
    localStorage.setItem("wl_selected", JSON.stringify(selected));
  }, [selected]);

  useEffect(() => {
    localStorage.setItem("wl_confirmed", String(servicesConfirmed));
  }, [servicesConfirmed]);

  const toggleService = (key) =>
    setSelected((prev) => ({ ...prev, [key]: !prev[key] }));

  const anySelected = Object.values(selected).some(Boolean);

  const formatPhone = (raw) => {
    const digits = raw.replace(/\D/g, "").slice(0, 10);
    if (digits.length <= 3) return digits;
    if (digits.length <= 6) return `(${digits.slice(0,3)}) ${digits.slice(3)}`;
    return `(${digits.slice(0,3)}) ${digits.slice(3,6)}-${digits.slice(6)}`;
  };

  const handlePhoneChange = (e) => setPhone(formatPhone(e.target.value));

  const handleRegister = async (e) => {
    e.preventDefault();
    const digits = phone.replace(/\D/g, "");
    if (digits.length !== 10) return showToast("Enter a valid 10-digit US number", true);
    const e164 = `+1${digits}`;
    try {
      localStorage.removeItem("wl_phone");
      try { await axios.post(`${API}/api/logout`, {}, { withCredentials: true }); } catch {}
      await axios.post(`${API}/api/register`, { phone: e164 }, { withCredentials: true });
      localStorage.setItem("wl_phone", e164);
      setRegistered(true);
      await fetchStatus();
    } catch {
      showToast("Failed to register phone number", true);
    }
  };

  const handleReset = async () => {
    localStorage.removeItem("wl_phone");
    localStorage.removeItem("wl_confirmed");
    localStorage.removeItem("wl_selected");
    localStorage.removeItem("wl_canvas_domain");
    localStorage.setItem("wl_canvas_domain_cleared", "true");
    try { await axios.post(`${API}/api/logout`, {}, { withCredentials: true }); } catch {}
    setPhone("");
    setCanvasDomain("");
    setCanvasDomainLocked(false);
    setRegistered(false);
    setServicesConfirmed(false);
    setSelected({ calendar: true, gmail: true, canvas: true, slack: true });
    setStatus(DEFAULT_STATUS);
  };

  const handleCanvasSubmit = async (e) => {
    e.preventDefault();
    setCanvasError("");
    setCanvasLoading(true);
    try {
      const savedPhone = localStorage.getItem("wl_phone") || status.phone;
      await axios.post(
        `${API}/api/canvas/token`,
        { token: canvasToken, domain: canvasDomain, phone: savedPhone },
        { withCredentials: true }
      );
      showToast("Canvas connected!");
      setCanvasToken("");
      await fetchStatus();
    } catch (err) {
      setCanvasError(err.response?.data?.error || "Invalid token or domain");
    } finally {
      setCanvasLoading(false);
    }
  };

  const googleServices = ["calendar", "gmail"].filter((k) => selected[k]);
  const needsGoogle = googleServices.length > 0;
  const needsCanvas = selected.canvas;
  const needsSlack = selected.slack;

  let stepNum = 2;
  const googleStep  = needsGoogle ? stepNum++ : null;
  const canvasStep  = needsCanvas ? stepNum++ : null;
  const slackStep   = needsSlack  ? stepNum++ : null;

  return (
    <div className="container">
      {toast && (
        <div className={`toast ${toast.isError ? "error" : ""}`}>{toast.msg}</div>
      )}

      <header>
        <div className="header-row">
          <h1>Deadline Reminder</h1>
          {registered && (
            <button className="text-btn reset-btn" onClick={handleReset}>Start Over</button>
          )}
        </div>
        <p className="subtitle">Connect your accounts and get iMessage reminders for every deadline.</p>
      </header>

      {/* Step 1: Phone */}
      <section className="card">
        <h2>1. Your Phone Number</h2>
        {registered ? (
          <p className="done">Registered: <strong>{status.phone || phone}</strong></p>
        ) : (
          <form onSubmit={handleRegister} className="row-form">
            <input
              type="tel"
              placeholder="(555) 000-0000"
              value={phone}
              onChange={handlePhoneChange}
              required
            />
            <button type="submit">Register</button>
          </form>
        )}
      </section>

      {/* Step 2: Choose services */}
      {registered && (
        <section className="card">
          <h2>2. Choose What to Sync</h2>
          <p className="hint">Select the sources you want deadline reminders from.</p>
          <div className="service-grid">
            {ALL_SERVICES.map(({ key, label, icon }) => (
              <label
                key={key}
                className={`service-option ${selected[key] ? "active" : ""} ${servicesConfirmed ? "locked" : ""}`}
              >
                <input
                  type="checkbox"
                  checked={selected[key]}
                  onChange={() => !servicesConfirmed && toggleService(key)}
                  disabled={servicesConfirmed}
                />
                <span className="service-icon">{icon}</span>
                <span>{label}</span>
              </label>
            ))}
          </div>
          {!servicesConfirmed ? (
            <button
              onClick={() => setServicesConfirmed(true)}
              disabled={!anySelected}
              className="confirm-btn"
            >
              Confirm Selection
            </button>
          ) : (
            <div className="confirmed-row">
              <span className="done">Selection confirmed.</span>
              <button className="text-btn" onClick={() => { setServicesConfirmed(false); localStorage.removeItem("wl_confirmed"); }}>Edit</button>
            </div>
          )}
        </section>
      )}

      {/* Connection steps — only for selected services */}
      {registered && servicesConfirmed && (
        <>
          {needsGoogle && (
            <section className="card">
              <h2>{googleStep}. Connect Google</h2>
              <p className="hint">
                Syncing: {googleServices.map((s) => s === "calendar" ? "Google Calendar" : "Gmail").join(" + ")}
              </p>
              <ConnectButton
                service="Google"
                connected={status.google}
                onClick={() => {
                  const savedPhone = localStorage.getItem("wl_phone") || status.phone;
                  window.location.href = `${API}/auth/google/start?phone=${encodeURIComponent(savedPhone)}`;
                }}
              >
                Connect Google Account
              </ConnectButton>
            </section>
          )}

          {needsCanvas && (
            <section className="card">
              <h2>{canvasStep}. Connect Canvas</h2>
              {status.canvas ? (
                <p className="done">Canvas connected.</p>
              ) : (
                <form onSubmit={handleCanvasSubmit} className="stack-form">
                  {canvasDomainLocked ? (
                    <p className="hint domain-prefilled">
                      School: <strong>{canvasDomain}</strong>
                    </p>
                  ) : (
                    <input
                      type="text"
                      placeholder="your-school.instructure.com"
                      value={canvasDomain}
                      onChange={(e) => { localStorage.removeItem("wl_canvas_domain_cleared"); setCanvasDomain(e.target.value); }}
                      required
                    />
                  )}
                  <div className="canvas-steps">
                    <p className="canvas-step-label">Generate your token in 3 clicks:</p>
                    <ol className="canvas-step-list">
                      <li>
                        {canvasDomain
                          ? <a href={`https://${canvasDomain}/profile/settings#access_tokens`} target="_blank" rel="noreferrer">Open Canvas Account Settings ↗</a>

                          : "Open Canvas → Account → Settings"
                        }
                      </li>
                      <li>Scroll to <strong>Approved Integrations</strong> → click <strong>+ New Access Token</strong></li>
                      <li>Set purpose (e.g. "Wavelength"), leave expiry blank, click <strong>Generate Token</strong></li>
                    </ol>
                  </div>
                  <input
                    type="password"
                    placeholder="Paste your token here"
                    value={canvasToken}
                    onChange={(e) => setCanvasToken(e.target.value)}
                    required
                  />
                  {canvasError && <p className="field-error">{canvasError}</p>}
                  <button type="submit" disabled={canvasLoading}>
                    {canvasLoading ? "Verifying…" : "Connect Canvas"}
                  </button>
                </form>
              )}
            </section>
          )}

          {needsSlack && (
            <section className="card">
              <h2>{slackStep}. Connect Slack</h2>
              <p className="hint">Connect each Slack workspace you want Wavelength to read.</p>
              {status.slack_workspaces?.length > 0 && (
                <ul className="workspace-list">
                  {status.slack_workspaces.map((ws) => (
                    <li key={ws.team_id}>✅ {ws.team_name}</li>
                  ))}
                </ul>
              )}
              <ConnectButton
                service="Slack"
                connected={false}
                onClick={() => {
                  const savedPhone = localStorage.getItem("wl_phone") || status.phone;
                  window.location.href = `${API}/auth/slack/start?phone=${encodeURIComponent(savedPhone)}`;
                }}
              >
                {status.slack_workspaces?.length > 0 ? "Add Another Workspace" : "Connect Slack Account"}
              </ConnectButton>
            </section>
          )}

          <StatusCard status={status} selected={selected} />
        </>
      )}
    </div>
  );
}
