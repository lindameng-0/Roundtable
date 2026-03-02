/**
 * Single source for API base URL.
 * Uses, in order: meta[name="backend-url"] (for production without rebuild), then REACT_APP_BACKEND_URL, then localhost.
 * Ensures URL has a scheme (adds https:// if missing) so hostname-only meta values work.
 */
export function getApiBase() {
  try {
    const meta = document.querySelector('meta[name="backend-url"]');
    const fromMeta = meta && meta.getAttribute('content');
    let url = (fromMeta && fromMeta.trim()) || process.env.REACT_APP_BACKEND_URL || "http://localhost:8000";
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
