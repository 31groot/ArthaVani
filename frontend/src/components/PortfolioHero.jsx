import { WalletCards } from "lucide-react";
import Metric from "./Metric";
import { formatINR, formatPct } from "../utils/formatters";

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

export default PortfolioHero;
