import content from "./searchContent.json";
import cases from "./useCases.json";
import { publicPageUrl } from "./publicPageUrl";

const origin = "https://roundtable.works";
const organizationId = `${origin}/#organization`;
const websiteId = `${origin}/#website`;

function breadcrumb(path, page) {
  if (cases[path]) return {
    "@type": "BreadcrumbList",
    itemListElement: [
      { "@type": "ListItem", position: 1, name: "Roundtable", item: `${origin}/` },
      { "@type": "ListItem", position: 2, name: "Writing use cases", item: publicPageUrl("/use-cases") },
      { "@type": "ListItem", position: 3, name: cases[path].label, item: publicPageUrl(path) },
    ],
  };
  if (content.guides[path] || ["/sample-reading", "/connect-assistant"].includes(path)) return {
    "@type": "BreadcrumbList",
    itemListElement: [
      { "@type": "ListItem", position: 1, name: "Roundtable", item: `${origin}/` },
      { "@type": "ListItem", position: 2, name: page.title.split(" | ")[0], item: publicPageUrl(path) },
    ],
  };
  return null;
}

export function searchSchema(path) {
  const page = content.pages[path];
  const pageUrl = publicPageUrl(path);
  const webPage = {
    "@type": "WebPage",
    "@id": `${pageUrl}#webpage`,
    name: page.title,
    description: page.description,
    url: pageUrl,
    inLanguage: "en-US",
    dateModified: page.lastModified,
    isPartOf: { "@id": websiteId },
    publisher: { "@id": organizationId },
  };
  if (path === "/beta-readers") {
    webPage.about = {
      "@type": "DefinedTerm",
      name: "Beta reader",
      description: "A person who reads a draft from the intended audience's point of view and reports where the story engages, confuses, or loses them.",
    };
  }
  const graph = [
    {
      "@type": "Organization",
      "@id": organizationId,
      name: "Roundtable",
      url: `${origin}/`,
      logo: { "@type": "ImageObject", url: `${origin}/favicon.svg`, width: 100, height: 100 },
      email: "roundtablesupport@gmail.com",
      founder: { "@type": "Person", name: "Linda Meng" },
      contactPoint: { "@type": "ContactPoint", email: "roundtablesupport@gmail.com", contactType: "customer support" },
    },
    { "@type": "WebSite", "@id": websiteId, name: "Roundtable", url: `${origin}/`, inLanguage: "en-US", publisher: { "@id": organizationId } },
    webPage,
  ];
  const breadcrumbList = breadcrumb(path, page);
  if (breadcrumbList) graph.push(breadcrumbList);
  if (path === "/") {
    const serviceId = `${origin}/#service`;
    webPage.mainEntity = { "@id": serviceId };
    graph.push({
      "@type": "Service",
      "@id": serviceId,
      name: "Roundtable AI beta reader feedback",
      serviceType: "AI-assisted manuscript feedback for fiction writers",
      url: `${origin}/`,
      description: content.faq[0].answer,
      provider: { "@id": organizationId },
      audience: { "@type": "Audience", audienceType: "Fiction writers" },
      offers: { "@type": "Offer", price: 0, priceCurrency: "USD", description: "Free starter credits; no payment card required." },
    });
  }
  if (path === "/" || content.guides[path]) graph.push({ "@type": "FAQPage", mainEntity: content.faq.map(item => ({ "@type": "Question", name: item.question, acceptedAnswer: { "@type": "Answer", text: item.answer } })) });
  return { "@context": "https://schema.org", "@graph": graph };
}
