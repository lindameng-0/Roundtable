# Roundtable: the reading room

Roundtable helps a writer understand how a story lands with different AI readers. Its identity should belong to that exchange: a manuscript at the centre, perspectives around it, and useful observations in the margins.

## Visual system

- Parchment `#F7F5EE`: the quiet page background.
- Aubergine `#493449`: primary actions, the brand mark, and display accents.
- Ink `#302D32`: readable text.
- Moss `#526653`: completion and constructive feedback.
- Lilac `#E9E1EC`: highlighted passages and selected states.
- Ochre `#B18B48`: a small accent for questions and reading in progress.

Instrument Serif gives the masthead and headings a recognisable book-jacket character. DM Sans handles navigation and controls; Georgia provides a familiar, readable manuscript face. The fonts have system fallbacks.

## Layout

The public homepage pairs a left-aligned invitation with a working, explicitly labelled feedback example. A circular table with five open book shapes is the brand device. Auth uses that same light surface and identity. Application pages put consistent navigation above a spacious, focused work area.

```text
Public:    [Roundtable]                  [How it works] [Plans] [Sign in]
           [An invitation to writers]   [Manuscript + reader response]
           [Three steps from draft to revision]

Workspace: [Roundtable] [Manuscripts] [New manuscript]     [Credits] [Account]
           [Page title and one clear primary action]
           [Manuscripts / setup / reading / report]

Reading:   [Shared navigation]
           [Title] [Reading status] [Editor report]
           [Manuscript, wide] [Reader responses]
Mobile:    [Shared compact navigation]
           [Manuscript | Reader responses] (one panel at a time)
```

## Review against the brief

Cream and serif alone would reproduce the existing generic aesthetic. Use aubergine instead of clay, a bespoke circular book mark instead of a library icon, and an interactive manuscript example instead of decorative cards. Avoid ornamental numbering, all-caps labels, faux testimonials, or claims of guaranteed editorial quality. The product's writing and feedback carry the visual interest.

Keep keyboard focus visible, controls labelled, useful contrast, comfortable touch targets, and reduced-motion support. Keep the manuscript readable without horizontal scrolling. Preserve billing and authentication behaviour while improving their presentation. Failures need an explanation and a recovery action, not an endless spinner.

## Implementation and verification

Shared brand, navigation, auth layout, reader avatars, and accessible confirmation dialogs now connect the public homepage, account pages, manuscript library, three-step setup, reading workspace, and billing. The homepage example is explicitly illustrative. The manuscript text uses Georgia, with display type reserved for the surrounding interface.

The UI review also found and fixed two existing blockers: the dashboard never fetched its manuscript list, and `manuscriptRequestConfig` referenced an undefined variable. Failed manuscript/report loads now have a recoverable state. Clicking annotated prose opens its feedback, and the mobile reader can switch between text and notes.

Browser verification used local fixtures with all API requests intercepted. It covered 33 page/viewport combinations at 320, 768, and 1440 pixels, plus the setup journey at 390 pixels; none overflowed horizontally. Signup, verification resend, reset-email request, login/logout, search, empty/error/retry states, the three setup steps, report navigation, comment opening, and confirmation cancellation were exercised. No real payments or AI calls were made. Main signed-in checks reported no JavaScript runtime errors.

Production build and undefined-variable lint passed. The build still reports the existing reading/report effect-dependency warnings. Actual Paddle checkout and email delivery require the external configuration described in `BILLING-SETUP.md`; browser fixtures do not verify those services.

Local visual artifacts are in `output/playwright/` (ignored by Git). No deployment was performed.
