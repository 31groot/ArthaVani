import { TrendingDown, TrendingUp } from "lucide-react";

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

export default Metric;
