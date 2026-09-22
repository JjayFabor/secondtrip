# Homepage product walkthrough

This directory owns the scripted, client-side preview rendered by `src/app/page.tsx`. It uses
fictional local data only: no file picker, API utility, server action, or dashboard data hook may
be added here.

## Maintenance map

- `walkthrough-storyboard.ts` is the single timeline. Change scene titles, captions, order, and
  durations there.
- `walkthrough-data.ts` holds the fictional CSV, job pair, evidence, and cost inputs. Keep the
  same story and exact arithmetic consistent across every scene.
- `walkthrough-controller.ts` owns deterministic playback and direct navigation state.
- `product-walkthrough.tsx` owns visibility, reduced-motion behavior, the RAF lifecycle, and the
  real playback controls.
- `walkthrough-scenes.tsx` contains preview-only presentational scenes. Replace one scene by
  keeping its `WalkthroughSceneId` branch and swapping only that scene component. Its inert shell
  intentionally mirrors `components/dashboard/{dashboard-layout,sidebar,topbar}.tsx`; keep the
  shared logo, navigation vocabulary, selected-row treatment, and top-bar proportions aligned
  when the authenticated shell changes.
- `walkthrough.module.css` contains the small set of pause-aware entrance animations.

To disable the section, remove the `#product-preview` section and `ProductWalkthrough` import
from `src/app/page.tsx`. Do not hide it only with CSS, because the static explanatory copy should
also disappear from crawlers and assistive technology.

## Future product replacements

Every scene is a marketing preview, not a shipped application screen. As the product UI lands,
replace these previews with lightweight, sample-data renderings of the real components:

1. Import → `/app/imports/new`, `ImportColumnMapper`, and `ImportIssueTable`.
2. Queue → the review queue and `CandidateListRow`.
3. Evidence → `/app/rework/[id]`, `EvidencePanel`, `SignalRow`, and `ScoreBadge`.
4. Classification → `ReviewDecisionControl` and the append-only review flow.
5. Impact → dashboard metrics and the cost breakdown/report view.

Keep the homepage page component server-rendered. Any future interactivity belongs inside this
directory's narrow client boundary. Run `pnpm lint`, `pnpm typecheck`, and `pnpm build` after a
change, and verify mobile manual mode plus desktop autoplay/pause behavior in a real browser.
