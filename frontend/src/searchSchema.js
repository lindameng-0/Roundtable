import content from "./searchContent.json";

export function searchSchema(path) {
  const page = content.pages[path];
  const origin = "https://roundtable.works";
  const graph = [
    { "@type": "Organization", "@id": `${origin}/#organization`, name: "Roundtable", url: `${origin}/`, founder: { "@type": "Person", name: "Linda Meng" } },
    { "@type": "WebSite", "@id": `${origin}/#website`, name: "Roundtable", url: `${origin}/`, publisher: { "@id": `${origin}/#organization` } },
    { "@type": "WebPage", name: page.title, description: page.description, url: `${origin}${path}`, isPartOf: { "@id": `${origin}/#website` } },
  ];
  if (path === "/") graph.push({ "@type": "SoftwareApplication", name: "Roundtable", applicationCategory: "ProductivityApplication", operatingSystem: "Web browser", url: `${origin}/`, description: content.faq[0].answer });
  if (path === "/" || content.guides[path]) graph.push({ "@type": "FAQPage", mainEntity: content.faq.map(item => ({ "@type": "Question", name: item.question, acceptedAnswer: { "@type": "Answer", text: item.answer } })) });
  return { "@context": "https://schema.org", "@graph": graph };
}
