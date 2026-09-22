"use client";

import { ArrowLeft, Clock3 } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { useAppShell } from "@/components/dashboard/app-shell";
import { ReviewHistory } from "@/components/rework/review-history";
import { ReviewDecisionPanel } from "@/components/rework/review-form";
import {
  ReviewStatusBadge,
  ScoreBadge,
  SignalEvidenceList,
  VisitComparison,
  customerLabel,
  equipmentLabel,
} from "@/components/rework/rework-ui";
import { Card } from "@/components/ui/card";
import type { CandidateDetail, ReworkCategory, ReworkReview, RootCause } from "@/lib/api";

export function CandidateDetailView({
  initialCandidate,
  categories,
  rootCauses,
  initialReviews,
  organizationId,
}: {
  initialCandidate: CandidateDetail;
  categories: ReworkCategory[];
  rootCauses: RootCause[];
  initialReviews: ReworkReview[];
  organizationId: string;
}) {
  const { organization, canReviewCallbacks } = useAppShell();
  const [candidate, setCandidate] = useState(initialCandidate);
  const [reviews, setReviews] = useState(initialReviews);
  const timezone = organization?.timezone ?? "UTC";
  const queueHref = `/app/rework?org=${encodeURIComponent(organizationId)}`;

  return (
    <div className="mx-auto w-full max-w-[1440px] space-y-5">
      <Link
        href={queueHref}
        className="inline-flex min-h-10 items-center gap-2 rounded-[var(--radius-control)] text-sm font-semibold text-brand-primary underline-offset-4 hover:underline"
      >
        <ArrowLeft size={16} aria-hidden="true" />
        Back to possible callbacks
      </Link>

      <header className="border-b border-border-subtle pb-5">
        <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
          <div className="min-w-0">
            <p className="text-xs font-semibold uppercase tracking-wide text-brand-primary">Evidence review</p>
            <h1 className="mt-1 break-words text-[28px] font-bold leading-tight text-text-primary sm:text-[34px]">
              {customerLabel(candidate)}
            </h1>
            <p className="mt-1 text-sm text-text-secondary">{equipmentLabel(candidate)}</p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <ScoreBadge score={candidate.score} band={candidate.band} />
            <span className="inline-flex items-center gap-1.5 rounded-full border border-border-strong bg-surface-raised px-2.5 py-0.5 text-xs font-medium text-text-secondary tabular-nums">
              <Clock3 size={14} aria-hidden="true" />
              {candidate.days_between} days between
            </span>
            <ReviewStatusBadge review={candidate.current_review} workflowStatus={candidate.workflow_status} />
          </div>
        </div>
        <p className="mt-3 max-w-3xl text-sm leading-6 text-text-secondary">
          Review the visit records and every deterministic signal before recording the human outcome.
        </p>
      </header>

      {candidate.is_suppressed && (
        <Card className="border-border-strong bg-surface-raised p-4" role="status">
          <p className="text-sm font-semibold text-text-primary">This candidate is suppressed</p>
          <p className="mt-1 text-sm text-text-secondary">
            {candidate.suppressed_by_signal_key
              ? `Suppressed by the ${candidate.suppressed_by_signal_key.replaceAll("_", " ")} signal.`
              : "It is retained for evidence review but excluded from the active queue."}
          </p>
        </Card>
      )}

      <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_360px]">
        <div className="space-y-5">
          <VisitComparison candidate={candidate} timezone={timezone} />
          <SignalEvidenceList signals={candidate.signals} />
          <ReviewHistory
            reviews={reviews}
            categories={categories}
            rootCauses={rootCauses}
            timezone={timezone}
          />
        </div>
        <aside aria-label="Callback classification">
          <ReviewDecisionPanel
            organizationId={organizationId}
            candidateId={candidate.id}
            categories={categories}
            rootCauses={rootCauses}
            currentReview={candidate.current_review}
            canReview={canReviewCallbacks}
            timezone={timezone}
            onReviewed={(review) => {
              setCandidate((current) => ({
                ...current,
                current_review: review,
                workflow_status: "reviewed",
              }));
              setReviews((current) => [review, ...current.filter((item) => item.id !== review.id)]);
            }}
          />
        </aside>
      </div>
    </div>
  );
}

export function CandidateDetailError({ message, organizationId }: { message: string; organizationId: string }) {
  return (
    <div className="mx-auto w-full max-w-3xl">
      <Card className="border-danger bg-[var(--danger-bg)] p-6" role="alert">
        <h1 className="text-lg font-semibold text-danger">Callback evidence is unavailable</h1>
        <p className="mt-2 text-sm leading-6 text-text-primary">{message}</p>
        <Link
          href={`/app/rework?org=${encodeURIComponent(organizationId)}`}
          className="mt-4 inline-flex min-h-10 items-center font-semibold text-brand-primary underline-offset-4 hover:underline"
        >
          Return to the review queue
        </Link>
      </Card>
    </div>
  );
}
