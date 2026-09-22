import { ReviewOutcomeBadge, formatReviewDate, formatScore } from "@/components/rework/rework-ui";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { ReworkCategory, ReworkReview, RootCause } from "@/lib/api";

export function ReviewHistory({
  reviews,
  categories,
  rootCauses,
  timezone,
}: {
  reviews: ReworkReview[];
  categories: ReworkCategory[];
  rootCauses: RootCause[];
  timezone: string;
}) {
  const categoryLabels = new Map(categories.map((category) => [category.id, category.label]));
  const rootCauseLabels = new Map(rootCauses.map((rootCause) => [rootCause.id, rootCause.label]));

  return (
    <Card>
      <CardHeader className="border-b border-border-subtle p-5">
        <CardTitle>Review history</CardTitle>
        <p className="text-sm text-text-secondary">
          Human decisions are append-only. Reclassifying adds a new entry without removing prior judgement.
        </p>
      </CardHeader>
      <CardContent className="p-0">
        {reviews.length === 0 ? (
          <p className="px-5 py-6 text-sm text-text-secondary">
            No human reviews have been recorded yet.
          </p>
        ) : (
          <ol className="divide-y divide-border-subtle" aria-label="Review history, newest first">
            {reviews.map((review, index) => {
              const isCurrent = index === 0;
              const category = review.category_id ? categoryLabels.get(review.category_id) : undefined;
              const rootCause = review.root_cause_id ? rootCauseLabels.get(review.root_cause_id) : undefined;

              return (
                <li key={review.id} className="px-5 py-4">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant={isCurrent ? "strong" : "neutral"}>
                      {isCurrent ? "Current classification" : "Previous classification"}
                    </Badge>
                    <ReviewOutcomeBadge decision={review.decision} />
                    {!isCurrent && <span className="text-xs font-medium text-text-secondary">Superseded</span>}
                  </div>

                  <div className="mt-3 grid gap-3 text-sm sm:grid-cols-[minmax(0,1fr)_auto] sm:items-start">
                    <div className="min-w-0">
                      <p className="font-semibold text-text-primary">
                        {category ?? "No category recorded"}
                        {rootCause && <span className="font-normal text-text-secondary"> · {rootCause}</span>}
                      </p>
                      {review.note && (
                        <p className="mt-1 whitespace-pre-wrap break-words leading-6 text-text-secondary">
                          {review.note}
                        </p>
                      )}
                    </div>
                    <dl className="grid grid-cols-2 gap-x-5 gap-y-2 sm:grid-cols-1 sm:text-right">
                      <div>
                        <dt className="text-xs text-text-secondary">Reviewed</dt>
                        <dd className="mt-0.5 whitespace-nowrap font-medium text-text-primary">
                          {formatReviewDate(review.decided_at, timezone)}
                        </dd>
                      </div>
                      {review.score_at_review !== null && (
                        <div>
                          <dt className="text-xs text-text-secondary">Score at review</dt>
                          <dd className="mt-0.5 font-medium tabular-nums text-text-primary">
                            {formatScore(review.score_at_review)}
                          </dd>
                        </div>
                      )}
                    </dl>
                  </div>
                </li>
              );
            })}
          </ol>
        )}
      </CardContent>
    </Card>
  );
}
