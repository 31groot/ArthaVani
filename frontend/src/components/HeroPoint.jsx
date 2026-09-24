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

export default HeroPoint;
