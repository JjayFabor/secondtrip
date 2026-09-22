"use client";

import { useEffect, useMemo, useReducer, useRef, useState } from "react";
import {
  ChevronLeft,
  ChevronRight,
  Pause,
  Play,
  RotateCcw,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

import styles from "./walkthrough.module.css";
import {
  INITIAL_WALKTHROUGH_STATE,
  walkthroughReducer,
} from "./walkthrough-controller";
import { WalkthroughWorkspace } from "./walkthrough-scenes";
import {
  elapsedBeforeScene,
  WALKTHROUGH_DURATION_MS,
  WALKTHROUGH_SCENES,
} from "./walkthrough-storyboard";

export function ProductWalkthrough() {
  const [state, dispatch] = useReducer(walkthroughReducer, INITIAL_WALKTHROUGH_STATE);
  const [isInView, setIsInView] = useState(false);
  const [isDocumentVisible, setIsDocumentVisible] = useState(true);
  const [isDesktopPlayback, setIsDesktopPlayback] = useState(false);
  const [prefersReducedMotion, setPrefersReducedMotion] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  const scene = WALKTHROUGH_SCENES[state.sceneIndex];
  const isEnvironmentReady = isInView && isDocumentVisible;
  const isRunning =
    state.status === "playing" && isEnvironmentReady && !prefersReducedMotion;
  const isStaticComplete =
    prefersReducedMotion ||
    (state.status !== "playing" && state.sceneElapsedMs >= scene.durationMs);
  const sceneProgress = prefersReducedMotion
    ? 1
    : Math.min(state.sceneElapsedMs / scene.durationMs, 1);
  const overallProgress = useMemo(() => {
    const elapsed = elapsedBeforeScene(state.sceneIndex) + state.sceneElapsedMs;
    return Math.min((elapsed / WALKTHROUGH_DURATION_MS) * 100, 100);
  }, [state.sceneElapsedMs, state.sceneIndex]);

  useEffect(() => {
    const reducedMotionQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
    const desktopQuery = window.matchMedia(
      "(min-width: 768px) and (hover: hover) and (pointer: fine)",
    );
    const updatePreferences = () => {
      setPrefersReducedMotion(reducedMotionQuery.matches);
      setIsDesktopPlayback(desktopQuery.matches);
    };

    updatePreferences();
    reducedMotionQuery.addEventListener("change", updatePreferences);
    desktopQuery.addEventListener("change", updatePreferences);
    return () => {
      reducedMotionQuery.removeEventListener("change", updatePreferences);
      desktopQuery.removeEventListener("change", updatePreferences);
    };
  }, []);

  useEffect(() => {
    const element = rootRef.current;
    if (!element) return;

    const observer = new IntersectionObserver(
      ([entry]) => setIsInView(entry.isIntersecting && entry.intersectionRatio >= 0.55),
      { threshold: [0, 0.55, 1] },
    );
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const updateVisibility = () => setIsDocumentVisible(document.visibilityState === "visible");
    updateVisibility();
    document.addEventListener("visibilitychange", updateVisibility);
    return () => document.removeEventListener("visibilitychange", updateVisibility);
  }, []);

  useEffect(() => {
    if (isDesktopPlayback && isEnvironmentReady && !prefersReducedMotion) {
      dispatch({ type: "AUTOPLAY" });
    }
  }, [isDesktopPlayback, isEnvironmentReady, prefersReducedMotion]);

  useEffect(() => {
    if (!isRunning) return;

    let animationFrame = 0;
    let previousTimestamp: number | null = null;
    const tick = (timestamp: number) => {
      if (previousTimestamp !== null) {
        dispatch({ type: "TICK", deltaMs: Math.min(timestamp - previousTimestamp, 100) });
      }
      previousTimestamp = timestamp;
      animationFrame = window.requestAnimationFrame(tick);
    };
    animationFrame = window.requestAnimationFrame(tick);
    return () => window.cancelAnimationFrame(animationFrame);
  }, [isRunning]);

  const togglePlayback = () => {
    if (state.status === "playing") {
      dispatch({ type: "PAUSE" });
      return;
    }
    dispatch({ type: "PLAY" });
  };

  const goToScene = (sceneIndex: number) => dispatch({ type: "GO_TO", sceneIndex });

  return (
    <div
      ref={rootRef}
      className={cn(
        styles.walkthrough,
        "overflow-hidden rounded-[var(--radius-card)] border border-border-strong bg-surface-raised",
      )}
      data-running={isRunning ? "true" : "false"}
      data-static={isStaticComplete ? "true" : "false"}
    >
      <div className="min-h-[252px] border-b border-border-subtle bg-surface-raised px-4 py-4 sm:min-h-[194px] sm:px-5 lg:min-h-[178px]">
        <div className="flex flex-col items-start justify-between gap-3 sm:flex-row">
          <div className="w-full min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="neutral">Product preview</Badge>
              <Badge variant="warning">Sample data</Badge>
            </div>
            <p className="mt-3 text-[11px] font-semibold uppercase tracking-[0.14em] text-brand-primary">
              Step {state.sceneIndex + 1} of {WALKTHROUGH_SCENES.length}
            </p>
            <h3 className="mt-1 text-xl font-semibold text-text-primary sm:text-2xl">
              {scene.title}
            </h3>
            <p className="mt-1 min-h-12 text-sm leading-6 text-text-secondary sm:min-h-6">
              {scene.caption}
            </p>
          </div>
          <div className="flex w-full shrink-0 items-center gap-2 sm:w-auto">
            <Button
              type="button"
              variant="ghost"
              onClick={() => dispatch({ type: "REPLAY", reducedMotion: prefersReducedMotion })}
            >
              <RotateCcw size={16} aria-hidden="true" />
              Replay
            </Button>
            {state.status !== "finished" && (
              <Button
                type="button"
                variant="secondary"
                onClick={togglePlayback}
                disabled={prefersReducedMotion}
                aria-describedby={prefersReducedMotion ? "walkthrough-motion-note" : undefined}
              >
                {state.status === "playing" ? (
                  <Pause size={16} aria-hidden="true" />
                ) : (
                  <Play size={16} aria-hidden="true" />
                )}
                {state.status === "playing"
                  ? "Pause"
                  : state.status === "paused" && state.sceneElapsedMs < scene.durationMs
                    ? "Resume"
                    : state.status === "paused"
                      ? "Play from step"
                      : "Play"}
              </Button>
            )}
          </div>
        </div>

        <div className="mt-4 flex items-center gap-2">
          <div
            className="h-1.5 flex-1 overflow-hidden rounded-full bg-border-subtle"
            role="progressbar"
            aria-label="Walkthrough progress"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={Math.round(overallProgress)}
            aria-valuetext={`Step ${state.sceneIndex + 1} of ${WALKTHROUGH_SCENES.length}: ${scene.title}`}
          >
            <div
              className="h-full rounded-full bg-brand-primary"
              style={{ width: `${overallProgress}%` }}
            />
          </div>
          <span className="w-9 text-right text-[11px] font-medium tabular-nums text-text-secondary">
            {Math.round(overallProgress)}%
          </span>
        </div>
      </div>

      <div className="h-[640px] overflow-hidden sm:h-[560px] lg:h-[500px]">
        <WalkthroughWorkspace sceneId={scene.id} progress={sceneProgress} />
      </div>

      <div className="border-t border-border-subtle bg-surface-raised px-3 py-3 sm:px-5">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex items-center justify-between gap-2 lg:order-2 lg:justify-end">
            <Button
              type="button"
              size="icon"
              variant="ghost"
              onClick={() => goToScene(state.sceneIndex - 1)}
              disabled={state.sceneIndex === 0}
              aria-label="Previous step"
            >
              <ChevronLeft size={18} aria-hidden="true" />
            </Button>
            <Button
              type="button"
              size="icon"
              variant="ghost"
              onClick={() => goToScene(state.sceneIndex + 1)}
              disabled={state.sceneIndex === WALKTHROUGH_SCENES.length - 1}
              aria-label="Next step"
            >
              <ChevronRight size={18} aria-hidden="true" />
            </Button>
          </div>
          <div className="grid grid-cols-5 gap-1.5 lg:order-1 lg:flex lg:flex-wrap">
            {WALKTHROUGH_SCENES.map((item, index) => (
              <button
                key={item.id}
                type="button"
                onClick={() => goToScene(index)}
                aria-current={index === state.sceneIndex ? "step" : undefined}
                className={cn(
                  "min-h-10 rounded-[var(--radius-control)] border px-2 text-[11px] font-semibold transition-colors duration-[var(--duration-fast)] sm:px-3 sm:text-xs",
                  index === state.sceneIndex
                    ? "border-brand-primary bg-brand-primary text-text-inverse"
                    : "border-border-strong bg-surface-raised text-text-secondary hover:bg-surface-canvas hover:text-text-primary",
                )}
              >
                <span className="hidden sm:inline">{index + 1}. </span>
                {item.shortLabel}
              </button>
            ))}
          </div>
        </div>
        <p id="walkthrough-motion-note" className="mt-2 text-[11px] leading-4 text-text-secondary">
          {prefersReducedMotion
            ? "Reduced motion is on. Use the step controls to view each complete scene."
            : state.status === "playing" && !isEnvironmentReady
              ? "Playback is paused while the preview is out of view."
              : "This preview uses fictional local data and does not upload or fetch anything."}
        </p>
      </div>
    </div>
  );
}
