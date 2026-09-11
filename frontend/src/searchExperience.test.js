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
