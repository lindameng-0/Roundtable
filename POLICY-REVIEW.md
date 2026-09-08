# Roundtable policy review

Prepared September 8, 2026 for Linda Meng. These are tailored drafts, not a guarantee of enforceability or Paddle approval. No deployment or live payment activation was performed.

## Public pages

- `/pricing`: existing live catalog, with clearer USD, renewal, cancellation, deliverables, and refund disclosures. Published reference prices remain visible when billing is unavailable; purchasing remains disabled in that case.
- `/terms`: sole proprietor identity, AI limitations, author ownership, limited processing licence, credit rules, subscription terms, proportionate suspension provisions, and liability limits with mandatory-rights exceptions.
- `/privacy`: information categories, processing purposes and bases, AI providers, cookies, retention criteria, international processing, and requests to exercise privacy rights.
- `/refunds`: 14-day refund for unused purchases, service-fault remedies, cancellation instructions, and Paddle/statutory rights.

All four are linked from the shared footer. Signup and pricing also link the relevant policies. The policies require no login or API response.

## Finish before publication

1. **Public inbox confirmed:** the owner supplied `roundtablesupport@gmail.com`, now configured as `SUPPORT_EMAIL` in `frontend/src/components/PolicyContact.jsx`.
2. **Business location:** confirm country/state and applicable business contact-address disclosure requirements. The draft deliberately does not invent an address or impose an arbitrary court/jurisdiction. Add appropriate location and contact details after confirmation.
3. **Operational privacy facts:** confirm the production hosting/database providers and regions, active AI models, paid/free provider tiers, retention settings, training permissions, any analytics not present in source, provider contracts, and international transfer safeguards. The source supports Google/OpenAI/Anthropic routing, Google sign-in, and Resend email, but does not establish the deployed account settings. Replace conditional provider language with the confirmed production details. The transfer wording describes required safeguards; it is not evidence that contracts are already in place.
4. **Retention and requests:** confirm actual backup/log retention and a process for account deletion, data access/export, and requests within statutory deadlines. The draft uses purpose-based retention criteria rather than making up automatic deletion periods. Manuscript deletion exists; account deletion requests require operator handling.
5. **Legal review:** check the terms against the country of operation and customer markets, especially liability, age eligibility, business identity disclosures, digital-service withdrawal rights, and data protection. Strong wording cannot remove liability imposed by law.

## Proposed commercial decisions for Linda to review

- Full refund requested within **14 calendar days** if none of that purchase's credits were used, including renewals. Used purchases are generally not refunded for a change of mind; service faults, billing errors, Paddle decisions, and statutory remedies remain covered.
- Liability cap: **the greater of US$100 or the prior 12 months of Roundtable payments**, only where lawful, with explicit exceptions for fraud, wilful misconduct, gross negligence, personal injury, mandatory consumer remedies, and data protection rights.
- Accounts are for adults **18+**.
- Authors retain manuscript rights. Limited permission is granted to process content; no public-marketing licence is taken.
- No perpetual-storage promise. If the service closes for reasons unrelated to a user's breach, appropriate refunds cover unused purchased credits and undelivered subscription service.
- Roundtable does not train models on manuscripts. On September 8, 2026, the owner confirmed opting out of provider training; the homepage, upload notice, FAQ, and privacy policy now reflect that confirmation. Provider settings were not independently inspected. Keep training disabled when changing provider accounts or routes, and retain the relevant configuration evidence. This does not establish zero retention: storage, backups, and provider retention remain disclosed.

## Pricing maintenance and launch

`frontend/src/publishedPricing.json` is a public fallback snapshot of `backend/services/billing_catalog.py` (Writer $15/200; Studio $29/450; packs $10/100, $20/220, $35/400; 50 default starter credits). Keep it aligned whenever catalog prices or the deployed starter grant change. The live API remains authoritative and is required for checkout.

Deploy only after the missing business details and factual review above are complete. Verify the HTTPS URLs by opening each in a signed-out browser directly; the static host needs SPA deep-link support. The existing deployment uses a GitHub Pages `404.html` fallback. Submit the deployed URLs to Paddle, not localhost. Actual sandbox checkout/refund/cancellation validation and Paddle approval remain separate from these page changes.

## Primary sources checked

Validation: production build passed (existing React Hook warnings remain in ReadingPage and ReportPage); browser checks covered all four public pages and signup at 1440px and 390px, plus the four pages at 320px. Confirmed policy navigation, section anchors, footer links, no horizontal overflow, no application page errors, and readable prices with checkout disabled when the API fails. Verified all five fallback offers against the backend catalog. Screenshots are in `output/playwright/`.

- [Paddle domain review](https://www.paddle.com/help/start/account-verification/what-is-domain-verification): public product description, pricing/deliverables, accessible terms/privacy/refunds, sole proprietor identity, and HTTPS.
- [Paddle Buyer Terms](https://www.paddle.com/legal/buyer-terms) and [Refund Policy](https://www.paddle.com/legal/refund-policy): reseller role and transaction/withdrawal rights.
- [ICO privacy-notice information](https://ico.org.uk/for-organisations/advice-for-small-organisations/getting-started-with-gdpr/data-protection-self-assessment/what-information-you-must-supply-under-the-gdpr/): identity, purposes/bases, recipients, retention, transfers, and individual rights where applicable.
- [European Commission unfair contract terms guidance](https://commission.europa.eu/law/law-topic/consumer-protection-law/consumer-contract-law/unfair-contract-terms-directive_en): plain terms and protections against unfair limitations for consumers.
