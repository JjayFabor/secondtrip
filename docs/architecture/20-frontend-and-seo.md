# 20 — Frontend Architecture, SEO & AEO

Two products share one Next.js app: a **public site** whose job is to be found and to convert,
and an **authenticated application** whose job is to make a manager trust a score. They have
opposite requirements — static and indexable versus dynamic and private — and the route-group
split is what keeps them from contaminating each other.

---

## 1. Rendering strategy

| Route group | Strategy | Indexed |
| --- | --- | --- |
| `(marketing)` | Static generation; ISR (1 h) for anything data-backed | ✅ |
| `(marketing)/tools/*` | Static shell + client-side calculator | ✅ |
| `(auth)` | Static shell, client forms | ❌ `noindex` |
| `app/*` | Dynamic, server-rendered per request | ❌ `noindex` |

`app/*` sets `export const dynamic = "force-dynamic"` and emits
`X-Robots-Tag: noindex, nofollow`. Customer job data must never be cached at the edge or
rendered into a static artifact — and on Vercel, an accidentally-static authenticated page is
a page served to the wrong user.

---

## 2. Data fetching in the app

```
Server Component  →  forwards the session cookie  →  FastAPI  →  renders with data
Client Component  →  direct fetch (credentials: "include")     →  interactive updates
```

- **Initial page load is server-rendered** with data already present. The review queue should
  not flash a skeleton before its first row.
- **Interactions** (filtering, paging, polling an import) go straight from the browser to the
  API, skipping a pointless Next.js hop.
- `lib/api-client.ts` is one typed wrapper over `packages/contracts`, handling cookie
  forwarding, `X-Request-Id`, CSRF headers, and problem+json error mapping. Nothing calls
  `fetch` directly.
- Import progress polls `GET /imports/{id}` every 2 s while processing. Websockets would be a
  meaningful cost (a persistent connection per user on a $7 instance) for a marginal gain.

### Authorization in the UI

Role gates the *rendering* of controls, never the *access* to data. Every page's data comes
from an API call that independently authorizes. A user who forges a role client-side sees
buttons that return 403.

---

## 3. The two screens that matter

Everything else is a table.

### `/app/rework/[id]` — the evidence panel

This screen is the product. It has to make a manager believe a machine-generated claim about
their own business, in about eight seconds.

Requirements:

- The **full signal breakdown** from [07 §5](07-detection-engine.md), including non-matching
  and `NOT_EVALUABLE` rows. Showing what *didn't* match is what makes the score feel honest
  rather than sold.
- Both job records **side by side**, with the fields that drove the score highlighted.
- Score arithmetic shown, not just the total: `120 / 130 → 92`.
- AI analysis, when present, visually distinct and explicitly labelled a suggestion — never
  adjacent to the deterministic evidence in a way that implies equal standing.
- Decision controls (confirm / reject / uncertain + category + root cause) reachable without
  scrolling past the evidence.
- Keyboard navigation: `J`/`K` between candidates, `C`/`R` to confirm/reject. A manager working
  a queue of 200 will use these; requiring a mouse makes the queue feel like a chore.
- One API round trip ([15 §2](15-api-design.md)).

### `/app/imports/new` — the mapping wizard

Where users decide whether the product works. A four-step wizard with persistent state, so a
browser refresh mid-mapping does not lose the work:

```
Upload  →  Map columns  →  Review issues  →  Confirm
```

- Auto-suggested mappings shown **with confidence**, always confirmable.
- Live preview: the first five rows rendered as they will be imported, updating as mappings
  change. This catches a wrong date format before 60,000 rows are parsed with it.
- Unmapped columns listed explicitly with a "keep anyway" option, so nothing disappears
  silently.
- The issues step leads with counts and the top error codes, with remediation text per code,
  and a downloadable error CSV.
- Impact hints on optional fields: *"Mapping `equipment_serial` would materially improve
  detection accuracy"* — this is the highest-leverage copy in the product.

---

## 4. Public site architecture

```
/                                   Homepage
/features                           Product overview
/pricing                            Plans + entitlement comparison
/industries/hvac                    Primary landing page
/industries/plumbing
/industries/electrical
/industries/appliance-repair
/industries/pest-control
/resources                          Article index
/resources/[slug]                   MDX articles
/glossary/[term]                    Definition pages
/tools/callback-cost-calculator     Interactive, free, no signup
/tools/rework-cost-calculator
/compare/[slug]                     Comparison pages
/login /register
```

Industry pages are generated from a single content collection via `generateStaticParams`, so
adding a vertical is a content file, not a route. The same structure is what makes the
architecture's "no hard-coded HVAC assumptions" requirement visible in the marketing layer too.

---

## 5. SEO architecture

### Metadata

Every page exports `generateMetadata` producing title, description, canonical, OpenGraph, and
Twitter tags. Canonical URLs are built from `NEXT_PUBLIC_APP_URL` — **the domain is never
hard-coded**, which also means preview deployments do not emit canonicals pointing at
production.

`opengraph-image.tsx` per route group generates social cards at build time via `next/og`.

### Structured data (JSON-LD)

| Page | Schema |
| --- | --- |
| All | `Organization`, `WebSite` |
| `/` and `/features` | `SoftwareApplication` with `offers` |
| `/pricing` | `Product` + `Offer` per plan |
| `/resources/[slug]` | `Article` with `datePublished`, `author` |
| `/glossary/[term]` | `DefinedTerm` in a `DefinedTermSet` |
| `/tools/*` | `WebApplication` |
| Any FAQ block | `FAQPage` |
| Nested pages | `BreadcrumbList` |

Built by typed helpers in `lib/seo.ts`, not hand-written `<script>` blocks — malformed JSON-LD
is invisible in the browser and silently ignored by crawlers, which is exactly the kind of
error that persists for months.

### Technical

`sitemap.ts` (dynamic, includes every generated industry/resource/glossary route) ·
`robots.ts` (disallows `/app`, `/api`) · `noindex` on preview deployments via
`NEXT_PUBLIC_ENVIRONMENT` · static generation for LCP · `next/image` with explicit dimensions ·
`next/font` self-hosted (no render-blocking third-party font request) · a single H1 per page ·
internal linking from every article to its industry page and the calculators.

### Target queries

| Query | Page |
| --- | --- |
| HVAC callback software | `/industries/hvac` |
| HVAC callback tracking | `/industries/hvac` |
| field service callback tracking | `/features` |
| service callback software | `/` |
| how to reduce HVAC callbacks | `/resources/reduce-hvac-callbacks` |
| what is a callback rate in HVAC | `/glossary/callback-rate` |
| HVAC callback cost calculator | `/tools/callback-cost-calculator` |
| average HVAC callback rate | `/resources/hvac-callback-benchmarks` |
| warranty vs callback HVAC | `/glossary/warranty-work` |

**The calculators are the acquisition strategy, not a feature.** "HVAC callback cost
calculator" is a query with commercial intent and low competition, the tool is genuinely useful
without an account, and its output — *"your callbacks cost roughly $84,000/year"* — is the
exact argument for the product. It should require no signup, and it should end with an offer to
find the actual number from real data.

---

## 6. AEO — answer engine optimisation

Optimising for AI assistants and featured snippets, which answer rather than link.

1. **Answer first.** Every article and glossary page opens with a 40–60 word direct answer,
   before context or narrative. This is the extractable unit.
2. **Question-shaped headings.** `## What is a callback rate?` — matching real query phrasing,
   with the answer in the first paragraph beneath.
3. **FAQ blocks with `FAQPage` markup** on every substantive page.
4. **Definitions are self-contained.** A glossary entry must make sense quoted in isolation, so
   it never begins "As mentioned above…".
5. **Comparison tables** in real HTML `<table>` markup, not CSS grids. Extractors parse tables;
   they do not parse divs that look like tables.
6. **Concrete, sourced numbers.** "Industry callback rates typically run 3–8% of completed
   jobs" is quotable; "callbacks are expensive" is not. Cite sources — assistants favour
   attributable claims.
7. **`/llms.txt`** at the root: a plain-text summary of what SecondTrip is, who it serves, and
   the canonical URLs for key topics.
8. **No content behind JS.** All marketing content is in the server-rendered HTML. Many
   crawlers and most assistant fetchers do not execute JavaScript.

### Content plan (first ten pieces)

1. What is an HVAC callback? (definition + how to measure)
2. Average HVAC callback rates — benchmarks and how to compare
3. The true cost of an HVAC callback (calculator-linked)
4. Callback vs. warranty vs. rework: the distinctions that matter
5. How to track callbacks when your FSM doesn't
6. Seven root causes of HVAC callbacks and how to fix each
7. Reducing callbacks without slowing technicians down
8. What your job history reveals about your rework rate
9. How to run a callback review meeting
10. Callback tracking for plumbing contractors

Pieces 1–4 target definitional queries (AEO). 5–9 target problem-aware buyers. Each links to a
calculator and its industry page.

---

## 7. Design system

The full visual language — tokens, palette, typography, component inventory, and the
score-band/review-outcome color mapping — is specified in
[22-design-system.md](22-design-system.md) and governs both the marketing site and the app.
This section covers only the app-surface behaviors that are about interaction and density
rather than visual tokens:

- **Density is a feature.** The review queue should show 15–20 rows without scrolling. Generous
  marketing-site spacing is wrong here.
- **Tables are first-class**: sortable headers, sticky header row, keyboard navigation,
  consistent column alignment (numbers right-aligned, tabular figures).
- **Money and dates always formatted in the organization's currency and timezone**, never the
  browser's. A US manager reviewing a job at 11pm must not see tomorrow's date.
- Mobile: the app is usable at 400px but optimised for desktop — this is a work tool used at a
  desk. The marketing site is mobile-first.
- WCAG 2.1 AA: 4.5:1 contrast, visible focus rings, full keyboard operability, labelled form
  controls, `aria-live` on async status changes (import progress, save confirmations).

---

## 8. Performance

| Target | Value |
| --- | --- |
| Marketing LCP | < 1.5 s |
| Marketing CLS | < 0.1 |
| App time-to-interactive | < 2 s on a warm API |
| Review queue render (50 rows) | < 300 ms after data |
| API p95 (list endpoints) | < 300 ms |

Techniques: static generation for marketing · server components by default (client components
only where interaction demands) · route-level code splitting · `next/image` · self-hosted fonts
· no analytics script on `/app` · virtualized rendering only if a table genuinely exceeds ~200
rows (cursor pagination means it usually will not).

Note the Render cold-start caveat from [01 §6](01-system-architecture.md): the first request
after idle will miss these targets. The Starter instance avoids sleep-on-idle, which is most of
why it is worth $7.
