import * as mockApi from './mockApi.js'

const _IS_DEMO = new URLSearchParams(window.location.search).has('demo')

export function isDemoMode() {
  return _IS_DEMO
}

const BASE = "/api";

async function request(path, options = {}) {
  const response = await fetch(`${BASE}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    ...options,
  });

  if (!response.ok) {
    let message = `Request failed with status ${response.status}`;
    try {
      const payload = await response.json();
      message = payload.detail || payload.message || message;
    } catch {
      const text = await response.text();
      if (text) message = text;
    }
    throw new Error(message);
  }

  if (response.status === 204) return null;
  return response.json();
}

export function createNotebook({ seedUrl, seedText, title }) {
  if (isDemoMode()) return mockApi.createNotebook({ seedUrl, seedText, title })
  return request("/notebooks", {
    method: "POST",
    body: JSON.stringify({
      seed_url: seedUrl || undefined,
      seed_text: seedText || undefined,
      title: title || undefined,
    }),
  });
}

export function getNotebook(notebookId) {
  if (isDemoMode()) return mockApi.getNotebook(notebookId)
  return request(`/notebooks/${notebookId}`);
}

export function listSources(notebookId) {
  if (isDemoMode()) return mockApi.listSources(notebookId)
  return request(`/notebooks/${notebookId}/sources`);
}

export function addSource(notebookId, { url, title, sourceType = "webpage" }) {
  if (isDemoMode()) return mockApi.addSource(notebookId, { url, title, sourceType })
  return request(`/notebooks/${notebookId}/sources`, {
    method: "POST",
    body: JSON.stringify({
      url,
      title: title || undefined,
      source_type: sourceType,
    }),
  });
}

export function getChatHistory(notebookId) {
  if (isDemoMode()) return mockApi.getChatHistory(notebookId)
  return request(`/notebooks/${notebookId}/chat`);
}

export function sendChatMessage(notebookId, message) {
  if (isDemoMode()) return mockApi.sendChatMessage(notebookId, message)
  return request(`/notebooks/${notebookId}/chat`, {
    method: "POST",
    body: JSON.stringify({ message }),
  });
}
