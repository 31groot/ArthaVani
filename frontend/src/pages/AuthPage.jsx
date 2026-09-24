import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowRight } from "lucide-react";
import HeroPoint from "../components/HeroPoint";
import Brand from "../components/Brand";
import { login, me, register, setToken, growwStatus } from "../api";
import { ShieldCheck, Sparkles, Mic } from "lucide-react";

function AuthPage({ onAuthenticated }) {
  const navigate = useNavigate();
  const [mode, setMode] = useState("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [working, setWorking] = useState(false);
  const [error, setError] = useState("");

  async function submit(event) {
    event.preventDefault();
    setWorking(true);
    setError("");

    try {
      if (mode === "register") {
        await register(email, password);
      }

      const token = await login(email, password);
      setToken(token.access_token);

      const [user, groww] = await Promise.all([
        me(),
        growwStatus(),
      ]);

      onAuthenticated(user, Boolean(groww.connected));
      navigate(groww.connected ? "/" : "/connect", { replace: true });
    } catch (err) {
      setError(err.message || "Something went wrong.");
    } finally {
      setWorking(false);
    }
  }

  return (
    <div className="auth-page">
      <div className="auth-grid">
        <div className="auth-hero">
          <Brand />
          <div className="eyebrow">PERSONAL FINANCE COPILOT</div>
          <h1>Your portfolio,<br />with a voice.</h1>
          <p>
            See your holdings, stay on top of market news, and ask ArthaVani
            what matters without digging through five different screens.
          </p>

          <div className="hero-points">
            <HeroPoint icon={<ShieldCheck size={17} />} title="Private by default" text="Your account owns its data and Groww connection." />
            <HeroPoint icon={<Sparkles size={17} />} title="Grounded answers" text="The assistant answers from live tool results." />
            <HeroPoint icon={<Mic size={17} />} title="Voice-first" text="Talk naturally, interrupt responses, and keep the conversation going." />
          </div>
        </div>

        <div className="auth-card-wrap">
          <div className="auth-card">
            <div className="mobile-brand">
              <Brand compact />
            </div>

            <div className="auth-tabs">
              <button className={mode === "login" ? "active" : ""} onClick={() => setMode("login")}>
                Sign in
              </button>
              <button className={mode === "register" ? "active" : ""} onClick={() => setMode("register")}>
                Create account
              </button>
            </div>

            <div className="auth-heading">
              <h2>{mode === "login" ? "Welcome back." : "Create your account."}</h2>
              <p>
                {mode === "login"
                  ? "Pick up where you left off."
                  : "A few seconds now, then straight to your portfolio."}
              </p>
            </div>

            <form onSubmit={submit} className="stack">
              <label>
                Email
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@example.com"
                  autoComplete="email"
                  required
                />
              </label>

              <label>
                Password
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="At least 8 characters"
                  autoComplete={mode === "login" ? "current-password" : "new-password"}
                  minLength={8}
                  required
                />
              </label>

              {error && <div className="form-error">{error}</div>}

              <button className="primary-button" disabled={working}>
                {working ? "Working…" : mode === "login" ? "Sign in" : "Create account"}
                <ArrowRight size={17} />
              </button>
            </form>

            <p className="auth-footnote">
              Your Groww credentials are only entered during the connection step
              and are stored encrypted by the backend.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

export default AuthPage;
