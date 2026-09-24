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

export default MarketPulse;
