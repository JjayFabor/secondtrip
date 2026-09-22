export type WalkthroughSceneId = "import" | "queue" | "evidence" | "classify" | "impact";

export interface WalkthroughSceneDefinition {
  id: WalkthroughSceneId;
  shortLabel: string;
  title: string;
  caption: string;
  durationMs: number;
}

export const WALKTHROUGH_SCENES: readonly WalkthroughSceneDefinition[] = [
  {
    id: "import",
    shortLabel: "Import",
    title: "Import job history",
    caption: "Start with the job history you already have.",
    durationMs: 6_000,
  },
  {
    id: "queue",
    shortLabel: "Find",
    title: "Find possible return visits",
    caption: "Find repeat visits that need a closer look.",
    durationMs: 6_000,
  },
  {
    id: "evidence",
    shortLabel: "Review",
    title: "Review the evidence",
    caption: "See why two visits may be connected.",
    durationMs: 9_000,
  },
  {
    id: "classify",
    shortLabel: "Classify",
    title: "Make the final classification",
    caption: "Review the evidence. Make the final classification.",
    durationMs: 6_000,
  },
  {
    id: "impact",
    shortLabel: "Impact",
    title: "Understand the impact",
    caption: "Understand recurring problems and estimated rework costs.",
    durationMs: 7_000,
  },
] as const;

export const WALKTHROUGH_DURATION_MS = WALKTHROUGH_SCENES.reduce(
  (total, scene) => total + scene.durationMs,
  0,
);

export function elapsedBeforeScene(sceneIndex: number) {
  return WALKTHROUGH_SCENES.slice(0, sceneIndex).reduce(
    (total, scene) => total + scene.durationMs,
    0,
  );
}
