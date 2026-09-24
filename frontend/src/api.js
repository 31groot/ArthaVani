const API_BASE = import.meta.env.VITE_API_BASE_URL || "";

export function getToken() {
  return localStorage.getItem("arthavani_token");
}

export function setToken(token) {
  localStorage.setItem("arthavani_token", token);
}

export function clearToken() {
  localStorage.removeItem("arthavani_token");
}

async function request(path, options = {}) {
  const token = getToken();
  const headers = new Headers(options.headers || {});

  if (options.body && !(options.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }

  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
  });

  let body = null;
  const type = response.headers.get("content-type") || "";

  if (type.includes("application/json")) {
    body = await response.json();
  } else {
    body = await response.text();
  }

  if (!response.ok) {
    const message =
      typeof body === "object" && body?.detail
        ? body.detail
        : `Request failed with ${response.status}`;
    throw new Error(message);
  }

  return body;
}

export function register(email, password) {
  return request("/api/v1/auth/register", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export function login(email, password) {
  const form = new URLSearchParams();
  form.set("username", email);
  form.set("password", password);

  return fetch(`${API_BASE}/api/v1/auth/token`, {
    method: "POST",
    headers: {
      "Content-Type": "application/x-www-form-urlencoded",
    },
    body: form.toString(),
  }).then(async (response) => {
    const body = await response.json();
    if (!response.ok) {
      throw new Error(body?.detail || "Login failed");
    }
    return body;
  });
}

export function me() {
  return request("/api/v1/auth/me");
}

export function growwStatus() {
  return request("/api/v1/integrations/groww");
}

export function connectGroww(payload) {
  return request("/api/v1/integrations/groww/connect", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateGroww(payload) {
  return request("/api/v1/integrations/groww", {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function disconnectGroww() {
  return request("/api/v1/integrations/groww", {
    method: "DELETE",
  });
}

export function dashboard() {
  return request("/api/v1/dashboard");
}

export function chat(message, conversationId = "default") {
  return request("/api/v1/chat", {
    method: "POST",
    body: JSON.stringify({
      message,
      conversation_id: conversationId,
    }),
  });
}

export function voiceSocketUrl() {
  const explicit = import.meta.env.VITE_VOICE_WS_URL;
  if (explicit) {
    return explicit.replace(/\/$/, "") + "/api/v1/voice";
  }

  // During Vite development, keep the socket same-origin so the Vite
  // /api proxy handles the WebSocket upgrade. This avoids localhost/127.0.0.1
  // mismatches and works consistently with the REST API.
  if (import.meta.env.DEV) {
    const url = new URL(window.location.origin);
    url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
    url.pathname = "/api/v1/voice";
    return url.toString();
  }

  const configuredBase = import.meta.env.VITE_API_BASE_URL || window.location.origin;
  const url = new URL(configuredBase, window.location.origin);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  const basePath = url.pathname.replace(/\/$/, "");
  url.pathname = `${basePath}/api/v1/voice`;
  url.search = "";
  url.hash = "";
  return url.toString();
}
