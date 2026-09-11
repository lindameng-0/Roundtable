/* Render the actual public React pages into crawlable HTML, without a browser,
 * API credentials or network requests. GitHub Pages serves these directories.
 */
process.env.NODE_ENV = "production";
const fs = require("fs");
const path = require("path");
const babel = require("@babel/core");
const root = path.resolve(__dirname, "..");
const src = path.join(root, "src") + path.sep;
for (const ext of [".js", ".jsx"]) {
  const original = require.extensions[ext] || require.extensions[".js"];
  require.extensions[ext] = (module, filename) => {
    if (!filename.startsWith(src)) return original(module, filename);
    const { code } = babel.transformFileSync(filename, {
      babelrc: false, configFile: false,
      presets: [[require.resolve("@babel/preset-env"), { targets: { node: "current" } }], require.resolve("@babel/preset-react")],
    });
    module._compile(code, filename);
  };
}
require.extensions[".css"] = () => {};
const React = require("react");
const { renderToString } = require("react-dom/server");
const { MemoryRouter } = require("react-router-dom");
const { AuthProvider } = require("../src/context/AuthContext");
const ConfirmationProvider = require("../src/components/ConfirmationProvider").default;
const ConnectAssistantPage = require("../src/pages/ConnectAssistantPage").default;
const SampleReadingPage = require("../src/pages/SampleReadingPage").default;
const HomePage = require("../src/pages/HomePage").default;
const UseCasePage = require("../src/pages/UseCasePage").default;
const GuidePage = require("../src/pages/GuidePage").default;
const BillingPage = require("../src/pages/BillingPage").default;
const PolicyPage = require("../src/pages/PolicyPage").default;
const { pages } = require("../src/searchContent.json");
const { searchSchema } = require("../src/searchSchema");
const build = path.join(root, "build");
const manifest = JSON.parse(fs.readFileSync(path.join(build, "asset-manifest.json"), "utf8"));
const extraStyles = Object.values(manifest.files).filter(file => file.endsWith(".css") && file !== manifest.files["main.css"])
  .map(file => `<link rel="stylesheet" href="${file}">`).join("");
const template = fs.readFileSync(path.join(build, "index.html"), "utf8");
const escape = value => value.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/"/g, "&quot;");
const clean = template.replace(/<title>[\s\S]*?<\/title>/g, "")
  .replace(/<meta\s+[^>]*(?:name=["'](?:description|robots|twitter:[^"']+)["']|property=["']og:[^"']+["'])[^>]*>/g, "")
  .replace(/<link\s+[^>]*rel=["']canonical["'][^>]*>/g, "");
for (const [route, page] of Object.entries(pages)) {
  const Component = route === "/use-cases" || route.startsWith("/use-cases/") ? UseCasePage : route === "/connect-assistant" ? ConnectAssistantPage : route === "/sample-reading" ? SampleReadingPage : route === "/" ? HomePage : route === "/pricing" ? BillingPage : ["/terms", "/privacy", "/refunds"].includes(route) ? PolicyPage : GuidePage;
  const body = renderToString(React.createElement(AuthProvider, null,
    React.createElement(MemoryRouter, { initialEntries: [route] },
      React.createElement(ConfirmationProvider, null, React.createElement(Component, { kind: route.slice(1) })))));
  if (!body.includes("<h1") || body.length < 1000) throw new Error(`Missing public content: ${route}`);
  const url = `https://roundtable.works${route}`;
  const head = `<title>${escape(page.title)}</title><meta name="description" content="${escape(page.description)}"><meta name="robots" content="index, follow, max-image-preview:large"><link rel="canonical" href="${url}"><meta property="og:title" content="${escape(page.title)}"><meta property="og:description" content="${escape(page.description)}"><meta property="og:url" content="${url}"><meta property="og:type" content="website"><meta property="og:site_name" content="Roundtable"><meta name="twitter:card" content="summary"><meta name="twitter:title" content="${escape(page.title)}"><meta name="twitter:description" content="${escape(page.description)}"><script id="search-structured-data" type="application/ld+json">${JSON.stringify(searchSchema(route)).replace(/</g, "\\u003c")}</script>`;
  const html = clean.replace("</head>", `${head}${route === "/pricing" ? extraStyles : ""}</head>`).replace(/<div id="root"><\/div>/, `<div id="root">${body}</div>`);
  const directory = path.join(build, route.slice(1));
  fs.mkdirSync(directory, { recursive: true });
  fs.writeFileSync(path.join(directory, "index.html"), html);
  console.log(`Prerendered ${route}`);
}
// SPA fallback is deliberately unindexed and never copies home-page metadata.
fs.writeFileSync(path.join(build, "404.html"), clean.replace("</head>", '<title>Roundtable workspace</title><meta name="robots" content="noindex, nofollow"></head>'));
fs.writeFileSync(path.join(build, "sitemap.xml"), `<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">${Object.keys(pages).map(route => `<url><loc>https://roundtable.works${route}</loc></url>`).join("")}</urlset>`);
