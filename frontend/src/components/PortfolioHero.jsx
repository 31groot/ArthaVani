import { WalletCards } from "lucide-react";
import Metric from "./Metric";
import { formatINR, formatPct } from "../utils/formatters";

function PortfolioHero({ data, loading, growwConnected }) {
  if (loading) return <div className="skeleton-card tall" />;

  const pnlUp = Number(data?.profit_loss || 0) >= 0;

  return (
    <div className="portfolio-hero card-surface">
      <div className="section-kicker">
        <span>PORTFOLIO</span>
        <WalletCards size={17} />
      </div>

      <div className="portfolio-value">{growwConnected ? formatINR(data?.current_value) : "—"}</div>
      <div className="portfolio-meta">
        <span>{growwConnected ? "Total market value" : "Connect Groww to load your portfolio"}</span>
        {growwConnected && (
          <>
            <span className="meta-separator">•</span>
            <span>Cost {formatINR(data?.invested_value)}</span>
          </>
        )}
      </div>

      <div className="portfolio-stats">
        <Metric
          label="Total P&L"
          value={growwConnected ? formatINR(data?.profit_loss) : "—"}
          sub={growwConnected ? formatPct(data?.profit_loss_percentage) : "available after connection"}
          positive={pnlUp}
        />
        <Metric
          label="Holdings"
          value={growwConnected ? String(data?.holding_count ?? "—") : "—"}
          sub={growwConnected ? (data?.market_data_realtime ? "live pricing" : "fallback pricing") : "not connected"}
        />
        <Metric
          label="Top holding"
          value={growwConnected ? (data?.top_holding || "—") : "—"}
          sub={growwConnected && data?.allocation?.[0] ? `${data.allocation[0].weight_percentage}% weight` : "—"}
        />
      </div>
    </div>
  );
}

export default PortfolioHero;
