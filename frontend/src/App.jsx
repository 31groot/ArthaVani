import { useEffect, useMemo, useState } from "react";
import { Navigate, Route, Routes, useNavigate } from "react-router-dom";
import {
  ArrowRight,
  BadgeCheck,
  BarChart3,
  Bot,
  BriefcaseBusiness,
  Check,
  ChevronDown,
  Clock3,
  Flame,
  LogOut,
  Mic,
  MicOff,
  Newspaper,
  ShieldCheck,
  Sparkles,
  TrendingDown,
  TrendingUp,
  UserRound,
  WalletCards,
  X,
} from "lucide-react";

import {
  chat,
  clearToken,
  connectGroww,
  dashboard,
  getToken,
  growwStatus,
  login,
  me,
  register,
  setToken,
} from "./api";

function formatINR(value, digits = 2) {
  if (value == null) return "—";
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value);
}

function formatPct(value) {
  if (value == null) return "—";
  return `${value > 0 ? "+" : ""}${Number(value).toFixed(2)}%`;
}

function App() {
  const [session, setSession] = useState({
    loading: true,
    user: null,
    growwConnected: false,
  });

  useEffect(() => {
    let active = true;

    async function bootstrap() {
      const token = getToken();

      if (!token) {
        if (active) setSession({ loading: false, user: null, growwConnected: false });
        return;
      }

      try {
        const [user, groww] = await Promise.all([me(), growwStatus()]);
        if (active) {
          setSession({
            loading: false,
            user,
            growwConnected: Boolean(groww.connected),
          });
        }
      } catch {
        clearToken();
        if (active) setSession({ loading: false, user: null, growwConnected: false });
      }
    }

    bootstrap();
    return () => {
      active = false;
    };
  }, []);

  if (session.loading) {
    return (
      <div className="app-shell centered">
        <div className="loader-orb" />
      </div>
    );
  }

  return (
    <Routes>
      <Route
        path="/auth"
        element={
          session.user ? (
            <Navigate to={session.growwConnected ? "/" : "/connect"} replace />
          ) : (
            <AuthPage
              onAuthenticated={(user, growwConnected) =>
                setSession((prev) => ({
                  ...prev,
                  user,
                  growwConnected,
                  loading: false,
                }))
              }
            />
          )
        }
      />

      <Route
        path="/connect"
        element={
          !session.user ? (
            <Navigate to="/auth" replace />
          ) : session.growwConnected ? (
            <Navigate to="/" replace />
          ) : (
            <GrowwConnectPage
              user={session.user}
              onConnected={() =>
                setSession((prev) => ({ ...prev, growwConnected: true }))
              }
            />
          )
        }
      />

      <Route
        path="/"
        element={
          !session.user ? (
            <Navigate to="/auth" replace />
          ) : !session.growwConnected ? (
            <Navigate to="/connect" replace />
          ) : (
            <DashboardPage
              user={session.user}
              onLogout={() => {
                clearToken();
                setSession({ loading: false, user: null, growwConnected: false });
              }}
            />
          )
        }
      />

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

function Brand({ compact = false }) {
  return (
    <div className={`brand ${compact ? "compact" : ""}`}>
      <div className="brand-mark">
        <span />
        <span />
        <span />
      </div>
      <div>
        <div className="brand-name">ArthaVani</div>
        {!compact && <div className="brand-subtitle">Finance intelligence, spoken naturally.</div>}
      </div>
    </div>
  );
}

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
            <HeroPoint icon={<Mic size={17} />} title="Voice-first" text="Talk naturally, then keep the conversation going." />
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

function HeroPoint({ icon, title, text }) {
  return (
    <div className="hero-point">
      <div className="hero-point-icon">{icon}</div>
      <div>
        <strong>{title}</strong>
        <span>{text}</span>
      </div>
    </div>
  );
}

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

function Step({ index, label, active, done }) {
  return (
    <div className={`step ${active ? "active" : ""} ${done ? "done" : ""}`}>
      <span>{done ? <Check size={13} /> : index}</span>
      <strong>{label}</strong>
    </div>
  );
}

function DashboardPage({ user, onLogout }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function loadDashboard() {
    try {
      setError("");
      const result = await dashboard();
      setData(result);
    } catch (err) {
      setError(err.message || "Could not load dashboard.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadDashboard();
    const timer = setInterval(loadDashboard, 60_000);
    return () => clearInterval(timer);
  }, []);

  const userInitial = useMemo(() => user.email?.[0]?.toUpperCase() || "A", [user.email]);

  return (
    <div className="dashboard-shell">
      <header className="dashboard-header">
        <Brand compact />

        <div className="header-center">
          <div className="live-dot" />
          <span>Markets</span>
          <span className="header-separator">/</span>
          <span className={data?.market_status?.open ? "market-open" : "market-closed"}>
            NSE {data?.market_status?.open ? "Open" : "Closed"}
          </span>
        </div>

        <div className="header-actions">
          <span className="last-updated">
            <Clock3 size={14} />
            {data?.updated_at ? "Updated just now" : "Syncing"}
          </span>
          <div className="avatar">{userInitial}</div>
          <button className="icon-button" title="Sign out" onClick={onLogout}>
            <LogOut size={17} />
          </button>
        </div>
      </header>

      <main className="dashboard-main">
        {error && <div className="dashboard-error">{error}<button onClick={loadDashboard}><RefreshIcon /></button></div>}

        <section className="dashboard-intro">
          <div>
            <div className="eyebrow">THURSDAY, YOUR MONEY AT A GLANCE</div>
            <h1>Good morning.</h1>
            <p>Here’s what is happening across your portfolio and the market.</p>
          </div>
          <div className="quick-status">
            <div className="status-pill">
              <span className="status-dot" />
              Groww connected
            </div>
            <span className="muted">{user.email}</span>
          </div>
        </section>

        <section className="hero-grid">
          <PortfolioHero data={data?.portfolio} loading={loading} />
          <AssistantCard />
        </section>

        <section className="content-grid">
          <div className="main-column">
            <NewsCard
              title="Market now"
              icon={<Newspaper size={18} />}
              items={data?.market_news || []}
              loading={loading}
            />
            <HoldingsCard holdings={data?.portfolio?.holdings || []} loading={loading} />
          </div>

          <aside className="side-column">
            <NewsCard
              title="Hot news"
              icon={<Flame size={18} />}
              items={data?.hot_news || []}
              loading={loading}
              compact
            />

            <MarketPulse status={data?.market_status} />
          </aside>
        </section>
      </main>
    </div>
  );
}

function PortfolioHero({ data, loading }) {
  if (loading) return <div className="skeleton-card tall" />;

  const pnlUp = Number(data?.profit_loss || 0) >= 0;

  return (
    <div className="portfolio-hero card-surface">
      <div className="section-kicker">
        <span>PORTFOLIO</span>
        <WalletCards size={17} />
      </div>

      <div className="portfolio-value">{formatINR(data?.current_value)}</div>
      <div className="portfolio-meta">
        <span>Total market value</span>
        <span className="meta-separator">•</span>
        <span>Cost {formatINR(data?.invested_value)}</span>
      </div>

      <div className="portfolio-stats">
        <Metric
          label="Total P&L"
          value={formatINR(data?.profit_loss)}
          sub={formatPct(data?.profit_loss_percentage)}
          positive={pnlUp}
        />
        <Metric
          label="Holdings"
          value={String(data?.holding_count ?? "—")}
          sub={data?.market_data_realtime ? "live pricing" : "fallback pricing"}
        />
        <Metric
          label="Top holding"
          value={data?.top_holding || "—"}
          sub={data?.allocation?.[0] ? `${data.allocation[0].weight_percentage}% weight` : "—"}
        />
      </div>
    </div>
  );
}

function Metric({ label, value, sub, positive }) {
  return (
    <div className="metric">
      <span className="metric-label">{label}</span>
      <strong className={positive === true ? "positive" : positive === false ? "negative" : ""}>{value}</strong>
      <span className="metric-sub">
        {positive !== undefined && (positive ? <TrendingUp size={13} /> : <TrendingDown size={13} />)}
        {sub}
      </span>
    </div>
  );
}

function HoldingsCard({ holdings, loading }) {
  return (
    <div className="card-surface">
      <div className="card-header">
        <div>
          <div className="section-kicker">YOUR HOLDINGS</div>
          <h2>Portfolio positions</h2>
        </div>
        <button className="ghost-button">All holdings <ChevronDown size={14} /></button>
      </div>

      {loading ? (
        <div className="skeleton-list">
          {[1, 2, 3].map((item) => <div className="skeleton-row" key={item} />)}
        </div>
      ) : holdings.length === 0 ? (
        <div className="empty-state">No holdings returned by Groww.</div>
      ) : (
        <div className="holdings-table-wrap">
          <table className="holdings-table">
            <thead>
              <tr>
                <th>Holding</th>
                <th>Qty</th>
                <th>Avg. price</th>
                <th>Current</th>
                <th>P&L</th>
                <th>Weight</th>
              </tr>
            </thead>
            <tbody>
              {holdings.map((holding) => {
                const positive = Number(holding.profit_loss || 0) >= 0;
                return (
                  <tr key={`${holding.trading_symbol}-${holding.exchange_used}`}>
                    <td>
                      <div className="holding-name">
                        <div className="ticker-avatar">{holding.trading_symbol.slice(0, 2)}</div>
                        <div>
                          <strong>{holding.trading_symbol}</strong>
                          <span>{holding.exchange_used || "—"}</span>
                        </div>
                      </div>
                    </td>
                    <td>{holding.quantity}</td>
                    <td>{formatINR(holding.average_price)}</td>
                    <td>{formatINR(holding.current_price)}</td>
                    <td className={positive ? "positive" : "negative"}>
                      {formatINR(holding.profit_loss)}
                      <span className="tiny-pct">{formatPct(holding.profit_loss_percentage)}</span>
                    </td>
                    <td>{holding.allocation_percentage ? `${holding.allocation_percentage}%` : "—"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function NewsCard({ title, icon, items, loading, compact }) {
  return (
    <div className={`card-surface ${compact ? "compact-news" : ""}`}>
      <div className="card-header">
        <div className="card-title-with-icon">
          <div className="news-icon">{icon}</div>
          <div>
            <div className="section-kicker">{compact ? "WHAT TO WATCH" : "LIVE HEADLINES"}</div>
            <h2>{title}</h2>
          </div>
        </div>
        <button className="circle-arrow" title="Open news">
          <ArrowRight size={15} />
        </button>
      </div>

      {loading ? (
        <div className="skeleton-news">
          {[1, 2, 3].map((item) => <div className="skeleton-news-row" key={item} />)}
        </div>
      ) : items.length === 0 ? (
        <div className="empty-state">No recent headlines available.</div>
      ) : (
        <div className="news-list">
          {items.slice(0, compact ? 5 : 6).map((item, index) => (
            <article className="news-item" key={`${item.title}-${index}`}>
              <div className="news-item-top">
                <span className="publisher">{item.publisher || "Yahoo Finance"}</span>
                <span className="news-time">{formatNewsTime(item.published)}</span>
              </div>
              <a href={item.url || "#"} target="_blank" rel="noreferrer">
                {item.title}
              </a>
              {item.ticker && <span className="news-ticker">{item.ticker}</span>}
            </article>
          ))}
        </div>
      )}
    </div>
  );
}

function MarketPulse({ status }) {
  return (
    <div className="pulse-card">
      <div className="section-kicker">MARKET PULSE</div>
      <div className="pulse-row">
        <div className={`pulse-orb ${status?.open ? "open" : "closed"}`} />
        <div>
          <strong>NSE equity market</strong>
          <span>{status?.open ? "Regular session is live." : "Outside regular session."}</span>
        </div>
      </div>
      <div className="pulse-detail">
        <span>Session</span>
        <strong>{status?.regular_session || "09:15–15:30 IST"}</strong>
      </div>
    </div>
  );
}

function AssistantCard() {
  const [messages, setMessages] = useState([
    {
      role: "assistant",
      content: "I’m ready. Ask me about your portfolio, a company, or the market.",
    },
  ]);
  const [input, setInput] = useState("");
  const [working, setWorking] = useState(false);
  const [listening, setListening] = useState(false);
  const [voiceSupported, setVoiceSupported] = useState(false);
  const [voiceError, setVoiceError] = useState("");
  const recognitionRef = useState({ current: null })[0];
  const speechBufferRef = useState({ current: "" })[0];

  useEffect(() => {
    setVoiceSupported(
      Boolean(window.SpeechRecognition || window.webkitSpeechRecognition)
    );
  }, []);

  async function send(text) {
    const value = text.trim();
    if (!value || working) return;

    setMessages((items) => [...items, { role: "user", content: value }]);
    setInput("");
    setWorking(true);
    setVoiceError("");

    try {
      const result = await chat(value);
      setMessages((items) => [
        ...items,
        { role: "assistant", content: result.message },
      ]);

      if ("speechSynthesis" in window) {
        window.speechSynthesis.cancel();
        window.speechSynthesis.speak(
          new SpeechSynthesisUtterance(result.message)
        );
      }
    } catch (err) {
      setMessages((items) => [
        ...items,
        {
          role: "assistant",
          content: err.message || "I couldn't complete that request.",
        },
      ]);
    } finally {
      setWorking(false);
    }
  }

  function stopListening() {
    recognitionRef.current?.stop();
  }

  function startListening() {
    if (listening) {
      stopListening();
      return;
    }

    const Recognition =
      window.SpeechRecognition || window.webkitSpeechRecognition;

    if (!Recognition) {
      setVoiceError(
        "Voice input is not available in this browser. Use Chrome or Edge on localhost or HTTPS."
      );
      return;
    }

    const recognition = new Recognition();
    recognition.lang = "en-IN";
    recognition.interimResults = true;
    recognition.continuous = false;
    recognition.maxAlternatives = 1;

    speechBufferRef.current = "";
    setVoiceError("");
    recognitionRef.current = recognition;

    recognition.onstart = () => setListening(true);

    recognition.onresult = (event) => {
      let transcript = "";
      for (let i = 0; i < event.results.length; i += 1) {
        transcript += event.results[i][0].transcript;
      }

      speechBufferRef.current = transcript.trim();
      setInput(speechBufferRef.current);
    };

    recognition.onerror = (event) => {
      if (event.error === "not-allowed" || event.error === "service-not-allowed") {
        setVoiceError(
          "Microphone access was blocked. Allow microphone access for localhost and try again."
        );
      } else if (event.error !== "aborted") {
        setVoiceError(`Voice input failed: ${event.error}.`);
      }
      setListening(false);
    };

    recognition.onend = () => {
      setListening(false);
      recognitionRef.current = null;

      const transcript = speechBufferRef.current.trim();
      speechBufferRef.current = "";

      if (transcript) {
        send(transcript);
      }
    };

    try {
      recognition.start();
    } catch {
      setListening(false);
      setVoiceError("Could not start the microphone. Try again.");
    }
  }

  return (
    <div className="assistant-card">
      <div className="assistant-head">
        <div className="assistant-avatar">
          <Bot size={17} />
        </div>
        <div>
          <div className="assistant-title">Ask ArthaVani</div>
          <div className="assistant-subtitle">Portfolio, markets, research</div>
        </div>
        <div className="assistant-live">
          <span />
          Ready
        </div>
      </div>

      <div className="voice-helper">
        <div className={`voice-indicator ${listening ? "active" : ""}`}>
          <Mic size={15} />
        </div>
        <div>
          <strong>{listening ? "Listening…" : "Tap Speak to talk"}</strong>
          <span>
            {listening
              ? "Speak naturally. I’ll send your question when you finish."
              : voiceSupported
                ? "Your browser microphone will turn speech into a finance question."
                : "Voice input needs Chrome or Edge on localhost or HTTPS."}
          </span>
        </div>
      </div>

      <div className="chat-messages">
        {messages.slice(-4).map((message, index) => (
          <div
            key={`${message.role}-${index}`}
            className={`chat-bubble ${message.role}`}
          >
            {message.content}
          </div>
        ))}
        {working && (
          <div className="typing" aria-label="ArthaVani is thinking">
            <span />
            <span />
            <span />
          </div>
        )}
      </div>

      <div className="assistant-input">
        <button
          className={`mic-button ${listening ? "listening" : ""}`}
          title={listening ? "Stop listening" : "Speak to ArthaVani"}
          onClick={startListening}
          disabled={working}
          aria-label={listening ? "Stop listening" : "Speak to ArthaVani"}
        >
          {listening ? <MicOff size={17} /> : <Mic size={17} />}
        </button>

        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") send(input);
          }}
          placeholder="Type or use Speak…"
          disabled={working || listening}
          aria-label="Ask ArthaVani"
        />

        <button
          className="send-button"
          onClick={() => send(input)}
          disabled={!input.trim() || working || listening}
          aria-label="Send message"
        >
          <ArrowRight size={16} />
        </button>
      </div>

      {voiceError && (
        <div className="voice-error">
          <MicOff size={14} />
          <span>{voiceError}</span>
        </div>
      )}

      <div className="assistant-hints">
        <button onClick={() => send("What is my portfolio worth?")}>
          Portfolio value
        </button>
        <button onClick={() => send("What is my largest holding?")}>
          Largest holding
        </button>
        <button onClick={() => send("What is happening in the market?")}>
          Market
        </button>
      </div>
    </div>
  );
}

function formatNewsTime(value) {
  if (!value) return "recent";

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "recent";

  const diff = Date.now() - date.getTime();
  const minutes = Math.max(1, Math.floor(diff / 60_000));

  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h`;
  return `${Math.floor(hours / 24)}d`;
}

function RefreshIcon() {
  return <span style={{ fontSize: 12 }}>Retry</span>;
}

export default App;
