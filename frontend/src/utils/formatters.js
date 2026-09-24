export function formatINR(value, digits = 2) {
  if (value == null) return "—";
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value);
}

export function formatPct(value) {
  if (value == null) return "—";
  return `${value > 0 ? "+" : ""}${Number(value).toFixed(2)}%`;
}

export function formatNewsTime(value) {
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

export function safeExternalUrl(value) {
  if (!value) return "#";
  try {
    const parsed = new URL(value, window.location.href);
    if (parsed.protocol === "http:" || parsed.protocol === "https:") {
      return parsed.href;
    }
  } catch {
    // fall through to the safe default below
  }
  return "#";
}
