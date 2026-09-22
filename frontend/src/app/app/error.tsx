"use client";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";

export default function AuthenticatedAppError({ reset }: { error: Error; reset: () => void }) {
  return (
    <main className="flex min-h-dvh items-center justify-center bg-surface-canvas p-6">
      <Card className="max-w-lg border-danger bg-[var(--danger-bg)] p-6">
        <h1 className="text-lg font-semibold text-danger">Could not load your workspace</h1>
        <p className="mt-2 text-sm leading-6 text-text-primary">
          The workspace API is temporarily unavailable. Your data was not changed.
        </p>
        <Button className="mt-4" variant="secondary" onClick={reset}>
          Try again
        </Button>
      </Card>
    </main>
  );
}
