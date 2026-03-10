/**
 * Single source for API base URL.
 * Priority order:
 *   1. REACT_APP_BACKEND_URL (set in .env at build time — overrides everything)
 *   2. meta[name="backend-url"] (baked into index.html for GitHub Pages → Railway)
 *   3. http://localhost:8000 (local dev fallback)
 */
export function getApiBase() {
  try {
    const fromEnv = process.env.REACT_APP_BACKEND_URL;
    if (fromEnv && fromEnv.trim()) {
      return fromEnv.trim().replace(/\/$/, "");
    }
    const meta = document.querySelector('meta[name="backend-url"]');
    const fromMeta = meta && meta.getAttribute('content');
    let url = (fromMeta && fromMeta.trim()) || "http://localhost:8000";
    url = url.replace(/\/$/, "");
    if (url && !/^https?:\/\//i.test(url)) {
      url = "https://" + url;
    }
    return url;
  } catch {
    const url = (process.env.REACT_APP_BACKEND_URL || "http://localhost:8000").replace(/\/$/, "");
    return /^https?:\/\//i.test(url) ? url : "https://" + url;
  }
}

export function getApi() {
  return getApiBase() + "/api";
}
