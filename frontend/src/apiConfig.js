/**
 * Single source for API base URL.
 * Uses, in order: meta[name="backend-url"] (for production without rebuild), then REACT_APP_BACKEND_URL, then localhost.
 */
export function getApiBase() {
  try {
    const meta = document.querySelector('meta[name="backend-url"]');
    const fromMeta = meta && meta.getAttribute('content');
    const url = (fromMeta && fromMeta.trim()) || process.env.REACT_APP_BACKEND_URL || "http://localhost:8000";
    return url.replace(/\/$/, "");
  } catch {
    return (process.env.REACT_APP_BACKEND_URL || "http://localhost:8000").replace(/\/$/, "");
  }
}

export function getApi() {
  return getApiBase() + "/api";
}
