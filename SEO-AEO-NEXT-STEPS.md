# Roundtable: next search and AI visibility work

## September 12: discovery through writers' problems

The September 12 implementation adds `/guides/`, `/guides/beta-reader-questionnaire/`, and `/guides/conflicting-beta-reader-feedback/`. These are HTML-authored resources built by `frontend/scripts/build-static-guides.cjs`, not React routes. Each has full text, native links, a canonical URL, social metadata, and structured context. The two articles offer plain-text downloads and print styles. Their bylines disclose AI assistance; examples are explicitly invented, not recorded product output or customer evidence.

Existing public guides already satisfy the no-JavaScript content requirement. A direct fetch of the production `/beta-readers/` URL on September 12 returned HTTP 200, 18,313 bytes, the full guide headings/text, and its trailing-slash canonical. One local request took 0.356 seconds in total, with 0.355 seconds to first byte. This is one HTML-fetch measurement, not full browser load time, Core Web Vitals, a geographic benchmark, or Googlebot response time. Preserve the existing URLs. Moving them to Jekyll would not itself make their already-rendered text more crawlable.

The new guides use a small stylesheet and no executable JavaScript, external fonts, or React bundle. They are included in the generated sitemap and linked through native anchors from the shared footer and existing guide pages. The existing beta-reader overview now also explains how to find human readers for free. Static guide visits/downloads do not run the React owner-analytics collector; use Search Console landing-page data for discovery, and do not claim these pages have an attributed signup funnel.

### Free query evidence and its limits

Research used indexed public Reddit threads and Google's live autocomplete endpoint (`client=firefox`, English, US). Suggestions indicate query phrasing, not search volume or ranking difficulty. Reddit votes describe engagement in that community, not Google demand. Attempts to open both subreddits' searches with `sort=top&t=all`, including their public JSON endpoints, were blocked. Consequently this was not an exhaustive top-sorted sample. Google Search returned a JavaScript interstitial and no browser was available, so People Also Ask wording remains unverified.

- **Questionnaire: implemented first.** Google autocomplete for `beta reader` included `beta reader questionnaire`; `beta reader questions` returned `beta reader questions to ask`, `good beta reader questions`, and `beta reader feedback questions`. Recurring questions appear in [r/writing's chapter-feedback discussion](https://www.reddit.com/r/writing/comments/sht5ci/), [what to send and expect from readers](https://www.reddit.com/r/writing/comments/181763y/), and [r/BetaReaders' question-form discussion](https://www.reddit.com/r/BetaReaders/comments/1vnzp9x/discussion_beta_reader_question_form/). The resource adds a usable questionnaire, reading brief, open follow-ups, and an original worked answer.
- **Conflicting feedback: implemented second.** Repeated discussions include [how to decide whether to use feedback](https://www.reddit.com/r/writing/comments/vvmzbx/), [conflicting character/pacing reactions](https://www.reddit.com/r/writing/comments/172k128/), and [feeling overwhelmed by contradictory notes](https://www.reddit.com/r/writing/comments/1ofrmh0/just_got_my_beta_readers_feedback_and_im_freaking/). The seed `conflicting beta reader` returned no autocomplete suggestions. Prioritization is based on recurring observed problems and close product fit, not verified search volume. The worksheet separates reported reactions, suggested fixes, intended effect, and a testable revision.
- **Finding appropriate readers: expand only if useful.** Autocomplete for `how to find beta readers` included `for my book`, `for your novel`, `for free`, and `and critique partners`. The existing overview now answers the basic question. A later resource could add an original request template and a method for checking genre fit and scope, instead of duplicating the overview as another thin page.
- **Unreliable or missing feedback: research candidate.** [Ghosting discussion](https://www.reddit.com/r/BetaReaders/comments/1v5pxsw/discussion_whats_with_the_ghosting/) and [reader reliability discussion](https://www.reddit.com/r/BetaReaders/comments/1v5hkoh/discussion_is_there_any_serious_beta_reader_on/) suggest a practical reading-agreement/check-in resource. Do not infer that AI can replace the human relationship or that every unfinished read reflects the manuscript's quality.
- **Opening, pacing, and character motivation: improve existing examples.** Link the relevant worked example from each problem answer and from the questionnaire. Validate more specific language against actual landing-page queries before adding genre-specific pages. Autocomplete also surfaced beta-reader jobs and hiring terms; reader-job seekers are a different audience from authors seeking manuscript feedback.

Broaden discovery beyond people who already know the term "beta reader." The live seed `how to fix pacing` returned `how to fix pacing in writing`, `how to fix pacing in a story`, and `how to fix pacing in a novel`. [Writers asking how to improve slow pacing](https://www.reddit.com/r/writing/comments/1ch14xh/) and [how to open without boring readers](https://www.reddit.com/r/writing/comments/x64slt/) support extending the existing pacing and opening examples with a practical diagnosis exercise. The seed `is my first chapter` did not return useful writer-intent suggestions in this check. `how to make characters more` returned `interesting`, `unique`, `complex`, and `realistic`, but also unrelated gaming queries. Treat these broader topics as candidates, and qualify titles with fiction/story context. The useful progression is a writing problem, a worked exercise, a sample of feedback, and an optional product trial. Avoid promising maximum traffic from unmeasured keywords.

### Next actions for broader relevant reach

1. Publish the verified build, then inspect the two article URLs and confirm sitemap submission in Google and Bing. Request indexing once after publication. Being crawlable is not proof of indexing.
2. Cross-check the two article topics in a normal Google browser session. Record the date, query, country/language, and actual People Also Ask text. Use a relevant follow-up to improve an existing answer; do not manufacture a page for every wording variant.
3. Have writers use the questionnaire and decision worksheet on actual drafts. With permission, add a real example showing the original question, feedback, accepted/rejected changes, and why. Keep untested examples labelled. This adds evidence beyond generic writing advice.
4. Make authorship accountable when factual background is available: add an About/editorial-method page with verified experience and actual review responsibilities. Do not invent credentials or imply that an editor reviewed an AI draft.
5. Share a useful resource with writing newsletters, critique groups, and communities that permit this material. Disclose affiliation and seek independent feedback. Researching r/writing or r/BetaReaders is not permission to advertise there: [r/BetaReaders' moderator guidance](https://www.reddit.com/r/BetaReaders/comments/1t0yp6p/discussion_rbetareaders_checkin_series_share_how/) explicitly disallows AI-generated feedback and directs that material elsewhere. No outreach or messages were sent.
6. Review Search Console weekly using equal 28-day windows. Inspect the new URLs through the Pages tab even when queries are hidden. Track relevant non-brand queries, impressions by page, clicks, and the separate product activity totals. Query filters can exclude anonymized queries; do not present filtered non-brand counts as complete. Evaluate actual referrals and signup interest alongside citations, rather than treating a citation as a visit or customer.

Google says its [foundational SEO requirements also apply to AI features](https://developers.google.com/search/docs/appearance/ai-features). Useful direct answers, original examples, accessible text, internal discovery, and accurate attribution are the priorities. There is no special AI schema requirement. New guides use Article/CollectionPage and BreadcrumbList markup that describes the content; no promise of FAQ rich results is made. Google [restricts FAQ rich results](https://developers.google.com/search/blog/2023/08/howto-faq-changes) to authoritative government and health sites.

The [Growth Method article](https://growthmethod.com/aeo/) does state that sub-second pages receive three times as many crawler requests, attributing it to a [Growth Memo report](https://www.growth-memo.com/p/state-of-ai-search-optimization-2026). The accessible source does not expose enough methodology to validate that ratio or apply it to this site. Google's [crawl-efficiency guidance](https://developers.google.com/search/docs/crawling-indexing/troubleshoot-crawling-errors) says faster responses can increase capacity while quality and demand still matter. Do not turn the cited association into a guaranteed multiplier or conflate a faster HTML response with full-page rendering speed.

### Implementation checks

Run `npm.cmd run build`, `node scripts/check-public-html.cjs`, and the existing `src/searchExperience.test.js` suite from `frontend`. The HTML checker now verifies full static article inclusion, no executable guide JavaScript, a 25 KB HTML budget per static guide, download files, fragment anchors, canonical/schema/sitemap consistency, and HTML link discovery from the homepage. The three new routes are intentionally absent from the React router; all incoming links must remain ordinary anchors so the browser requests their HTML documents.

Validation completed locally: the production build passed with the existing ReadingPage/ReportPage hook warnings; all nine search-experience tests passed; the HTML checker passed all 17 public pages. Local HTTP requests returned 200 for the guide hub, both articles, stylesheet, and both text downloads. Article HTML sizes are 12,335 and 12,841 bytes; the stylesheet is 3,996 bytes. No browser was connected, so visual/mobile browser verification was not completed. Deployed to GitHub Pages on September 12 after owner authorization, including the updated reader-experience positioning. All 17 public HTML pages, sitemap, guide stylesheet, both worksheet downloads, and the current main JavaScript/CSS assets matched the verified local build in direct public HTTP checks (23 resources total). Verification details are in output/deployment-verification.json. No indexing or traffic improvement is claimed.

The prior September 11 findings below provide historical context; they are not deployment or verification evidence for this September 12 change.

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
