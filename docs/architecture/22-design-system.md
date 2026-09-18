# 22 — Design System

**Status:** binding specification, implementation not started.
**Scope:** the marketing site and the authenticated app — one visual language, not two.

This document is the source of truth for every color, type size, spacing value, radius,
shadow, and component used in the frontend. A PR that introduces any of those outside this
spec is a defect, not a style preference. Where this document and
[20-frontend-and-seo.md](20-frontend-and-seo.md) overlap, this document governs; 20 covers
rendering strategy, data fetching, SEO/AEO and performance, which are unaffected by the visual
language.

---

## 0. "Shared" means one app, not two packages

**Decision, stated up front because it resolves the only real ambiguity in scope:** marketing
and dashboard are route groups inside **one** Next.js application
([16-repository-structure.md](16-repository-structure.md)). Sharing tokens and components
between them does not require a published package, a second build target, or a
`packages/ui` workspace — it requires only that both route groups import from the same
`src/styles/tokens.css` and the same `src/components/ui/`.

**Rejected: a separate `packages/ui` design-system package.** The monorepo already made a
deliberate call to keep `packages/` to one member (`contracts/`) because package proliferation
is the specific failure mode a solo-maintained monorepo falls into
([16 §1](16-repository-structure.md)). A second consumer would justify extraction; there is
only one Next.js app, so there is only one consumer. If a second frontend ever exists (a native
app, an embeddable widget), extraction is a mechanical move at that point — the components
below are written with no route-group-specific imports, so nothing here blocks it.

---

## 1. Brand

| | |
| --- | --- |
| Name | **SecondTrip** |
| Descriptor | Callback & Rework Analytics |
| Primary positioning | Find the patterns behind costly repeat visits. |
| Supporting positioning | Review your job history, investigate possible callbacks, and understand rework patterns without replacing your existing CRM. |
| Personality | Clear, practical, analytical, dependable, calm, observant, professional |

AI is a capability the product uses, not the brand's subject. It is named when explaining a
specific mechanism (e.g. "SecondTrip compares job notes for similar wording") and never used
as the headline claim. This is a direct extension of
[07-detection-engine.md ADR / §5](07-detection-engine.md): the deterministic score is the
credible artifact; AI adds a narrative on top of it. The visual language should make the same
argument the architecture makes — evidence first, AI labelled as a suggestion, human judgement
visibly final.

---

## 2. The anti-pattern checklist

Treat this as a PR review gate, not a mood board. Any of the following in a diff is a revert,
not a nitpick:

Gradients as decoration · glow/neon effects · glassmorphism · background blobs/orbs · cards
nested inside cards · shadows on ordinary content cards · floating decorative elements ·
sparkle/AI-brain/robot iconography · a fake chat interface · an oversized empty hero · pill
buttons on non-pill components · a different background color per marketing section ·
oversized display type used purely for impact · animation with no functional purpose · an icon
beside every label · gradient text · the purple/blue "AI startup" palette · a chart added for
visual balance rather than to answer a question · fabricated metrics, logos, or testimonials ·
generic SaaS stock illustration.

**Before shipping any screen, ask two questions:**

1. Does this element help the user understand the product, navigate, decide, or act? If not,
   remove it.
2. Would this be at home in twenty other AI-generated SaaS landing pages? If yes, make it more
   specific to SecondTrip or cut it.

The product's visual identity comes from its own subject matter — connected visits, timelines,
recurring patterns, evidence — not from generic technology imagery.

---

## 3. Color

### 3.1 Palette

| Token | Hex | Role |
| --- | --- | --- |
| Deep Petrol | `#12343B` | Brand, dark surfaces, headings-as-brand-moment |
| Primary Teal | `#0B7A75` | Primary action, links, focus |
| Warm Apricot | `#F2B36D` | Accent — attention/warning fill, **background only** |
| Soft Canvas | `#F6F8F7` | App/page background |
| White | `#FFFFFF` | Cards, panels, inputs |
| Ink | `#172B2F` | Primary text |
| Muted Slate | `#607176` | Secondary text, ≥13px only |
| Soft Border | `#D8E2E1` | Decorative dividers only — see §3.3 |

Target mix across any screen: **70–80% neutral surfaces, 15–20% petrol/teal, under 5%
apricot.** Apricot is a highlight, not a UI color — if a screen has more than one or two
apricot elements in view, that is a signal to reconsider, not a green light to add more accent.

### 3.2 Semantic tokens

Raw hex values are never referenced directly from components. Every color is a CSS custom
property in `src/styles/tokens.css`, consumed through the Tailwind theme:

```css
:root {
  /* surfaces */
  --surface-canvas:   #F6F8F7;
  --surface-raised:   #FFFFFF;
  --surface-inverse:  #12343B;

  /* borders */
  --border-subtle:    #D8E2E1;   /* decorative dividers only */
  --border-strong:    #7E9490;   /* interactive boundaries — inputs, tables, selects */

  /* text */
  --text-primary:     #172B2F;
  --text-secondary:   #607176;   /* ≥13px only */
  --text-inverse:      #FFFFFF;
  --text-on-accent:   #172B2F;   /* required on any apricot fill — see §3.3 */

  /* brand */
  --brand-primary:        #0B7A75;
  --brand-primary-hover:  color-mix(in srgb, var(--brand-primary) 88%, black);
  --brand-primary-active: color-mix(in srgb, var(--brand-primary) 78%, black);
  --brand-deep:        #12343B;
  --accent:            #F2B36D;
  --focus-ring:        var(--brand-primary);   /* never --accent — see §3.3 */

  /* status */
  --success:      #3F7D58;
  --warning:      var(--accent);
  --danger:       #B54B3F;
  --success-bg:   color-mix(in srgb, var(--success) 12%, white);
  --warning-bg:   color-mix(in srgb, var(--warning) 16%, white);
  --danger-bg:    color-mix(in srgb, var(--danger) 12%, white);
}
```

`color-mix()` derives hover/active/tint shades from the base tokens instead of hand-picked
hex steps, so every derived shade stays mathematically consistent if a base color ever
changes, and there is one fewer set of values to keep in sync.

Warning deliberately reuses `--accent`. Amber-for-attention is a low-surprise, standard
mapping, and letting the brand accent double as the warning semantic keeps the palette small —
consistent with the brief's minimalism goal. The one discipline this requires: never place a
decorative apricot element directly beside a warning badge on the same screen, where the two
meanings could be misread as related.

### 3.3 Accessibility findings specific to this palette

Verified against the WCAG relative-luminance formula by hand; re-check with contrast tooling
at implementation time before shipping, and treat the figures below as "confirmed in range,"
not pixel-exact.

| Pair | Approx. contrast | Verdict |
| --- | --- | --- |
| Ink on White | ~14.8:1 | Body text, any size |
| Deep Petrol on White | ~13.3:1 | Headings, secondary-button text |
| Teal on White (text/links) | ~5.2:1 | Passes AA at any size, not just large text |
| White on Teal (button label) | ~5.2:1 | Passes AA |
| Muted Slate on White | ~5.1:1 | Passes AA — **restrict to ≥13px**, don't use for primary body copy |
| Success (`#3F7D58`) on White | ~4.9:1 | Usable as text/icon, not just a fill |
| Danger (`#B54B3F`) on White | ~5.2:1 | Usable as text/icon, not just a fill |
| **Ink on Apricot fill** | ~8.1:1 | The only acceptable text color on an apricot background |
| **White on Apricot fill** | ~1.8:1 | **Fails.** Apricot must never carry white text |
| **Soft Border on White** | ~1.3:1 | **Fails** the 3:1 non-text contrast target (WCAG 1.4.11) for anything that must read as a boundary |
| Border Strong (`#7E9490`) on White | ~3.2:1 | Meets the 3:1 target — use for input/select/table boundaries |
| Apricot alone on White (as a border/ring) | ~1.8:1 | **Fails** — apricot cannot be a stand-alone focus indicator |

Three concrete rules follow directly from this table, and each is easy to get wrong by
copying the raw brief without checking it:

1. **`--border-subtle` (Soft Border) is decorative only** — a divider inside a card that
   already has its own edge, or a rule between rows on a surface that differs from the
   background behind it. Anything that must be *perceivable as a boundary on its own* —
   an input's outline, a table's row separators when there's no alternating fill, a select's
   edge — uses `--border-strong`.
2. **Apricot fills always pair with `--text-on-accent` (Ink), never white.**
3. **Focus rings use `--focus-ring` (Teal), never apricot.** Apricot alone doesn't clear the
   non-text contrast bar against a white or canvas background.

### 3.4 Score confidence vs. review outcome — two axes, deliberately not one palette

The product has two independent things to color, and conflating them is the single easiest
way to accidentally imply the machine is right:

| Axis | What it means | What it must never imply |
| --- | --- | --- |
| **Score band** (`low` / `medium` / `high`) | How strong the deterministic evidence is | Whether the pair *is* a real callback |
| **Review outcome** (`confirmed` / `rejected` / `uncertain`) | What a human decided | — this is the actual truth; nothing else is |

**Score bands use brand intensity, not alarm colors** — a high score is a strong signal, not
a bad outcome, and red would say the opposite of what's true:

| Band | Treatment |
| --- | --- |
| `low` | `--border-strong` outline badge, `--text-secondary` label — barely emphasized |
| `medium` | `--warning-bg` fill, `--text-primary` label — worth a look |
| `high` | `--brand-primary` solid fill, `--text-inverse` label — strong signal |

**Review outcomes use the status tokens, and rejection is explicitly not styled as an
error:**

| Outcome | Treatment |
| --- | --- |
| `confirmed` | `--success` |
| `rejected` | `--text-secondary` / neutral — **not `--danger`.** Rejecting a flagged pair is a normal, healthy outcome of human review, not a failure |
| `uncertain` | `--warning` |

This mapping is a direct visual expression of
[07-detection-engine.md §7](07-detection-engine.md): "AI output is not authoritative... the
manager confirms or rejects." A UI that colors a rejected candidate red is quietly arguing the
opposite of the product's own premise.

---

## 4. Typography

Single family: **Manrope**, loaded via `next/font/google` and self-hosted at build time — no
runtime request to Google Fonts, and no `fonts.googleapis.com` CSP allowance is needed as a
result (tighter than the general CSP guidance in
[11-security-threat-model.md §7](11-security-threat-model.md), which permits it for cases that
don't self-host).

| Role | Size | Weight | Line height |
| --- | --- | --- | --- |
| Hero | 48–60px / 3–3.75rem | 650–700 | 1.1 |
| H1 | 36–44px / 2.25–2.75rem | 650–700 | 1.15 |
| H2 | 28–32px / 1.75–2rem | 600–700 | 1.2 |
| H3 | 20–24px / 1.25–1.5rem | 600 | 1.3 |
| Body | 15–16px | 400–500 | 1.6 |
| Small | 13–14px | 400–500 | 1.5 |
| Button | 14–15px | 600 | 1 |
| Dashboard metric | 24–32px | 600 | 1.1 |

Rules: not every heading is bold — H3 and below stay at 600, weight increases with size, not
with emphasis-seeking. Marketing paragraph measure is capped at ~65–70 characters (`max-width:
34rem` at body size). Dashboard metrics and any money value use `font-variant-numeric:
tabular-nums`, so a column of figures aligns — this is the same "numbers must be trustworthy at
a glance" principle behind money being formatted in the org's currency and timezone
([20 §7](20-frontend-and-seo.md)).

---

## 5. Spacing, radius, borders, shadows

### Spacing — reuse Tailwind's default scale, add nothing

The brief's requested scale (4/8/12/16/24/32/48/64/96) is **exactly** Tailwind's default
spacing scale at `1/2/3/4/6/8/12/16/24`. No custom spacing config is needed. This is worth
stating explicitly so nobody "helpfully" adds a redundant spacing token set later — the
project's own bias throughout is not adding infrastructure a default already covers
([00 §5](00-overview-and-decisions.md)).

### Radius

| Token | Value | Used by |
| --- | --- | --- |
| `--radius-control` | 8px | Buttons, inputs, selects |
| `--radius-card` | 12px | Cards, panels |
| `--radius-modal` | 12px | Dialogs |
| `--radius-pill` | 9999px | Badges, tags, chips, filters — genuine pill components only |

Everything else is square. A card is not a pill; a badge is not a card.

### Borders

Default border is `1px solid var(--border-subtle)` for decorative use,
`1px solid var(--border-strong)` for anything functioning as a boundary (§3.3). Borders are the
primary separation technique — prefer a border over a shadow whenever a border communicates the
same thing.

### Shadows — exactly two, used sparingly

```css
--shadow-sm: 0 2px 8px rgba(23, 43, 47, 0.08);    /* dropdowns, popovers, tooltips */
--shadow-md: 0 8px 24px rgba(23, 43, 47, 0.12);   /* dialogs, modals */
```

**No shadow on an ordinary content card.** A card sitting flat on the page uses a border, not
elevation — it isn't elevated above anything. Shadow means "this is temporarily floating above
the page," which is only true for a dropdown, popover, or modal. This single rule is the most
common tell that separates a considered product UI from a generated one.

---

## 6. Iconography

**Library: `lucide-react`** — a single, consistent outline set, tree-shakeable, MIT-licensed,
matches the "one icon library" requirement without any brand baggage. (The set includes
things like a sparkle glyph; we simply never use it — see §2.)

| Context | Size | Stroke |
| --- | --- | --- |
| Inline with 13–14px text | 16px | 1.75 |
| Buttons, nav items | 18px | 1.75 |
| Standalone / empty-state | 20px | 1.75 |

An icon earns its place for status, an action's affordance, or navigation — not as decoration
next to a label that's already clear on its own. Default to no icon; add one only when it
changes how quickly the element is understood.

---

## 7. Logo

Shipped. The **open-loop S** mark — a geometric S formed from two returning strokes ending in
an arrow, representing a repeated trip being identified and interrupted — in a rounded dark
badge, paired with a "SecondTrip" wordmark.

```tsx
<Logo variant="horizontal" />   // icon + wordmark, for light surfaces — the default
<Logo variant="icon" />         // mark only — compact contexts, favicon source
<Logo variant="mono" />         // single-color wordmark, for constrained/print contexts
<Logo variant="dark" />         // self-contained lockup for dark/inverse surfaces — it paints
                                 // its own card, so it takes no wrapper (unlike the other three)
```

Source assets live in `frontend/public/brand/` (the four SVGs, kept as a reference/press-kit
copy); the same markup is inlined directly in `frontend/src/components/brand/logo.tsx` so the
mark renders with no extra network request. `frontend/src/app/icon.svg` and `apple-icon.png`
(rasterized from the icon mark, 180×180) wire the favicon via Next.js's file convention.

### The mark uses the UI palette — not its own colors

The mark shipped first with independent brand colors (navy `#0B1220`, indigo `#4F46E5`/
`#818CF8`) — deliberately documented as separate from the UI palette at the time (PLAN.md
D37). A side-by-side comparison of the two in context (the mark next to a teal button in the
nav) made the mismatch obvious enough to revisit: indigo sat close to exactly the "purple/blue
AI-startup palette" §2's anti-pattern checklist warns against, and it never matched anything
else on the page.

**Current state:** recolored to match (PLAN.md D38, superseding D37). The mark's dark ground
is `--brand-deep` (`#12343B`); its accent dot/stroke is `--brand-primary` (`#0B7A75`). The
`dark` lockup's "Trip" text uses `#6DAFAC` — a lighter tint of teal derived the same way
`tokens.css` derives every other hover/tint shade (`color-mix(in srgb, teal 60%, white 40%)`),
for contrast against its own petrol card. The mark is still drawn with fixed hex values rather
than CSS variables (it's a static SVG, inlined for zero extra network requests — see §15), but
those values are now the *same* colors as the token palette, kept in sync by hand rather than
by a shared reference. If `--brand-deep` or `--brand-primary` ever change, the four SVGs in
`frontend/public/brand/` and the inline copies in `logo.tsx` need updating alongside them —
there's no single source of truth linking the two.

**Never**, for anything other than this one shipped mark: airplane, location pin, truck,
wrench, refresh/circular-arrow, infinity symbol, or sparkle — the ban list in §2 still governs
every other icon in the product.

---

## 8. Motion

| Token | Value | Used for |
| --- | --- | --- |
| `--duration-fast` | 150ms | Hover states |
| `--duration-base` | 200ms | Dropdown/modal enter-exit |
| `--easing-out` | `cubic-bezier(0.16, 1, 0.3, 1)` | Entrances |

Allowed: hover transitions, dropdown/modal transitions, skeleton shimmer. **Not allowed:**
scroll-triggered reveals, parallax, floating idle animation, text flying in, animated
gradients. The application should read as fast, not as animated — motion communicates a state
change, never a mood.

---

## 9. Component inventory

### Shared primitives — `src/components/ui/` — used by marketing and dashboard alike

Button (primary / secondary / destructive / ghost) · Input · Textarea · Select · Checkbox ·
Radio · Switch · Badge/Tag/Chip (uses `--radius-pill`) · Card · Table (sortable header, sticky
head) · Dialog · Dropdown Menu · Tabs · Accordion · Tooltip · Popover · Skeleton · Separator.

Built on Radix primitives for behavior/accessibility, vendored and styled with our tokens —
not installed as a themeable third-party kit — per the existing repository decision
([16 §2](16-repository-structure.md)).

Button variants, concretely:

| Variant | Background | Text | Border |
| --- | --- | --- | --- |
| Primary | `--brand-primary` (hover/active via `color-mix`) | `--text-inverse` | none |
| Secondary | transparent / `--surface-raised` | `--brand-deep` | `--border-strong` |
| Destructive | `--danger` | `--text-inverse` | none |
| Ghost | transparent | `--text-primary` | none, `--surface-canvas` on hover |

Not pill-shaped unless the component genuinely is a pill (a filter chip, a tag) — see §5.

### Dashboard-specific — `src/components/dashboard/`

`Sidebar`, `TopBar`, `MetricPanel` (compact — a number, a label, one line of context; never a
large decorative KPI tile), `ScoreBadge` (renders a score band per §3.4), `SignalRow` (renders
one evidence line — matched / not matched / not evaluable, per
[07-detection-engine.md §5](07-detection-engine.md); this is the component that must visually
distinguish "checked, didn't match" from "couldn't check" — a dash, not a red ✗, for
`not_evaluable`), `EvidencePanel` (composes `SignalRow`s + the score arithmetic line + both job
records), `CandidateListRow` (the review queue row — `top_signals` chips per
[15-api-design.md §3](15-api-design.md)), `ReviewDecisionControl`, `ImportColumnMapper`,
`ImportIssueTable`, `EmptyState` (a small icon, one line, one action — never an illustration).

### Marketing-specific — `src/components/marketing/`

`Nav`, `Hero`, `ProductPreviewCard` (the callback-detection screenshot-style block from §10),
`StepItem` (How It Works — typographic, not a gradient card), `CapabilityCard`,
`PricingCard`, `FAQAccordion` (reuses the shared `Accordion`), `Footer`.

### Charts — `src/components/charts/`

Thin, pre-themed wrappers over **Recharts** (SVG-based — accessible and stylable through CSS,
unlike a canvas-rendered library): `LineChart`, `HorizontalBarChart`, `RankedList` (a table,
used in preference to a chart per §11). Series colors are drawn only from `--brand-primary`,
`--accent`, and neutral grays — never a new hue introduced just for a chart. Exact mark specs,
tooltip and legend behavior are decided at implementation time using the `dataviz` skill; this
document fixes only the allowed chart vocabulary and palette.

---

## 10. Marketing layout

**Nav:** logo · Product · How It Works · Pricing · FAQ · Sign In · **Try SecondTrip** (primary
button). No mega menu.

**Hero:** controlled two-column layout on desktop, not a full-viewport hero.

- Left: eyebrow (`CALLBACK & REWORK ANALYTICS`, small caps, `--text-secondary`) · headline
  ("Find the patterns behind costly repeat visits.") · supporting paragraph (one sentence,
  capped measure) · primary CTA ("Try SecondTrip") · secondary CTA ("View Sample Report").
- Right: a real product-interface preview, not abstract artwork —

  ```text
  Possible callback detected

  Original Visit  →  Return Visit

  Reason: Similar issue identified in job notes

  Estimated rework cost: $XXX
  ```

  This mirrors the actual `EvidencePanel` component, built with **clearly marked sample
  data** — the same component the dashboard uses, not a bespoke marketing mockup, so what a
  visitor sees is what they'll get. No invented customer metric is used to make it look more
  impressive than the real product.

**Section flow (homepage, kept short):** Hero → Problem (one short paragraph — repeat visits
are visible, patterns are buried across notes/technicians/categories) → How It Works (three
steps: Import / Analyze / Review, expressed with typography and thin dividers, not gradient
cards) → Product Preview (the strongest visual section — a real dashboard/report view) →
Capabilities (four short entries: Callback Detection, Pattern Analysis, Rework Cost, Evidence
Review) → Existing Workflow ("Keep your CRM. Add better visibility.") → Pricing (no
manipulative hierarchy; a "Recommended" label only if a plan genuinely is) → FAQ (accordion) →
short final CTA → Footer (Product, Pricing, Privacy, Terms, Contact; optional "Built by Jjay
Fabor").

---

## 11. Dashboard layout

Desktop: sidebar **224–240px** fixed · optional compact top bar (search/org switcher/account) ·
content area with `--surface-canvas` background and `--surface-raised` cards.

Sidebar sections, text labels with restrained icons, nothing overloaded:

```text
SecondTrip
  Overview
  Visits
  Callbacks
  Patterns
  Reports
  Imports
────────────
  Settings
  Help
  Account
```

(This maps onto the route structure in [16 §3](16-repository-structure.md) — "Callbacks" is
`/app/rework`, the primary landing surface.)

**Overview:** header + one-line supporting text · compact filter row (date range, location,
service, technician) · metrics as compact panels, not large KPI tiles:

```text
Possible Callbacks
24
3.8% of analyzed jobs
```

**Data visualization** — charts answer a specific operational question or they don't ship:
callbacks over time (line), callbacks by service (horizontal bar), estimated rework cost over
time (line/bar), most common repeat issues (ranked list — a table, not a chart, per §9).
Never: donut (unless a part-of-whole question genuinely demands it), 3D, gauges, a chart that
restates a number already shown clearly elsewhere on the same screen.

**Callback investigation** (`/app/rework/[id]`) — Original Visit / Return Visit / Why
SecondTrip Flagged It / Classification, using `EvidencePanel` and `SignalRow` from §9. The
classification control never visually implies the system is authoritative — see §3.4.

**Patterns** — answers "which services produce the most repeat visits," "which issues recur in
notes," "is the trend rising or falling," "which categories cost the most in rework."
Technician data is shown with context (job volume, evidence), never as a bare leaderboard —
this mirrors the minimum-volume gating already specified in
[12-privacy-and-data-lifecycle.md §7](12-privacy-and-data-lifecycle.md).

**Imports** — Upload → Map columns → Validate → Import → Analyze, mirroring
[06-csv-ingestion.md §1](06-csv-ingestion.md). Validation errors are shown clearly and per-row,
never summarized away. A sample-format download is offered where supported.

**Empty states** — one small icon (18–20px), one sentence, one action:

```text
No job history yet
Import your job history to start identifying repeat visits and rework patterns.
[Import Jobs]
```

No illustration.

**Loading / long-running work** — skeletons for layout-shaped loads; for anything that takes
real time (an import processing, detection running), state what's happening, not a spinner
alone:

```text
Analyzing 1,284 jobs
Checking visit relationships and recurring job-note patterns.
```

No fake typing effect, no AI-style "thinking" animation.

---

## 12. Copywriting

| Prefer | Avoid |
| --- | --- |
| Possible callback | AI-powered callback intelligence |
| Why this was flagged | AI reasoning engine |
| Analyze job history | Unlock actionable AI insights |
| Recurring issue | Intelligent anomaly |

Banned regardless of context: *revolutionize, supercharge, game-changing, next-generation,
cutting-edge, unlock the power of, seamless, AI-powered insights, transform your business.*

Product copy mirrors the domain's own vocabulary rather than inventing flashier synonyms —
`rework_categories` and `root_causes` are plain labels
([04-data-model.md §7](04-data-model.md): `confirmed_callback`, `warranty`, `misdiagnosis`,
…), and UI copy should read the same way. Be specific instead of superlative: a number and a
unit beat an adjective.

**Never fabricate:** customer logos, testimonials, review counts, jobs-analyzed counts,
savings figures, accuracy percentages, revenue, integrations, or certifications. Where real
data doesn't exist yet, use data that is clearly marked as sample/demo — the hero preview in
§10 is the template for how to do this honestly.

---

## 13. Accessibility

Target **WCAG 2.1 AA**: normal text ≥ 4.5:1 (§3.3 has the specific pairs already verified for
this palette) · visible focus rings using `--focus-ring`, never color alone · semantic HTML
first, ARIA only where semantic HTML can't express the state · labelled form controls with
visible, associated labels · accessible, specific error messages · full keyboard operability,
including the evidence-panel shortcuts already specified in
[20-frontend-and-seo.md §3](20-frontend-and-seo.md) (`J`/`K` between candidates, `C`/`R` to
confirm/reject) · minimum practical touch target ~40px on interactive controls.

Status is never color-only: `ScoreBadge` and review-outcome indicators always carry a label or
icon alongside the color (§3.4).

---

## 14. Responsive rules

Marketing: fully responsive, mobile-first.

Dashboard: desktop-first, fully usable at tablet width, and functional (not merely shrunk) on
mobile — sidebar collapses to a drawer below 1024px; tables scroll horizontally inside their
own contained wrapper rather than reflowing into an unreadable stack; filters collapse into a
single "Filters" control that opens a sheet; primary actions (confirm/reject, import) stay
reachable without hunting.

---

## 15. Where tokens live in code

| Category | File |
| --- | --- |
| Color, radius, shadow, motion custom properties, and the Tailwind theme mapping | `frontend/src/styles/tokens.css` (`@theme` block — Tailwind v4's CSS-native theming; no `tailwind.config.ts` needed for token mapping) |
| Font loading | `frontend/src/app/layout.tsx` (`next/font/google`) |
| Shared primitives | `frontend/src/components/ui/` |
| Charts | `frontend/src/components/charts/` |
| Brand/logo | `frontend/src/components/brand/` (component), `frontend/public/brand/` (source SVGs), `frontend/src/app/icon.svg` + `apple-icon.png` (favicon) |
| Marketing composites | `frontend/src/components/marketing/` |
| Dashboard composites | `frontend/src/components/dashboard/` |

Full tree in [16-repository-structure.md §3](16-repository-structure.md). Spacing uses
Tailwind's default scale unmodified (§5) — there is no `--spacing-*` override in the `@theme`
block.
