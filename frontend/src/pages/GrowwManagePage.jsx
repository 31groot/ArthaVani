import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Check } from "lucide-react";
import Brand from "../components/Brand";
import { disconnectGroww, growwStatus, updateGroww } from "../api";

function GrowwManagePage({ user }) {
  const navigate = useNavigate();
  const [status, setStatus] = useState(null);
  const [mode, setMode] = useState("api_key_secret");
  const [apiKey, setApiKey] = useState("");
  const [apiSecret, setApiSecret] = useState("");
  const [totpToken, setTotpToken] = useState("");
  const [totpSecret, setTotpSecret] = useState("");
  const [working, setWorking] = useState(false);
  const [disconnecting, setDisconnecting] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  useEffect(() => {
    let active = true;
    growwStatus()
      .then((value) => {
        if (active) setStatus(value);
      })
      .catch((err) => {
        if (active) setError(err.message || "Could not load Groww status.");
      });
    return () => { active = false; };
  }, []);

  async function submit(event) {
    event.preventDefault();
    setWorking(true);
    setError("");
    setSuccess("");

    try {
      const payload = mode === "api_key_secret"
        ? { auth_mode: mode, api_key: apiKey, api_secret: apiSecret }
        : { auth_mode: mode, totp_token: totpToken, totp_secret: totpSecret };

      const updated = await updateGroww(payload);
      setStatus(updated);
      setApiKey("");
      setApiSecret("");
      setTotpToken("");
      setTotpSecret("");
      setSuccess("Groww credentials updated and validated successfully.");
    } catch (err) {
      setError(err.message || "Groww credential update failed.");
    } finally {
      setWorking(false);
    }
  }

  async function handleDisconnect() {
    setDisconnecting(true);
    setError("");
    setSuccess("");
    try {
      await disconnectGroww();
      window.location.assign("/connect");
    } catch (err) {
      setError(err.message || "Could not disconnect Groww.");
    } finally {
      setDisconnecting(false);
    }
  }

  return (
    <div className="connect-page">
      <div className="connect-topbar">
        <Brand compact />
        <button className="ghost-button" onClick={() => navigate("/")}>Back to dashboard</button>
      </div>

      <main className="connect-content">
        <div className="connect-card">
          <div className="eyebrow centered-eyebrow">BROKER CONNECTION</div>
          <h1>Manage Groww.</h1>
          <p className="connect-copy">
            Rotate expired credentials without signing out. ArthaVani validates the new credentials with Groww before replacing the encrypted connection already stored for {user.email}.
          </p>

          <div className="status-pill connection-status-line">
            <span className="status-dot" />
            {status?.connected ? "Groww connected" : "Groww not connected"}
            {status?.updated_at ? ` · updated ${new Date(status.updated_at).toLocaleString()}` : ""}
          </div>

          <form onSubmit={submit} className="stack">
            <div className="auth-tabs">
              <button type="button" className={mode === "api_key_secret" ? "active" : ""} onClick={() => setMode("api_key_secret")}>API key + secret</button>
              <button type="button" className={mode === "totp" ? "active" : ""} onClick={() => setMode("totp")}>TOTP</button>
            </div>

            {mode === "api_key_secret" ? (
              <>
                <label>
                  New Groww API key
                  <input value={apiKey} onChange={(e) => setApiKey(e.target.value)} autoComplete="off" required />
                </label>
                <label>
                  New Groww API secret
                  <input type="password" value={apiSecret} onChange={(e) => setApiSecret(e.target.value)} autoComplete="new-password" required />
                </label>
              </>
            ) : (
              <>
                <label>
                  Groww TOTP token
                  <input value={totpToken} onChange={(e) => setTotpToken(e.target.value)} autoComplete="off" required />
                </label>
                <label>
                  TOTP secret
                  <input type="password" value={totpSecret} onChange={(e) => setTotpSecret(e.target.value)} autoComplete="new-password" required />
                </label>
              </>
            )}

            {error && <div className="form-error">{error}</div>}
            {success && <div className="success-message">{success}</div>}

            <button className="primary-button" disabled={working}>
              {working ? "Validating and updating…" : "Replace Groww credentials"}
              <Check size={17} />
            </button>
          </form>

          <div className="settings-danger-zone">
            <div>
              <strong>Disconnect Groww</strong>
              <span>Removes the encrypted broker credentials from ArthaVani. Your ArthaVani account remains intact.</span>
            </div>
            <button className="ghost-button danger" type="button" disabled={disconnecting} onClick={handleDisconnect}>
              {disconnecting ? "Disconnecting…" : "Disconnect"}
            </button>
          </div>
        </div>
      </main>
    </div>
  );
}

export default GrowwManagePage;
