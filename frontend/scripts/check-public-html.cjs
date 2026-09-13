/* Verify the deployed artifacts, including discovery without JavaScript. */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const content = require("../src/searchContent.json");
const staticGuides = require("../content/guides/manifest.json");
const pages = { ...content.pages, ...staticGuides };
const cases = require("../src/useCases.json");
const build = path.resolve(__dirname, "../build");
const siteConfig = require("../src/siteConfig.json");
const origin = siteConfig.origin;
const sitemap = fs.readFileSync(path.join(build, "sitemap.xml"), "utf8");
const socialImage = path.join(build, siteConfig.socialImagePath.slice(1));
const decode = value => value.replace(/&amp;/g, "&").replace(/&#x27;/g, "'").replace(/&quot;/g, '"').replace(/&lt;/g, "<").replace(/&gt;/g, ">");
const htmlByRoute = {};
for (const [route, page] of Object.entries(pages)) {
  const canonicalUrl = `${origin}${route === "/" ? "/" : `${route}/`}`;
  const html = fs.readFileSync(path.join(build, route.slice(1), "index.html"), "utf8");
  htmlByRoute[route] = html;
  assert.equal((html.match(/<h1\b/g) || []).length, 1, `${route}: exactly one H1`);
  assert.equal(decode(html.match(/<title>(.*?)<\/title>/s)[1]), page.title, `${route}: title`);
  assert.equal((html.match(/rel="canonical"/g) || []).length, 1, `${route}: one canonical`);
  assert.ok(html.includes(`rel="canonical" href="${canonicalUrl}"`), `${route}: canonical URL matches the directory served by GitHub Pages`);
  assert.ok(html.includes(`property="og:url" content="${canonicalUrl}"`), `${route}: social URL matches canonical`);
  assert.ok(html.includes('name="robots" content="index, follow'), `${route}: indexable`);
  assert.ok(sitemap.includes(`<loc>${canonicalUrl}</loc>`), `${route}: sitemap`);
  assert.ok(sitemap.includes(`<lastmod>${page.lastModified}</lastmod>`), `${route}: accurate sitemap freshness`);
  assert.ok(html.includes(`property="og:image" content="${origin}${siteConfig.socialImagePath}"`), `${route}: social image`);
  assert.ok(html.includes(`property="og:image:width" content="${siteConfig.socialImageWidth}"`), `${route}: social image width`);
  assert.ok(html.includes(`property="og:image:height" content="${siteConfig.socialImageHeight}"`), `${route}: social image height`);
  assert.ok(html.includes('name="twitter:card" content="summary_large_image"'), `${route}: large social card`);
  const schema = JSON.parse(html.match(/<script id="search-structured-data" type="application\/ld\+json">(.*?)<\/script>/s)[1]);
  if (staticGuides[route]) {
    assert.equal((html.match(/<script\b/g) || []).length, 1, `${route}: only non-executable structured data`);
    assert.ok(!html.includes('/static/js/'), `${route}: no React bundle`);
    assert.ok(Buffer.byteLength(html) < 25000, `${route}: lightweight HTML budget`);
    const fragment = fs.readFileSync(path.join(__dirname, '../content/guides', page.file), 'utf8');
    assert.ok(html.includes(fragment), `${route}: complete authored guide visible without JavaScript`);
    assert.ok(fs.existsSync(path.join(build, 'guides.css')), `${route}: stylesheet exists`);
    if (page.download) {
      assert.ok(html.includes(`href="/guides/downloads/${page.download}" download`), `${route}: native download link`);
      const download = fs.readFileSync(path.join(build, 'guides/downloads', page.download), 'utf8');
      assert.ok(download.length > 500, `${route}: usable worksheet exists`);
      assert.ok(download.includes(origin + route + '/'), `${route}: download links to the canonical domain`);
    }
    const ids = new Set([...html.matchAll(/\bid="([^"]+)"/g)].map(match => match[1]));
    for (const [, anchor] of html.matchAll(/href="#([^"]+)"/g)) assert.ok(ids.has(anchor), `${route}: valid anchor ${anchor}`);
  }
  assert.ok(schema["@graph"].some(item => item.url === canonicalUrl), `${route}: structured URL`);
  for (const node of schema["@graph"].filter(item => item["@type"] === "BreadcrumbList")) {
    assert.ok(node.itemListElement.every(item => item.item.endsWith("/")), `${route}: canonical breadcrumb URLs`);
  }
  if (cases[route]) {
    for (const key of ["passage", "revision", "assessment", "tradeoff"]) {
      assert.ok(decode(html).includes(cases[route][key]), `${route}: visible ${key} without JavaScript`);
    }
    assert.ok(html.includes("not a recorded Readerfold run"), `${route}: example disclosure`);
  }
}
assert.ok(fs.statSync(socialImage).size > 10000, "Social image is included in the build");
const discovered = new Set(["/"]);
assert.equal(fs.readFileSync(path.join(build, "CNAME"), "utf8").trim(), new URL(origin).hostname, "Deployment hostname matches canonical origin");
assert.ok(fs.readFileSync(path.join(build, "robots.txt"), "utf8").includes(`Sitemap: ${origin}/sitemap.xml`), "Robots sitemap matches canonical origin");
for (const route of discovered) {
  for (const [, href] of htmlByRoute[route].matchAll(/<a\b[^>]*href="([^"]+)"/g)) {
    const url = new URL(decode(href), origin);
    const target = url.pathname.replace(/\/$/, "") || "/";
    if (url.origin === origin && pages[target]) {
      assert.ok(url.pathname.endsWith("/"), `${route}: public link ${href} must avoid a directory redirect`);
      discovered.add(target);
    }
  }
}
assert.deepEqual([...discovered].sort(), Object.keys(pages).sort(), "Every public page must be reachable from the homepage via HTML links");
assert.equal((sitemap.match(/<loc>/g) || []).length, Object.keys(pages).length, "No private or stale sitemap URLs");
const fallback = fs.readFileSync(path.join(build, "404.html"), "utf8");
assert.ok(fallback.includes('name="robots" content="noindex, nofollow"'), "Private fallback stays unindexed");
assert.ok(!fallback.includes('rel="canonical"'), "Fallback must not claim to be the homepage");
console.log(`Verified ${discovered.size} public pages: rendered content, metadata, sitemap, link discovery, and private fallback.`);
