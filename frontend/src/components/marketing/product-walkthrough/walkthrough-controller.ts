import { WALKTHROUGH_SCENES } from "./walkthrough-storyboard";

export type PlaybackStatus = "idle" | "playing" | "paused" | "finished";

export interface WalkthroughState {
  sceneIndex: number;
  sceneElapsedMs: number;
  status: PlaybackStatus;
  autoplayConsumed: boolean;
  userInteracted: boolean;
}

export type WalkthroughAction =
  | { type: "AUTOPLAY" }
  | { type: "PLAY" }
  | { type: "PAUSE" }
  | { type: "REPLAY"; reducedMotion: boolean }
  | { type: "GO_TO"; sceneIndex: number }
  | { type: "TICK"; deltaMs: number };

export const INITIAL_WALKTHROUGH_STATE: WalkthroughState = {
  sceneIndex: 0,
  sceneElapsedMs: 0,
  status: "idle",
  autoplayConsumed: false,
  userInteracted: false,
};

export function walkthroughReducer(
  state: WalkthroughState,
  action: WalkthroughAction,
): WalkthroughState {
  switch (action.type) {
    case "AUTOPLAY":
      if (state.autoplayConsumed || state.userInteracted || state.status !== "idle") return state;
      return { ...state, status: "playing", autoplayConsumed: true };
    case "PLAY":
      if (state.status === "finished") {
        return {
          ...state,
          sceneIndex: 0,
          sceneElapsedMs: 0,
          status: "playing",
          autoplayConsumed: true,
          userInteracted: true,
        };
      }
      return {
        ...state,
        sceneElapsedMs:
          state.sceneElapsedMs >= WALKTHROUGH_SCENES[state.sceneIndex].durationMs
            ? 0
            : state.sceneElapsedMs,
        status: "playing",
        autoplayConsumed: true,
        userInteracted: true,
      };
    case "PAUSE":
      return { ...state, status: "paused", userInteracted: true };
    case "REPLAY":
      return {
        ...state,
        sceneIndex: 0,
        sceneElapsedMs: action.reducedMotion ? WALKTHROUGH_SCENES[0].durationMs : 0,
        status: action.reducedMotion ? "paused" : "playing",
        autoplayConsumed: true,
        userInteracted: true,
      };
    case "GO_TO": {
      const sceneIndex = Math.min(Math.max(action.sceneIndex, 0), WALKTHROUGH_SCENES.length - 1);
      return {
        ...state,
        sceneIndex,
        sceneElapsedMs: WALKTHROUGH_SCENES[sceneIndex].durationMs,
        status: "paused",
        autoplayConsumed: true,
        userInteracted: true,
      };
    }
    case "TICK": {
      if (state.status !== "playing") return state;

      let sceneIndex = state.sceneIndex;
      let elapsed = state.sceneElapsedMs + Math.max(action.deltaMs, 0);

      while (elapsed >= WALKTHROUGH_SCENES[sceneIndex].durationMs) {
        elapsed -= WALKTHROUGH_SCENES[sceneIndex].durationMs;
        if (sceneIndex === WALKTHROUGH_SCENES.length - 1) {
          return {
            ...state,
            sceneElapsedMs: WALKTHROUGH_SCENES[sceneIndex].durationMs,
            status: "finished",
          };
        }
        sceneIndex += 1;
      }

      return { ...state, sceneIndex, sceneElapsedMs: elapsed };
    }
  }
}
