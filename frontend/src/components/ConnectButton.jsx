export default function ConnectButton({ service, connected, onClick, disabled, children }) {
  return (
    <button
      className={`connect-btn ${connected ? "connected" : ""}`}
      onClick={onClick}
      disabled={disabled || connected}
    >
      {connected ? `✓ ${service} Connected` : children}
    </button>
  );
}
