import { useEffect } from "react";
import { useLocation } from "react-router-dom";
import { searchSchema } from "../searchSchema";
import content from "../searchContent.json";
import { trackPublicEvent } from "../siteAnalytics";
import { publicPageUrl } from "../publicPageUrl";

export default function SearchExperience() {
  const { pathname } = useLocation();
  useEffect(() => {
    const path = pathname.replace(/\/$/, "") || "/";
    const page = content.pages[path];
    const socialImage = "https://roundtable.works/roundtable-social.jpg";
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
    canonical.href = publicPageUrl(page ? path : "/");
    if (!page) canonical.remove();
    for (const [key, value] of Object.entries({ title: document.title, description: page?.description || "Private workspace", url: page ? publicPageUrl(path) : "", type: "website", site_name: "Roundtable" })) setMeta(`og:${key}`, value, true);
    setMeta("og:image", page ? socialImage : "", true);
    setMeta("og:image:width", page ? "1200" : "", true);
    setMeta("og:image:height", page ? "630" : "", true);
    setMeta("og:image:alt", page ? "An open manuscript at a round table, surrounded by five reader perspectives" : "", true);
    setMeta("twitter:card", "summary_large_image");
    setMeta("twitter:title", document.title);
    setMeta("twitter:description", page?.description || "Private workspace");
    setMeta("twitter:image", page ? socialImage : "");
    setMeta("twitter:image:alt", page ? "An open manuscript at a round table, surrounded by five reader perspectives" : "");
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
