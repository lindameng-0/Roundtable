import { referralSource, trackPublicEvent } from "./siteAnalytics";
import { searchSchema } from "./searchSchema";
import content from "./searchContent.json";

test("referral categories use actual hosts and distinguish AI services", () => {
  expect(referralSource("https://chatgpt.com/c/private")).toBe("chatgpt");
  expect(referralSource("https://gemini.google.com/app")).toBe("gemini");
  expect(referralSource("https://www.google.com/search?q=private")).toBe("google");
  expect(referralSource("https://chatgpt.com.evil.example/")).toBe("other");
  expect(referralSource("")).toBe("direct");
});

test("private paths and privacy signals prevent analytics requests", () => {
  global.fetch = jest.fn(() => Promise.resolve());
  trackPublicEvent("/read/private-manuscript");
  expect(fetch).not.toHaveBeenCalled();
  Object.defineProperty(navigator, "globalPrivacyControl", { configurable: true, value: true });
  trackPublicEvent("/");
  expect(fetch).not.toHaveBeenCalled();
  Object.defineProperty(navigator, "globalPrivacyControl", { configurable: true, value: false });
  trackPublicEvent("/");
  const options = fetch.mock.calls[0][1];
  expect(options.credentials).toBe("omit");
  expect(Object.keys(JSON.parse(options.body)).sort()).toEqual(["event", "path", "source"]);
});

test("FAQ structured data matches the visible shared answers", () => {
  const faq = searchSchema("/")["@graph"].find(node => node["@type"] === "FAQPage");
  expect(faq.mainEntity.map(item => item.acceptedAnswer.text)).toEqual(content.faq.map(item => item.answer));
  expect(searchSchema("/pricing")["@graph"].some(node => node["@type"] === "FAQPage")).toBe(false);
});

test("beta reader guide has distinct search intent and structured context", () => {
  const page = content.pages["/beta-readers"];
  const graph = searchSchema("/beta-readers")["@graph"];
  const webPage = graph.find(node => node["@type"] === "WebPage");
  expect(page.title).toMatch(/^Beta Readers for Fiction Writers/);
  expect(content.guides["/beta-readers"].intro).toMatch(/^A beta reader reads a draft/);
  expect(webPage.about).toMatchObject({ "@type": "DefinedTerm", name: "Beta reader" });
  expect(graph.some(node => node["@type"] === "BreadcrumbList")).toBe(true);
});

test("public search metadata stays concise and includes real freshness dates", () => {
  for (const page of Object.values(content.pages)) {
    expect(page.title.length).toBeLessThanOrEqual(60);
    expect(page.description.length).toBeLessThanOrEqual(160);
    expect(page.lastModified).toMatch(/^2026-\d{2}-\d{2}$/);
  }
});

test("homepage describes the real service without incomplete review markup", () => {
  const graph = searchSchema("/")["@graph"];
  const service = graph.find(node => node["@type"] === "Service");
  expect(service).toMatchObject({
    name: "Roundtable AI beta reader feedback",
    provider: { "@id": "https://roundtable.works/#organization" },
    offers: { price: 0, priceCurrency: "USD" },
  });
  expect(graph.some(node => node["@type"] === "SoftwareApplication")).toBe(false);
});

test("worked examples have their full visible breadcrumb hierarchy", () => {
  const graph = searchSchema("/use-cases/pacing-feedback")["@graph"];
  const crumbs = graph.find(node => node["@type"] === "BreadcrumbList");
  expect(crumbs.itemListElement.map(item => item.item)).toEqual([
    "https://roundtable.works/",
    "https://roundtable.works/use-cases",
    "https://roundtable.works/use-cases/pacing-feedback",
  ]);
});
