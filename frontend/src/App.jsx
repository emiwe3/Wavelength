import { useState, useEffect } from "react";
import axios from "axios";
import ConnectButton from "./components/ConnectButton";
import StatusCard from "./components/StatusCard";
import "./App.css";

const API = "http://localhost:8000";
const DEFAULT_STATUS = { phone: null, google: false, canvas: false, slack: false, slack_workspaces: [] };

const ALL_SERVICES = [
  { key: "calendar", label: "Google Calendar", group: "google" },
  { key: "gmail",    label: "Gmail",           group: "google" },
  { key: "canvas",   label: "Canvas",          group: "canvas" },
  { key: "slack",    label: "Slack",           group: "slack"  },
];

export default function App() {
  const [showLanding, setShowLanding] = useState(() => !localStorage.getItem("wl_phone"));
  const [landingExiting, setLandingExiting] = useState(false);

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

  const fetchStatus = async () => {
    try {
      const savedPhone = localStorage.getItem("wl_phone");
      if (savedPhone) {
        await axios.post(`${API}/api/register`, { phone: savedPhone }, { withCredentials: true });
      }
      const { data } = await axios.get(`${API}/api/status`, { withCredentials: true });
      setStatus(data);
      if (data.phone) setRegistered(true);
    } catch (err) {
      console.error("[fetchStatus] error:", err);
    }
  };

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const connected = params.get("connected");
    const error = params.get("error");
    if (connected) {
      showToast(`${connected.charAt(0).toUpperCase() + connected.slice(1)} connected!`);
      window.history.replaceState({}, "", "/");
    }
    if (error) {
      showToast(`Error: ${error}`, true);
      window.history.replaceState({}, "", "/");
    }
    fetchStatus();
  }, []);

  const showToast = (msg, isError = false) => {
    setToast({ msg, isError });
    setTimeout(() => setToast(null), 3500);
  };

  useEffect(() => { localStorage.setItem("wl_selected", JSON.stringify(selected)); }, [selected]);
  useEffect(() => { localStorage.setItem("wl_confirmed", String(servicesConfirmed)); }, [servicesConfirmed]);

  const toggleService = (key) => setSelected((prev) => ({ ...prev, [key]: !prev[key] }));
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
    setShowLanding(true);
    setLandingExiting(false);
  };

  const handleGetStarted = () => {
    setLandingExiting(true);
    setTimeout(() => setShowLanding(false), 500);
  };

  const handleCanvasSubmit = async (e) => {
    e.preventDefault();
    setCanvasError("");
    setCanvasLoading(true);
    try {
      await axios.post(`${API}/api/canvas/token`, { token: canvasToken, domain: canvasDomain }, { withCredentials: true });
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
  const googleStep = needsGoogle ? stepNum++ : null;
  const canvasStep = needsCanvas ? stepNum++ : null;
  const slackStep  = needsSlack  ? stepNum++ : null;

  return (
    <>
      {/* Waves always in background */}
      <div className="wave-bg" aria-hidden="true">
        <svg className="wave-svg wave-1" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1440 80" preserveAspectRatio="none">
          <path d="M0,40 C90,0 270,80 360,40 C450,0 630,80 720,40 C810,0 990,80 1080,40 C1170,0 1350,80 1440,40 C1530,0 1710,80 1800,40 C1890,0 2070,80 2160,40 L2160,80 L0,80 Z"/>
        </svg>
        <svg className="wave-svg wave-2" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1440 80" preserveAspectRatio="none">
          <path d="M0,40 C90,0 270,80 360,40 C450,0 630,80 720,40 C810,0 990,80 1080,40 C1170,0 1350,80 1440,40 C1530,0 1710,80 1800,40 C1890,0 2070,80 2160,40 L2160,80 L0,80 Z"/>
        </svg>
        <svg className="wave-svg wave-3" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1440 80" preserveAspectRatio="none">
          <path d="M0,40 C90,0 270,80 360,40 C450,0 630,80 720,40 C810,0 990,80 1080,40 C1170,0 1350,80 1440,40 C1530,0 1710,80 1800,40 C1890,0 2070,80 2160,40 L2160,80 L0,80 Z"/>
        </svg>
      </div>

      {/* Landing hero */}
      {showLanding && (
        <div className={`landing ${landingExiting ? "landing-exit" : ""}`}>
          <div className="landing-content">
            <p className="landing-eyebrow">never miss a deadline</p>
            <h1 className="landing-title">Wavelength</h1>
            <p className="landing-sub">
              Connect your calendar, inbox, and learning tools.<br />
              Get iMessage reminders for everything that matters.
            </p>
            <button className="landing-cta" onClick={handleGetStarted}>
              Get Started
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M5 12h14M12 5l7 7-7 7"/>
              </svg>
            </button>
            <p className="landing-hint">Free · No account needed</p>
          </div>
        </div>
      )}

      {/* App */}
      {!showLanding && (
        <>
          <nav className="navbar">
            <div className="navbar-logo-wrap">
              <span className="navbar-logo">Wavelength</span>
              <svg className="navbar-wave" viewBox="0 0 80 8" preserveAspectRatio="none" xmlns="http://www.w3.org/2000/svg">
                <path d="M0,4 C10,0 20,8 30,4 C40,0 50,8 60,4 C70,0 80,8 80,4" fill="none" stroke="url(#waveGrad)" strokeWidth="1.5" strokeLinecap="round"/>
                <defs>
                  <linearGradient id="waveGrad" x1="0%" y1="0%" x2="100%" y2="0%">
                    <stop offset="0%" stopColor="rgba(255,255,255,0.1)"/>
                    <stop offset="50%" stopColor="rgba(255,255,255,0.6)"/>
                    <stop offset="100%" stopColor="rgba(255,255,255,0.1)"/>
                  </linearGradient>
                </defs>
              </svg>
            </div>
          </nav>

          <div className="container">
            {toast && (
              <div className={`toast ${toast.isError ? "error" : ""}`}>{toast.msg}</div>
            )}

            <header>
              <div className="header-row">
                <h1>Setup</h1>
                {registered && (
                  <button className="text-btn reset-btn" onClick={handleReset}>Start Over</button>
                )}
              </div>
              <p className="subtitle">Connect your accounts and get iMessage reminders for every deadline.</p>
            </header>

            {/* Step 1: Phone */}
            <section className="card">
              <h2>01 — Phone Number</h2>
              {registered ? (
                <p className="done">Registered: <strong>{status.phone || phone}</strong></p>
              ) : (
                <form onSubmit={handleRegister} className="stack-form">
                  <div className="form-group">
                    <label htmlFor="phone">Your number</label>
                    <input
                      id="phone"
                      type="tel"
                      placeholder="(555) 000-0000"
                      value={phone}
                      onChange={handlePhoneChange}
                      required
                    />
                  </div>
                  <button type="submit">Register</button>
                </form>
              )}
            </section>

            {/* Step 2: Choose services */}
            {registered && (
              <section className="card">
                <h2>02 — Choose Sources</h2>
                <p className="hint">Select what to pull deadlines from.</p>
                <div className="service-grid">
                  {ALL_SERVICES.map(({ key, label }) => (
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
                      <span>{label}</span>
                    </label>
                  ))}
                </div>
                {!servicesConfirmed ? (
                  <button onClick={() => setServicesConfirmed(true)} disabled={!anySelected} className="confirm-btn">
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

            {/* Connection steps */}
            {registered && servicesConfirmed && (
              <>
                {needsGoogle && (
                  <section className="card">
                    <h2>{String(googleStep).padStart(2, "0")} — Connect Google</h2>
                    <p className="hint">Syncing: {googleServices.map((s) => s === "calendar" ? "Google Calendar" : "Gmail").join(" + ")}</p>
                    <ConnectButton service="Google" connected={status.google} onClick={() => {
                      const svcs = googleServices.join(",");
                      window.location.href = `${API}/auth/google/start?services=${svcs}`;
                    }}>
                      Connect Google Account
                    </ConnectButton>
                  </section>
                )}

                {needsCanvas && (
                  <section className="card">
                    <h2>{String(canvasStep).padStart(2, "0")} — Connect Canvas</h2>
                    {status.canvas ? (
                      <p className="done">Canvas connected.</p>
                    ) : (
                      <form onSubmit={handleCanvasSubmit} className="stack-form">
                        {canvasDomainLocked ? (
                          <p className="hint domain-prefilled">School: <strong>{canvasDomain}</strong></p>
                        ) : (
                          <div className="form-group">
                            <label htmlFor="canvas-domain">School Domain</label>
                            <input
                              id="canvas-domain"
                              type="text"
                              placeholder="your-school.instructure.com"
                              value={canvasDomain}
                              onChange={(e) => { localStorage.removeItem("wl_canvas_domain_cleared"); setCanvasDomain(e.target.value); }}
                              required
                            />
                          </div>
                        )}
                        <div className="canvas-steps">
                          <p className="canvas-step-label">Generate your token in 3 steps</p>
                          <ol className="canvas-step-list">
                            <li>{canvasDomain ? <a href={`https://${canvasDomain}/profile/settings#access_tokens`} target="_blank" rel="noreferrer">Open Canvas Account Settings ↗</a> : "Open Canvas → Account → Settings"}</li>
                            <li>Scroll to <strong>Approved Integrations</strong> → <strong>+ New Access Token</strong></li>
                            <li>Set purpose to "Wavelength", leave expiry blank, click <strong>Generate Token</strong></li>
                          </ol>
                        </div>
                        <div className="form-group">
                          <label htmlFor="canvas-token">Access Token</label>
                          <input
                            id="canvas-token"
                            type="password"
                            placeholder="Paste your token here"
                            value={canvasToken}
                            onChange={(e) => setCanvasToken(e.target.value)}
                            required
                          />
                        </div>
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
                    <h2>{String(slackStep).padStart(2, "0")} — Connect Slack</h2>
                    <p className="hint">Connect each workspace you want Wavelength to read.</p>
                    {status.slack_workspaces?.length > 0 && (
                      <ul className="workspace-list">
                        {status.slack_workspaces.map((ws) => (
                          <li key={ws.team_id}>{ws.team_name}</li>
                        ))}
                      </ul>
                    )}
                    <ConnectButton service="Slack" connected={false} onClick={() => { window.location.href = `${API}/auth/slack/start`; }}>
                      {status.slack_workspaces?.length > 0 ? "Add Another Workspace" : "Connect Slack Account"}
                    </ConnectButton>
                  </section>
                )}

                <StatusCard status={status} selected={selected} />
              </>
            )}
          </div>
        </>
      )}
    </>
  );
}
