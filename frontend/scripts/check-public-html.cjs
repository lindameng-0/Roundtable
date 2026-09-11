/* Verify the deployed artifacts, including discovery without JavaScript. */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { pages } = require("../src/searchContent.json");
const cases = require("../src/useCases.json");
const build = path.resolve(__dirname, "../build");
const origin = "https://roundtable.works";
const sitemap = fs.readFileSync(path.join(build, "sitemap.xml"), "utf8");
const socialImage = path.join(build, "roundtable-social.jpg");
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
  assert.ok(html.includes(`property="og:image" content="${origin}/roundtable-social.jpg"`), `${route}: social image`);
  assert.ok(html.includes('property="og:image:width" content="1200"'), `${route}: social image width`);
  assert.ok(html.includes('property="og:image:height" content="630"'), `${route}: social image height`);
  assert.ok(html.includes('name="twitter:card" content="summary_large_image"'), `${route}: large social card`);
  const schema = JSON.parse(html.match(/<script id="search-structured-data" type="application\/ld\+json">(.*?)<\/script>/s)[1]);
  assert.ok(schema["@graph"].some(item => item.url === canonicalUrl), `${route}: structured URL`);
  for (const node of schema["@graph"].filter(item => item["@type"] === "BreadcrumbList")) {
    assert.ok(node.itemListElement.every(item => item.item.endsWith("/")), `${route}: canonical breadcrumb URLs`);
  }
  if (cases[route]) {
    for (const key of ["passage", "revision", "assessment", "tradeoff"]) {
      assert.ok(decode(html).includes(cases[route][key]), `${route}: visible ${key} without JavaScript`);
    }
    assert.ok(html.includes("not a recorded Roundtable run"), `${route}: example disclosure`);
  }
}
assert.ok(fs.statSync(socialImage).size > 10000, "Social image is included in the build");
const discovered = new Set(["/"]);
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
