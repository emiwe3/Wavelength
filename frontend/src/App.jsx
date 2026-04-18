import { useState, useEffect } from "react";
import axios from "axios";
import ConnectButton from "./components/ConnectButton";
import StatusCard from "./components/StatusCard";
import "./App.css";

const API = "http://localhost:8000";
const DEFAULT_STATUS = { phone: null, google: false, canvas: false, slack: false };

const ALL_SERVICES = [
  { key: "calendar", label: "Google Calendar", icon: "🗓️", group: "google" },
  { key: "gmail",    label: "Gmail",           icon: "✉️", group: "google" },
  { key: "canvas",   label: "Canvas",          icon: "📚", group: "canvas" },
  { key: "slack",    label: "Slack",           icon: "💬", group: "slack"  },
];

export default function App() {
  const [phone, setPhone] = useState("");
  const [registered, setRegistered] = useState(false);
  const [selected, setSelected] = useState({ calendar: true, gmail: true, canvas: true, slack: true });
  const [servicesConfirmed, setServicesConfirmed] = useState(false);
  const [status, setStatus] = useState(DEFAULT_STATUS);
  const [canvasDomain, setCanvasDomain] = useState("");
  const [canvasToken, setCanvasToken] = useState("");
  const [canvasError, setCanvasError] = useState("");
  const [canvasLoading, setCanvasLoading] = useState(false);
  const [toast, setToast] = useState(null);

  const fetchStatus = async () => {
    try {
      const { data } = await axios.get(`${API}/api/status`, { withCredentials: true });
      setStatus(data);
      if (data.phone) setRegistered(true);
    } catch {}
  };

  useEffect(() => {
    fetchStatus();
    const params = new URLSearchParams(window.location.search);
    const connected = params.get("connected");
    const error = params.get("error");
    if (connected) {
      showToast(`${connected.charAt(0).toUpperCase() + connected.slice(1)} connected!`);
      window.history.replaceState({}, "", "/");
      fetchStatus();
    }
    if (error) {
      showToast(`Error: ${error}`, true);
      window.history.replaceState({}, "", "/");
    }
  }, []);

  const showToast = (msg, isError = false) => {
    setToast({ msg, isError });
    setTimeout(() => setToast(null), 3500);
  };

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
      await axios.post(`${API}/api/register`, { phone: e164 }, { withCredentials: true });
      setRegistered(true);
      await fetchStatus();
    } catch {
      showToast("Failed to register phone number", true);
    }
  };

  const handleCanvasSubmit = async (e) => {
    e.preventDefault();
    setCanvasError("");
    setCanvasLoading(true);
    try {
      await axios.post(
        `${API}/api/canvas/token`,
        { token: canvasToken, domain: canvasDomain },
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
        <h1>Deadline Reminder</h1>
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
              <button className="text-btn" onClick={() => setServicesConfirmed(false)}>Edit</button>
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
                  const svcs = googleServices.join(",");
                  window.location.href = `${API}/auth/google/start?services=${svcs}`;
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
                  <input
                    type="text"
                    placeholder="your-school.instructure.com"
                    value={canvasDomain}
                    onChange={(e) => setCanvasDomain(e.target.value)}
                    required
                  />
                  <input
                    type="password"
                    placeholder="Canvas API token"
                    value={canvasToken}
                    onChange={(e) => setCanvasToken(e.target.value)}
                    required
                  />
                  <p className="hint">
                    Get your token: Canvas → Account → Settings → New Access Token
                  </p>
                  {canvasError && <p className="field-error">{canvasError}</p>}
                  <button type="submit" disabled={canvasLoading}>
                    {canvasLoading ? "Verifying…" : "Save Canvas Token"}
                  </button>
                </form>
              )}
            </section>
          )}

          {needsSlack && (
            <section className="card">
              <h2>{slackStep}. Connect Slack</h2>
              <p className="hint">Reads your Slack messages for deadline mentions.</p>
              <ConnectButton
                service="Slack"
                connected={status.slack}
                onClick={() => { window.location.href = `${API}/auth/slack/start`; }}
              >
                Connect Slack Workspace
              </ConnectButton>
            </section>
          )}

          <StatusCard status={status} selected={selected} />
        </>
      )}
    </div>
  );
}
