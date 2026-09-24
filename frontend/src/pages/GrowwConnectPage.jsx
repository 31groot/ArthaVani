import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowRight, BriefcaseBusiness, ShieldCheck, UserRound } from "lucide-react";
import Brand from "../components/Brand";
import Step from "../components/Step";
import { connectGroww } from "../api";

function GrowwConnectPage({ user, onConnected }) {
  const navigate = useNavigate();
  const [mode, setMode] = useState("api_key_secret");
  const [apiKey, setApiKey] = useState("");
  const [apiSecret, setApiSecret] = useState("");
  const [totpToken, setTotpToken] = useState("");
  const [totpSecret, setTotpSecret] = useState("");
  const [working, setWorking] = useState(false);
  const [error, setError] = useState("");

  async function submit(event) {
    event.preventDefault();
    setWorking(true);
    setError("");

    try {
      const payload =
        mode === "api_key_secret"
          ? {
              auth_mode: mode,
              api_key: apiKey,
              api_secret: apiSecret,
            }
          : {
              auth_mode: mode,
              totp_token: totpToken,
              totp_secret: totpSecret,
            };

      await connectGroww(payload);
      onConnected();
      navigate("/", { replace: true });
    } catch (err) {
      setError(err.message || "Groww connection failed.");
    } finally {
      setWorking(false);
    }
  }

  return (
    <div className="connect-page">
      <div className="connect-topbar">
        <Brand compact />
        <div className="user-chip">
          <UserRound size={15} />
          {user.email}
        </div>
      </div>

      <main className="connect-content">
        <div className="connect-progress">
          <Step index="01" label="Account" done />
          <div className="progress-line filled" />
          <Step index="02" label="Groww" active />
          <div className="progress-line" />
          <Step index="03" label="Dashboard" />
        </div>

        <div className="connect-card">
          <div className="connection-visual">
            <div className="glow-ring" />
            <div className="connection-icon"><BriefcaseBusiness size={34} /></div>
          </div>

          <div className="eyebrow centered-eyebrow">ONE-TIME CONNECTION</div>
          <h1>Bring in your Groww portfolio.</h1>
          <p className="connect-copy">
            Connect once and ArthaVani will use your saved, encrypted connection
            for your future portfolio requests.
          </p>

          <div className="mode-switch">
            <button
              className={mode === "api_key_secret" ? "active" : ""}
              onClick={() => setMode("api_key_secret")}
            >
              API key + secret
            </button>
            <button
              className={mode === "totp" ? "active" : ""}
              onClick={() => setMode("totp")}
            >
              TOTP
            </button>
          </div>

          <form onSubmit={submit} className="stack">
            {mode === "api_key_secret" ? (
              <>
                <label>
                  Groww API key
                  <input value={apiKey} onChange={(e) => setApiKey(e.target.value)} required />
                </label>
                <label>
                  Groww API secret
                  <input type="password" value={apiSecret} onChange={(e) => setApiSecret(e.target.value)} required />
                </label>
              </>
            ) : (
              <>
                <label>
                  Groww TOTP token
                  <input value={totpToken} onChange={(e) => setTotpToken(e.target.value)} required />
                </label>
                <label>
                  TOTP secret
                  <input type="password" value={totpSecret} onChange={(e) => setTotpSecret(e.target.value)} required />
                </label>
              </>
            )}

            {error && <div className="form-error">{error}</div>}

            <button className="primary-button large" disabled={working}>
              {working ? "Validating with Groww…" : "Connect Groww"}
              <ArrowRight size={18} />
            </button>
          </form>

          <div className="secure-strip">
            <ShieldCheck size={17} />
            <span>Credentials are encrypted before storage. They are never returned to the browser after connection.</span>
          </div>
        </div>
      </main>
    </div>
  );
}

export default GrowwConnectPage;
