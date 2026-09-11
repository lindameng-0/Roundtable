# Roundtable: next search and AI visibility work

Reviewed September 11, 2026 using the production site, repository, current official documentation, and the owner's report that individual pages appear in search while the indexing summary is dated August 28.

## Current position

Roundtable has 14 public pages with HTML content available without JavaScript, distinct metadata, structured data, a sitemap, internal links, a social preview, explanatory guides, and worked revision examples. Account and manuscript pages stay out of the sitemap. The owner previously confirmed Google and Bing verification.

The production audit found a specific inconsistency: `/beta-readers` redirects to `/beta-readers/`, but the original canonical and sitemap identified the redirecting URL. This update aligns public links, HTML and browser canonical metadata, social URLs, breadcrumb/page schema, and sitemap URLs with the final directory URLs. Existing incoming links continue to work through GitHub Pages' redirects. This resolves conflicting signals; it does not establish that they caused a ranking or reporting problem. [Google canonical guidance](https://developers.google.com/search/docs/crawling-indexing/consolidate-duplicate-urls)

## First: distinguish old reporting from an old crawl

1. In Search Console, inspect `https://roundtable.works/beta-readers/` and one recently changed example. Check the indexed result's last crawl and Google-selected canonical. An August 28 summary date alone does not establish that these pages are unindexed or that their current content has been fetched.
2. Use **Test live URL** to check what Google can access now, then compare with the stored indexed result. A successful live test is not proof of indexing.
3. Confirm that `https://roundtable.works/sitemap.xml` is submitted in Google and Bing and check its last read. After deployment, request indexing of priority changed pages once. Repeated requests do not speed up crawling; Google says recrawling can take days to weeks.

These are account actions; publishing the site does not perform them. [URL Inspection](https://support.google.com/webmasters/answer/9012289), [recrawl guidance](https://developers.google.com/search/docs/crawling-indexing/ask-google-to-recrawl)

## Highest-value next asset: a real reading with revision decisions

The current sample and use cases clearly disclose that they are curated illustrations. Keep those disclosures. Create a separate documented example using your own excerpt or one whose author has agreed to publication:

- State the intended audience and the author's specific revision question.
- Record the actual reader configuration and date of the Roundtable run.
- Show relevant passage-linked feedback exactly as produced, clearly marking any omissions.
- Explain one suggestion the author accepted and one they rejected, with reasons.
- Show the revised passage and the tradeoff it introduces; do not imply measured reader improvement without evidence.
- Include a short screen recording or screenshots with an accessible text explanation.

This is a practical way to add original experience and product evidence. It is a recommendation, not a guarantee of citations. [Google's current AI optimization guide](https://developers.google.com/search/docs/fundamentals/ai-optimization-guide)

## Give readers accountable editorial context

Add a concise About/editorial-method page explaining who makes Roundtable, who prepares or reviews the guides, and how AI-assisted examples are checked. Use verified background and credentials only. Link guide bylines to that context, show real review dates, and add Article/author schema only where it describes those visible facts. The founder name in existing organization schema is not sufficient evidence of authorship for every article. [Google's authorship guidance](https://developers.google.com/search/docs/fundamentals/creating-helpful-content#who-how-and-why)

## Measure before adding more landing pages

| Check weekly | What to do with the result |
| --- | --- |
| Google Search Console: non-brand queries and landing pages | Improve a relevant page already receiving impressions; clarify its answer and add a useful example. |
| Search Console: Settings > Search generative AI | Confirm the property includes its content in AI features. Inclusion is the default; check inherited settings too. |
| Search Console: Generative AI performance | Review AI Overview/AI Mode impressions by page. The report may be absent when there are insufficient impressions. |
| Bing Webmaster Tools: AI Performance | Review cited pages and grounding queries to learn which questions your content answers. |
| Roundtable owner analytics | Compare broad search/AI referrals and signup clicks with actual account activity. These counts are not unique users or an attributed conversion funnel. |

Google's AI control and impressions report were announced as rolled out worldwide August 31, 2026. The owner dashboard's referrer data still cannot distinguish a Google AI click from a conventional Google Search click. [Google AI control](https://support.google.com/webmasters/answer/16908024), [Google AI report](https://support.google.com/webmasters/answer/16984139), [Bing AI Performance](https://blogs.bing.com/webmaster/February-2026/Introducing-AI-Performance-in-Bing-Webmaster-Tools-Public-Preview)

For the next useful resource, validate demand for a beta-reader questionnaire or a worksheet for comparing conflicting feedback. Strengthen the existing beta-reader guide around the chosen resource. Share it with relevant writing groups and newsletters when their rules permit; seek honest, independent product feedback and references. Publication and outreach are separate work and have not been performed by this audit.

No additional skill installation is required for this work. More AI-specific markup is not the current priority: Google's guidance says `llms.txt` neither helps nor hurts its Search visibility. Useful answers, original evidence, accessible pages, and accurate descriptions remain the focus. [Google AI optimization guide](https://developers.google.com/search/docs/fundamentals/ai-optimization-guide)

## Verification of the URL update

The production build passed with existing ReadingPage/ReportPage hook warnings. Nine focused tests passed, including React metadata effects during public-to-private route changes. The HTML checker passed all 14 public pages, sitemap membership, canonical/social/schema consistency, internal link discovery, and the unindexed private fallback. A real-browser check could not complete because Chrome failed to start and no connected browser was available; no visual or full browser-navigation validation is claimed.
