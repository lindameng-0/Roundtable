import { useEffect } from "react";
import { useLocation } from "react-router-dom";
import { searchSchema } from "../searchSchema";
import content from "../searchContent.json";
import { trackPublicEvent } from "../siteAnalytics";

export default function SearchExperience() {
  const { pathname } = useLocation();
  useEffect(() => {
    const path = pathname.replace(/\/$/, "") || "/";
    const page = content.pages[path];
    const setMeta = (key, value, property = false) => {
      const attr = property ? "property" : "name";
      let node = document.head.querySelector(`meta[${attr}="${key}"]`);
      if (!node) { node = document.createElement("meta"); node.setAttribute(attr, key); document.head.appendChild(node); }
      node.content = value;
    };
    if (page) document.title = page.title;
    setMeta("description", page?.description || "Your private Roundtable workspace.");
    setMeta("robots", page ? "index, follow, max-image-preview:large" : "noindex, nofollow");
    let canonical = document.head.querySelector('link[rel="canonical"]');
    if (!canonical) { canonical = document.createElement("link"); canonical.rel = "canonical"; document.head.appendChild(canonical); }
    canonical.href = `https://roundtable.works${page ? path : "/"}`;
    if (!page) canonical.remove();
    for (const [key, value] of Object.entries({ title: document.title, description: page?.description || "Private workspace", url: page ? `https://roundtable.works${path}` : "", type: "website", site_name: "Roundtable" })) setMeta(`og:${key}`, value, true);
    setMeta("twitter:card", "summary");
    setMeta("twitter:title", document.title);
    setMeta("twitter:description", page?.description || "Private workspace");
    document.getElementById("search-structured-data")?.remove();
    if (page) {
      const script = document.createElement("script"); script.id = "search-structured-data"; script.type = "application/ld+json";
      script.textContent = JSON.stringify(searchSchema(path));
      document.head.appendChild(script);
    }
    // Defer so StrictMode's discarded effect does not double-count a route.
    const timer = setTimeout(() => trackPublicEvent(path), 0);
    const click = event => {
      const anchor = event.target.closest?.('a[href="/signup"]');
      if (anchor) trackPublicEvent(path, "signup_click");
    };
    document.addEventListener("click", click);
    return () => { clearTimeout(timer); document.removeEventListener("click", click); };
  }, [pathname]);
  return null;
}
