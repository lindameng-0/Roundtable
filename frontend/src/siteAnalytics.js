import content from "./searchContent.json";
import { getApi } from "./apiConfig";

export function referralSource(referrer) {
  let host;
  try { host = new URL(referrer).hostname.toLowerCase(); } catch { return "direct"; }
  const matches = domain => host === domain || host.endsWith(`.${domain}`);
  if (matches("roundtable.works")) return "direct";
  for (const [source, domains] of Object.entries({
    chatgpt: ["chatgpt.com", "chat.openai.com"], perplexity: ["perplexity.ai"],
    claude: ["claude.ai"], gemini: ["gemini.google.com"], copilot: ["copilot.microsoft.com"],
    google: ["google.com", "google.co.uk", "google.ca", "google.com.au", "google.de", "google.fr", "google.co.in"],
    bing: ["bing.com"], "other-search": ["duckduckgo.com", "search.yahoo.com", "search.brave.com", "baidu.com"],
    social: ["facebook.com", "instagram.com", "t.co", "x.com", "reddit.com", "linkedin.com", "youtube.com"],
  })) if (domains.some(matches)) return source;
  return "other";
}

export function trackPublicEvent(path, event = "pageview") {
  if (navigator.doNotTrack === "1" || window.doNotTrack === "1" || navigator.globalPrivacyControl) return;
  if (!content.pages[path] && !["/signup", "/login"].includes(path)) return;
  fetch(`${getApi()}/analytics/events`, {
    method: "POST", credentials: "omit", keepalive: true,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path, event, source: referralSource(document.referrer) }),
  }).catch(() => {});
}

