import { ChevronDown } from "lucide-react";
import { formatINR, formatPct } from "../utils/formatters";

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

export default HoldingsCard;
