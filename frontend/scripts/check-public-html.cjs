/* Verify the deployed artifacts, including discovery without JavaScript. */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { pages } = require("../src/searchContent.json");
const cases = require("../src/useCases.json");
const build = path.resolve(__dirname, "../build");
const origin = "https://roundtable.works";
const sitemap = fs.readFileSync(path.join(build, "sitemap.xml"), "utf8");
const decode = value => value.replace(/&amp;/g, "&").replace(/&#x27;/g, "'").replace(/&quot;/g, '"').replace(/&lt;/g, "<").replace(/&gt;/g, ">");
const htmlByRoute = {};
for (const [route, page] of Object.entries(pages)) {
  const html = fs.readFileSync(path.join(build, route.slice(1), "index.html"), "utf8");
  htmlByRoute[route] = html;
  assert.equal((html.match(/<h1\b/g) || []).length, 1, `${route}: exactly one H1`);
  assert.equal(decode(html.match(/<title>(.*?)<\/title>/s)[1]), page.title, `${route}: title`);
  assert.equal((html.match(/rel="canonical"/g) || []).length, 1, `${route}: one canonical`);
  assert.ok(html.includes(`rel="canonical" href="${origin}${route}"`), `${route}: canonical URL`);
  assert.ok(html.includes('name="robots" content="index, follow'), `${route}: indexable`);
  assert.ok(sitemap.includes(`<loc>${origin}${route}</loc>`), `${route}: sitemap`);
  const schema = JSON.parse(html.match(/<script id="search-structured-data" type="application\/ld\+json">(.*?)<\/script>/s)[1]);
  assert.ok(schema["@graph"].some(item => item.url === origin + route), `${route}: structured URL`);
  if (cases[route]) {
    for (const key of ["passage", "revision", "assessment", "tradeoff"]) {
      assert.ok(decode(html).includes(cases[route][key]), `${route}: visible ${key} without JavaScript`);
    }
    assert.ok(html.includes("not a recorded Roundtable run"), `${route}: example disclosure`);
  }
}
const discovered = new Set(["/"]);
for (const route of discovered) {
  for (const [, href] of htmlByRoute[route].matchAll(/href="([^"#?]+)"/g)) {
    if (pages[href]) discovered.add(href);
  }
}
assert.deepEqual([...discovered].sort(), Object.keys(pages).sort(), "Every public page must be reachable from the homepage via HTML links");
assert.equal((sitemap.match(/<loc>/g) || []).length, Object.keys(pages).length, "No private or stale sitemap URLs");
const fallback = fs.readFileSync(path.join(build, "404.html"), "utf8");
assert.ok(fallback.includes('name="robots" content="noindex, nofollow"'), "Private fallback stays unindexed");
assert.ok(!fallback.includes('rel="canonical"'), "Fallback must not claim to be the homepage");
console.log(`Verified ${discovered.size} public pages: rendered content, metadata, sitemap, link discovery, and private fallback.`);
