import { useEffect, useMemo, useState } from "react";
import { Clock3, Flame, LogOut, Newspaper, Settings } from "lucide-react";
import Brand from "../components/Brand";
import AssistantCard from "../components/AssistantCard";
import HoldingsCard from "../components/HoldingsCard";
import MarketPulse from "../components/MarketPulse";
import NewsCard from "../components/NewsCard";
import PortfolioHero from "../components/PortfolioHero";
import RefreshIcon from "../components/RefreshIcon";
import { dashboard } from "../api";

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

export default DashboardPage;
