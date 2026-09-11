const origin = "https://roundtable.works";

// GitHub Pages serves public pages as directory indexes. Match its final URL
// in HTML metadata, client navigation metadata, structured data and the sitemap.
export function publicPageUrl(path) {
  const route = path.split(/[?#]/)[0].replace(/\/+$/, "");
  return `${origin}${route}/`;
}
