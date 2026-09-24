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

export default Brand;
