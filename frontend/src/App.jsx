import { useEffect, useMemo, useRef, useState } from "react";
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
  Settings,
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
  disconnectGroww,
  updateGroww,
  getToken,
  growwStatus,
  login,
  me,
  register,
  setToken,
  voiceSocketUrl,
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
        path="/settings/groww"
        element={
          !session.user ? (
            <Navigate to="/auth" replace />
          ) : (
            <GrowwManagePage user={session.user} />
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
          <button className="icon-button" title="Manage Groww connection" onClick={() => window.location.assign("/settings/groww")}>
            <Settings size={17} />
          </button>
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
  const [ttsActive, setTtsActive] = useState(false);
  const socketRef = useRef(null);
  const streamRef = useRef(null);
  const audioContextRef = useRef(null);
  const captureNodeRef = useRef(null);
  const playbackNodeRef = useRef(null);
  const playbackSourcesRef = useRef(new Set());
  const playbackEndTimeRef = useRef(0);

  useEffect(() => {
    setVoiceSupported(
      Boolean(
        navigator.mediaDevices?.getUserMedia &&
          window.AudioContext &&
          window.AudioWorkletNode
      )
    );

    return () => {
      stopListening();
    };
  }, []);

  function stopPlayback() {
    for (const source of playbackSourcesRef.current) {
      try { source.stop(); } catch {}
      try { source.disconnect(); } catch {}
    }
    playbackSourcesRef.current.clear();
    playbackEndTimeRef.current = 0;
  }

  function queuePcmAudio(arrayBuffer) {
    const audioContext = audioContextRef.current;
    if (!audioContext || audioContext.state === "closed") return;

    let byteLength = arrayBuffer.byteLength;
    if (byteLength < 2) return;
    if (byteLength % 2 !== 0) byteLength -= 1;

    const pcm = new Int16Array(arrayBuffer, 0, byteLength / 2);
    const audioBuffer = audioContext.createBuffer(1, pcm.length, 16000);
    const channel = audioBuffer.getChannelData(0);
    for (let i = 0; i < pcm.length; i += 1) {
      channel[i] = pcm[i] / 32768;
    }

    const source = audioContext.createBufferSource();
    source.buffer = audioBuffer;
    source.connect(audioContext.destination);

    const startAt = Math.max(
      audioContext.currentTime + 0.01,
      playbackEndTimeRef.current
    );
    source.start(startAt);
    playbackEndTimeRef.current = startAt + audioBuffer.duration;

    playbackSourcesRef.current.add(source);
    source.onended = () => {
      playbackSourcesRef.current.delete(source);
      try { source.disconnect(); } catch {}
    };
  }

  async function stopListening() {
    const socket = socketRef.current;
    socketRef.current = null;

    if (socket && socket.readyState === WebSocket.OPEN) {
      try {
        socket.send(JSON.stringify({ type: "stop" }));
      } catch {
        // Socket may already be closing.
      }
      socket.close();
    }

    stopPlayback();
    captureNodeRef.current?.disconnect();
    playbackNodeRef.current?.disconnect();
    captureNodeRef.current = null;
    playbackNodeRef.current = null;

    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;

    if (audioContextRef.current) {
      try {
        await audioContextRef.current.close();
      } catch {
        // AudioContext may already be closed by the browser.
      }
      audioContextRef.current = null;
    }

    setListening(false);
  }

  async function send(text) {
    const value = text.trim();
    if (!value || working) return;

    if (listening) {
      await stopListening();
    }

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

  async function startListening() {
    if (listening) {
      await stopListening();
      return;
    }

    if (!voiceSupported) {
      setVoiceError("Live voice needs microphone access and AudioWorklet support. Use Chrome/Edge on localhost or HTTPS.");
      return;
    }

    const token = getToken();
    if (!token) {
      setVoiceError("Please sign in before starting live voice.");
      return;
    }

    setVoiceError("");
    setTtsActive(false);
    let stream;
    let audioContext;
    let socket;
    let captureNode;
    let playbackNode;
    let keepAliveGain;
    let captureReady = false;

    try {
      // Start audio output from the actual button gesture before awaiting
      // the microphone permission prompt. This avoids browsers leaving the
      // AudioContext suspended, which otherwise makes TTS silent.
      audioContext = new AudioContext();
      await audioContext.resume();

      stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });

      await audioContext.audioWorklet.addModule("/pcm-capture-worklet.js");

      socket = new WebSocket(voiceSocketUrl());
      socket.binaryType = "arraybuffer";

      socket.onopen = () => {
        socket.send(JSON.stringify({ type: "auth", token, conversation_id: "default" }));
      };

      socket.onmessage = async (event) => {
        if (typeof event.data !== "string") {
          const audio = event.data instanceof ArrayBuffer
            ? event.data
            : await event.data.arrayBuffer?.();
          if (audio) {
            if (audioContext.state !== "running") {
              await audioContext.resume().catch(() => {});
            }
            queuePcmAudio(audio);
          }
          return;
        }

        let message;
        try { message = JSON.parse(event.data); } catch { return; }

        if (message.type === "ready") {
          captureReady = true;
          setListening(true);
          setWorking(false);
          return;
        }
        if (message.type === "speech_detected") {
          setWorking(true);
          return;
        }
        if (message.type === "barge_in") {
          stopPlayback();
          setTtsActive(false);
          setWorking(true);
          return;
        }
        if (message.type === "interim_text") {
          setInput(message.text || "");
          return;
        }
        if (message.type === "user_text") {
          const text = message.text?.trim();
          if (!text) return;
          setMessages((items) => [...items, { role: "user", content: text }]);
          setInput("");
          setWorking(true);
          return;
        }
        if (message.type === "assistant_text") {
          const text = message.text?.trim();
          if (!text) return;
          setMessages((items) => [...items, { role: "assistant", content: text }]);
          setWorking(false);
          return;
        }
        if (message.type === "tts_started") {
          setTtsActive(true);
          return;
        }
        if (message.type === "tts_finished") {
          const delayMs = Math.max(0, (playbackEndTimeRef.current - audioContext.currentTime) * 1000);
          window.setTimeout(() => {
            if (audioContextRef.current === audioContext) setTtsActive(false);
          }, delayMs);
          return;
        }
        if (message.type === "tts_error") {
          setTtsActive(false);
          setVoiceError(`TTS failed: ${message.message || "unknown error"}`);
          return;
        }
        if (message.type === "error") {
          setVoiceError(message.message || "The live voice session failed.");
          setWorking(false);
        }
      };

      socket.onerror = () => {
        setTtsActive(false);
        setVoiceError("The live voice connection failed. Check the backend logs for Deepgram or TTS startup errors.");
      };
      socket.onclose = () => {
        setTtsActive(false);
        if (socketRef.current === socket) {
          socketRef.current = null;
          setListening(false);
        }
      };

      await new Promise((resolve, reject) => {
        const timer = setTimeout(() => reject(new Error("Timed out opening the voice WebSocket.")), 10000);
        if (socket.readyState === WebSocket.OPEN) {
          clearTimeout(timer);
          resolve();
          return;
        }
        socket.addEventListener("open", () => { clearTimeout(timer); resolve(); }, { once: true });
        socket.addEventListener("error", () => { clearTimeout(timer); reject(new Error("Could not open the voice WebSocket.")); }, { once: true });
      });

      await new Promise((resolve, reject) => {
        const timer = setTimeout(() => reject(new Error("Voice backend did not become ready within 15 seconds.")), 15000);
        const handler = (event) => {
          if (typeof event.data !== "string") return;
          let message;
          try { message = JSON.parse(event.data); } catch { return; }
          if (message.type === "ready") {
            clearTimeout(timer);
            socket.removeEventListener("message", handler);
            resolve();
          } else if (message.type === "error") {
            clearTimeout(timer);
            socket.removeEventListener("message", handler);
            reject(new Error(message.message || "Voice backend failed to start."));
          }
        };
        socket.addEventListener("message", handler);
      });

      const source = audioContext.createMediaStreamSource(stream);
      captureNode = new AudioWorkletNode(audioContext, "pcm16-capture", {
        processorOptions: { targetSampleRate: 16000 },
      });
      keepAliveGain = audioContext.createGain();
      keepAliveGain.gain.value = 0;

      source.connect(captureNode);
      captureNode.connect(keepAliveGain);
      keepAliveGain.connect(audioContext.destination);

      captureNode.port.onmessage = (event) => {
        if (captureReady && socket.readyState === WebSocket.OPEN) {
          socket.send(event.data);
        }
      };

      socketRef.current = socket;
      streamRef.current = stream;
      audioContextRef.current = audioContext;
      captureNodeRef.current = captureNode;
      playbackNodeRef.current = null;
    } catch (err) {
      try { socket?.close(); } catch {}
      stopPlayback();
      captureNode?.disconnect();
      keepAliveGain?.disconnect();
      stream?.getTracks().forEach((track) => track.stop());
      try { await audioContext?.close(); } catch {}
      setListening(false);
      setVoiceError(
        err?.name === "NotAllowedError"
          ? "Microphone access was blocked. Allow microphone access and try again."
          : err?.message || "Could not start live voice."
      );
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
          {listening ? "Live" : "Ready"}
        </div>
      </div>

      <div className="voice-helper">
        <div className={`voice-indicator ${listening ? "active" : ""}`}>
          <Mic size={15} />
        </div>
        <div>
          <strong>{listening ? (ttsActive ? "ArthaVani is speaking" : "Live voice is on") : "Tap Speak to talk"}</strong>
          <span>
            {listening
              ? ttsActive
                ? "Speak anytime to interrupt. Your words will appear below as they are recognized."
                : "Speak naturally. Your words appear in the input bar as ArthaVani listens."
              : voiceSupported
                ? "Streams microphone audio through Deepgram, Silero VAD and Edge-TTS."
                : "Live voice needs Chrome or Edge on localhost or HTTPS."}
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

      {voiceError && <div className="voice-error">{voiceError}</div>}

      <div className="assistant-input">
        <button
          className={`mic-button ${listening ? "listening" : ""}`}
          title={listening ? "Stop live voice" : "Speak to ArthaVani"}
          onClick={startListening}
          aria-label={listening ? "Stop live voice" : "Speak to ArthaVani"}
        >
          {listening ? <MicOff size={17} /> : <Mic size={17} />}
        </button>

        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") send(input);
          }}
          placeholder={listening ? "Listening…" : "Type or use Speak…"}
          disabled={working}
          aria-label="Ask ArthaVani"
        />

        <button
          className="send-button"
          onClick={() => send(input)}
          disabled={!input.trim() || working}
          aria-label="Send message"
        >
          <ArrowRight size={17} />
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
