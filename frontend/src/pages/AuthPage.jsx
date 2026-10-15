import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowRight, ShieldCheck, Sparkles, Mic } from "lucide-react";
import HeroPoint from "../components/HeroPoint";
import Brand from "../components/Brand";
import {
  isGrowwSkipped,
  login,
  me,
  register,
  setToken,
  growwStatus,
} from "../api";

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

    const normalizedEmail = email.trim();

    try {
      if (mode === "register") {
        // Registration returns both the new user and an access token, so a
        // second login request and immediate status lookups are unnecessary.
        const result = await register(normalizedEmail, password);

        if (!result?.access_token || !result?.user) {
          throw new Error(
            "Your account may have been created, but sign-in could not be completed. Please sign in."
          );
        }

        setToken(result.access_token);
        onAuthenticated(result.user, false);
        navigate("/connect", { replace: true });
        return;
      }

      // Keep the established flow for returning users.
      const token = await login(normalizedEmail, password);
      setToken(token.access_token);

      const [user, groww] = await Promise.all([me(), growwStatus()]);
      const growwConnected = Boolean(groww.connected);
      const growwSkipped = !growwConnected && isGrowwSkipped(user);

      onAuthenticated(user, growwConnected);
      navigate(growwConnected || growwSkipped ? "/" : "/connect", {
        replace: true,
      });
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
          <h1>
            Your portfolio,
            <br />
            with a voice.
          </h1>
          <p>
            See your holdings, stay on top of market news, and ask ArthaVani
            what matters without digging through five different screens.
          </p>

          <div className="hero-points">
            <HeroPoint
              icon={<ShieldCheck size={17} />}
              title="Private by default"
              text="Your account owns its data and Groww connection."
            />
            <HeroPoint
              icon={<Sparkles size={17} />}
              title="Grounded answers"
              text="The assistant answers from live tool results."
            />
            <HeroPoint
              icon={<Mic size={17} />}
              title="Voice-first"
              text="Talk naturally, interrupt responses, and keep the conversation going."
            />
          </div>
        </div>

        <div className="auth-card-wrap">
          <div className="auth-card">
            <div className="mobile-brand">
              <Brand compact />
            </div>

            <div className="auth-tabs">
              <button
                type="button"
                className={mode === "login" ? "active" : ""}
                disabled={working}
                onClick={() => setMode("login")}
              >
                Sign in
              </button>
              <button
                type="button"
                className={mode === "register" ? "active" : ""}
                disabled={working}
                onClick={() => setMode("register")}
              >
                Create account
              </button>
            </div>

            <div className="auth-heading">
              <h2>
                {mode === "login" ? "Welcome back." : "Create your account."}
              </h2>
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
                  onChange={(event) => setEmail(event.target.value)}
                  placeholder="you@example.com"
                  autoComplete="email"
                  required
                  disabled={working}
                />
              </label>

              <label>
                Password
                <input
                  type="password"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  placeholder="At least 8 characters"
                  autoComplete={
                    mode === "login" ? "current-password" : "new-password"
                  }
                  minLength={8}
                  required
                  disabled={working}
                />
              </label>

              {error && <div className="form-error" role="alert">{error}</div>}

              <button className="primary-button" disabled={working}>
                {working
                  ? "Working…"
                  : mode === "login"
                    ? "Sign in"
                    : "Create account"}
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
