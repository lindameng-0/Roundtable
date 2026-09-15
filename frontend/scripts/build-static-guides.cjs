/* Guides are authored as HTML and shipped without a React runtime. */
const fs = require("node:fs");
const path = require("node:path");
const guides = require("../content/guides/manifest.json");
const siteConfig = require("../src/siteConfig.json");
const origin = siteConfig.origin;
const escape = value => value.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

function buildStaticGuides(build) {
  for (const [route, page] of Object.entries(guides)) {
    const url = `${origin}${route}/`;
    const body = fs.readFileSync(path.join(__dirname, "../content/guides", page.file), "utf8");
    if (/<(?:script|h1)\b/i.test(body)) throw new Error(`${route}: fragments must not contain scripts or H1s`);
    const isHub = route === "/guides";
    const crumbs = [{ "@type": "ListItem", position: 1, name: "Readerfold", item: `${origin}/` }, { "@type": "ListItem", position: 2, name: "Writing guides", item: `${origin}/guides/` }];
    if (!isHub) crumbs.push({ "@type": "ListItem", position: 3, name: page.label, item: url });
    const schema = {
      "@context": "https://schema.org",
      "@graph": [
        { "@type": "Organization", "@id": `${origin}/#organization`, name: "Readerfold", url: `${origin}/` },
        { "@type": isHub ? "CollectionPage" : "Article", "@id": `${url}#${isHub ? "webpage" : "article"}`, url,
          name: page.title, headline: page.heading, description: page.description, inLanguage: "en-US",
          datePublished: "2026-09-12", dateModified: page.lastModified,
          publisher: { "@id": `${origin}/#organization` },
          ...(!isHub && { author: { "@id": `${origin}/#organization` }, mainEntityOfPage: url }) },
        { "@type": "BreadcrumbList", itemListElement: crumbs },
      ],
    };
    const html = `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>${escape(page.title)}</title><meta name="description" content="${escape(page.description)}"><meta name="robots" content="index, follow, max-image-preview:large"><link rel="canonical" href="${url}">
<link rel="icon" href="/favicon.svg" type="image/svg+xml"><link rel="stylesheet" href="/guides.css">
<meta property="og:title" content="${escape(page.title)}"><meta property="og:description" content="${escape(page.description)}"><meta property="og:url" content="${url}"><meta property="og:type" content="${isHub ? "website" : "article"}"><meta property="og:site_name" content="Readerfold"><meta property="og:image" content="${origin}${siteConfig.socialImagePath}"><meta property="og:image:width" content="${siteConfig.socialImageWidth}"><meta property="og:image:height" content="${siteConfig.socialImageHeight}"><meta property="og:image:alt" content="${escape(siteConfig.socialImageAlt)}">
<meta name="twitter:card" content="summary_large_image"><meta name="twitter:title" content="${escape(page.title)}"><meta name="twitter:description" content="${escape(page.description)}"><meta name="twitter:image" content="${origin}${siteConfig.socialImagePath}">
<script id="search-structured-data" type="application/ld+json">${JSON.stringify(schema).replace(/</g, "\\u003c")}</script></head>
<body><a class="skip-link" href="#main-content">Skip to content</a>
<header class="site-header"><a class="brand" href="/" aria-label="Readerfold home"><img src="/favicon.svg" width="40" height="40" alt="">Readerfold</a><nav aria-label="Main navigation"><a href="/guides/"${isHub ? ' aria-current="page"' : ""}>Guides</a><a href="/sample-reading/">Sample reading</a><a href="/pricing/">Pricing</a><a href="/login">Sign in</a></nav></header>
<main id="main-content" tabindex="-1"><nav class="breadcrumb" aria-label="Breadcrumb"><a href="/">Readerfold</a> / ${isHub ? "Writing guides" : `<a href="/guides/">Writing guides</a> / ${escape(page.label)}`}</nav>
<h1>${escape(page.heading)}</h1>${body}
<footer class="editorial"><p>By Readerfold. Prepared with AI assistance; examples are illustrative. These resources offer revision exercises, not evidence of how a real audience will respond.</p><p>Updated <time datetime="${page.lastModified}">${new Date(`${page.lastModified}T00:00:00Z`).toLocaleDateString("en-US", { year: "numeric", month: "long", day: "numeric", timeZone: "UTC" })}</time>. <a href="mailto:readerfold@gmail.com">Suggest a correction</a>.</p></footer></main>
<footer class="site-footer"><a class="brand" href="/">Readerfold</a><p>A little perspective for your next draft.</p><nav aria-label="Resources and policies"><a href="/guides/">Writing guides</a><a href="/beta-readers/">About beta readers</a><a href="/use-cases/">Worked revisions</a><a href="/privacy/">Privacy</a><a href="/terms/">Terms</a></nav></footer></body></html>`;
    const directory = path.join(build, route.slice(1));
    fs.mkdirSync(directory, { recursive: true });
    fs.writeFileSync(path.join(directory, "index.html"), html);
    if (page.download) {
      const target = path.join(build, "guides/downloads");
      fs.mkdirSync(target, { recursive: true });
      const text = fs.readFileSync(path.join(__dirname, "../public/guides/downloads", page.download), "utf8");
      fs.writeFileSync(path.join(target, page.download), text.replaceAll("https://roundtable.works", origin));
    }
    console.log(`Built static guide ${route}`);
  }
}
module.exports = { buildStaticGuides };
