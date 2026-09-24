import { ArrowRight } from "lucide-react";
import { formatNewsTime, safeExternalUrl } from "../utils/formatters";

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
              <a href={safeExternalUrl(item.url)} target="_blank" rel="noopener noreferrer">
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

export default NewsCard;
