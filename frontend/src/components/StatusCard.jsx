const ALL_SERVICES = [
  { key: "calendar", label: "Google Calendar", statusKey: "google" },
  { key: "gmail",    label: "Gmail",           statusKey: "google" },
  { key: "canvas",   label: "Canvas",          statusKey: "canvas" },
  { key: "slack",    label: "Slack",           statusKey: "slack"  },
];

export default function StatusCard({ status, selected = {} }) {
  const active = ALL_SERVICES.filter(({ key }) => selected[key] !== false && selected[key] !== undefined ? selected[key] : true);
  const allConnected = active.every(({ statusKey }) => status[statusKey]);

  return (
    <div className="status-card">
      <h3>Connection Status</h3>
      {active.map(({ key, label, icon, statusKey }) => (
        <div key={key} className={`status-row ${status[statusKey] ? "ok" : "pending"}`}>
          <span>{label}</span>
          <span className="badge">{status[statusKey] ? "Connected" : "Not connected"}</span>
        </div>
      ))}
      {allConnected && (
        <p className="all-set">All set! You'll receive iMessage reminders for upcoming deadlines.</p>
      )}
    </div>
  );
}
