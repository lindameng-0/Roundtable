import content from "./searchContent.json";

export function searchSchema(path) {
  const page = content.pages[path];
  const origin = "https://roundtable.works";
  const webPage = { "@type": "WebPage", name: page.title, description: page.description, url: `${origin}${path}`, isPartOf: { "@id": `${origin}/#website` } };
  if (path === "/beta-readers") {
    webPage.about = {
      "@type": "DefinedTerm",
      name: "Beta reader",
      description: "A person who reads a draft from the intended audience's point of view and reports where the story engages, confuses, or loses them.",
    };
  }
  const graph = [
    { "@type": "Organization", "@id": `${origin}/#organization`, name: "Roundtable", url: `${origin}/`, founder: { "@type": "Person", name: "Linda Meng" } },
    { "@type": "WebSite", "@id": `${origin}/#website`, name: "Roundtable", url: `${origin}/`, publisher: { "@id": `${origin}/#organization` } },
    webPage,
  ];
  if (content.guides[path]) graph.push({
    "@type": "BreadcrumbList",
    itemListElement: [
      { "@type": "ListItem", position: 1, name: "Roundtable", item: `${origin}/` },
      { "@type": "ListItem", position: 2, name: page.title.split(" | ")[0], item: `${origin}${path}` },
    ],
  });
  if (path === "/") graph.push({ "@type": "SoftwareApplication", name: "Roundtable", applicationCategory: "ProductivityApplication", operatingSystem: "Web browser", url: `${origin}/`, description: content.faq[0].answer });
  if (path === "/" || content.guides[path]) graph.push({ "@type": "FAQPage", mainEntity: content.faq.map(item => ({ "@type": "Question", name: item.question, acceptedAnswer: { "@type": "Answer", text: item.answer } })) });
  return { "@context": "https://schema.org", "@graph": graph };
}
