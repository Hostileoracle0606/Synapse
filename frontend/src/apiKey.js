// BYOK key handling — stores the user's Gemini API key in localStorage and
// exposes it to api.js, which sends it on every request as `X-Gemini-API-Key`.
//
// We intentionally use localStorage (not sessionStorage) so the key persists
// across reloads. The key never leaves the browser except to the Synapse
// backend, which forwards it to Gemini per-request.

const STORAGE_KEY = "synapse:geminiApiKey";

export function getApiKey() {
  try {
    return window.localStorage.getItem(STORAGE_KEY) || "";
  } catch {
    return "";
  }
}

export function setApiKey(key) {
  try {
    if (key && key.trim()) {
      window.localStorage.setItem(STORAGE_KEY, key.trim());
    } else {
      window.localStorage.removeItem(STORAGE_KEY);
    }
  } catch {
    // ignore — storage may be disabled
  }
}

export function hasApiKey() {
  return Boolean(getApiKey());
}

// Mask a key for display, e.g. "AIza...4LK4"
export function maskApiKey(key) {
  if (!key) return "";
  if (key.length <= 8) return "****";
  return `${key.slice(0, 4)}…${key.slice(-4)}`;
}
