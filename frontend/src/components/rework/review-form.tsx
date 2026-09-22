"use client";

import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";

import { DECISION_LABELS, formatReviewDate } from "@/components/rework/rework-ui";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { Textarea } from "@/components/ui/textarea";
import {
  ApiError,
  api,
  getApiErrorMessage,
  type ReviewDecision,
  type ReworkCategory,
  type ReworkReview,
  type RootCause,
} from "@/lib/api";

const DECISIONS: { value: ReviewDecision; label: string; detail: string }[] = [
  { value: "confirmed", label: "Confirmed", detail: "This was a callback or rework visit." },
  { value: "rejected", label: "Rejected", detail: "The return visit was unrelated or expected." },
  { value: "uncertain", label: "Uncertain", detail: "There is not enough evidence to decide." },
];

const CATEGORY_OUTCOME: Record<ReviewDecision, ReworkCategory["outcome"]> = {
  confirmed: "rework",
  rejected: "not_rework",
  uncertain: "uncertain",
};

export function ReviewDecisionPanel({
  organizationId,
  candidateId,
  categories,
  rootCauses,
  currentReview,
  canReview,
  timezone,
  onReviewed,
}: {
  organizationId: string;
  candidateId: string;
  categories: ReworkCategory[];
  rootCauses: RootCause[];
  currentReview: ReworkReview | null;
  canReview: boolean;
  timezone: string;
  onReviewed: (review: ReworkReview) => void;
}) {
  const router = useRouter();
  const initialDecision = currentReview?.decision ?? "confirmed";
  const [decision, setDecision] = useState<ReviewDecision>(initialDecision);
  const [categoryId, setCategoryId] = useState(currentReview?.category_id ?? "");
  const [rootCauseId, setRootCauseId] = useState(currentReview?.root_cause_id ?? "none");
  const [note, setNote] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string>();
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [success, setSuccess] = useState<string>();

  const availableCategories = useMemo(
    () => categories.filter((category) => category.is_active && category.outcome === CATEGORY_OUTCOME[decision]),
    [categories, decision],
  );
  const activeRootCauses = useMemo(
    () => rootCauses.filter((rootCause) => rootCause.is_active),
    [rootCauses],
  );

  function changeDecision(nextDecision: ReviewDecision) {
    const compatibleCategories = categories.filter(
      (category) => category.is_active && category.outcome === CATEGORY_OUTCOME[nextDecision],
    );
    const currentCategoryStillMatches = compatibleCategories.some((category) => category.id === categoryId);
    setDecision(nextDecision);
    setCategoryId(currentCategoryStillMatches ? categoryId : compatibleCategories[0]?.id ?? "");
    if (nextDecision !== "confirmed") setRootCauseId("none");
    setError(undefined);
    setFieldErrors({});
    setSuccess(undefined);
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(undefined);
    setFieldErrors({});
    setSuccess(undefined);

    if (!categoryId) {
      setFieldErrors({ category_id: "Choose the classification that best fits this decision." });
      return;
    }

    setSubmitting(true);
    try {
      const review = await api.createReview(organizationId, candidateId, {
        decision,
        category_id: categoryId,
        root_cause_id: decision === "confirmed" && rootCauseId !== "none" ? rootCauseId : null,
        note: note.trim() || null,
      });
      onReviewed(review);
      setNote("");
      setSuccess(currentReview ? "Classification updated. The earlier decision remains in review history." : "Review saved.");
      router.refresh();
    } catch (requestError) {
      if (requestError instanceof ApiError) {
        setFieldErrors(Object.fromEntries(
          requestError.fields
            .filter((item): item is { field: string; message: string } => Boolean(item.field && item.message))
            .map((item) => [item.field, item.message]),
        ));
      }
      setError(getApiErrorMessage(requestError));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Card className="lg:sticky lg:top-6">
      <CardHeader className="border-b border-border-subtle p-5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <CardTitle>Classification</CardTitle>
          {currentReview && <Badge variant="neutral">Existing review</Badge>}
        </div>
        <p className="text-sm text-text-secondary">
          Human judgement is the final outcome for this visit pair.
        </p>
      </CardHeader>
      <CardContent className="p-5">
        {currentReview && (
          <CurrentReview
            review={currentReview}
            categories={categories}
            rootCauses={rootCauses}
            timezone={timezone}
          />
        )}

        {!canReview ? (
          <div className={currentReview ? "mt-5" : undefined}>
            <p className="text-sm font-semibold text-text-primary">Review access is read-only</p>
            <p className="mt-1 text-sm leading-6 text-text-secondary">
              Managers, admins, and owners can classify or reclassify this candidate. You can still inspect all evidence.
            </p>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className={currentReview ? "mt-5" : undefined}>
            {currentReview && <Separator className="mb-5" />}
            <fieldset>
              <legend className="text-sm font-semibold text-text-primary">Decision</legend>
              <RadioGroup
                className="mt-3 gap-2"
                value={decision}
                onValueChange={(value) => changeDecision(value as ReviewDecision)}
                aria-describedby={fieldErrors.decision ? "decision-error" : undefined}
              >
                {DECISIONS.map((item) => (
                  <Label
                    key={item.value}
                    htmlFor={`decision-${item.value}`}
                    className="flex min-h-14 cursor-pointer items-start gap-3 rounded-[var(--radius-control)] border border-border-strong p-3 has-[[data-state=checked]]:border-brand-primary has-[[data-state=checked]]:bg-surface-canvas"
                  >
                    <RadioGroupItem id={`decision-${item.value}`} value={item.value} className="mt-0.5 shrink-0" />
                    <span>
                      <span className="block font-semibold text-text-primary">{item.label}</span>
                      <span className="mt-0.5 block text-xs font-normal leading-5 text-text-secondary">{item.detail}</span>
                    </span>
                  </Label>
                ))}
              </RadioGroup>
              {fieldErrors.decision && <p id="decision-error" className="mt-2 text-sm text-danger">{fieldErrors.decision}</p>}
            </fieldset>

            <div className="mt-5">
              <Label htmlFor="review-category">Category</Label>
              <Select value={categoryId || undefined} onValueChange={setCategoryId}>
                <SelectTrigger
                  id="review-category"
                  className="mt-1.5"
                  aria-invalid={Boolean(fieldErrors.category_id)}
                  aria-describedby={fieldErrors.category_id ? "category-error" : undefined}
                >
                  <SelectValue placeholder="Choose a category" />
                </SelectTrigger>
                <SelectContent>
                  {availableCategories.map((category) => (
                    <SelectItem key={category.id} value={category.id}>{category.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {fieldErrors.category_id && <p id="category-error" className="mt-2 text-sm text-danger">{fieldErrors.category_id}</p>}
            </div>

            {decision === "confirmed" && (
              <div className="mt-5">
                <Label htmlFor="review-root-cause">Root cause <span className="font-normal text-text-secondary">(optional)</span></Label>
                <Select value={rootCauseId} onValueChange={setRootCauseId}>
                  <SelectTrigger
                    id="review-root-cause"
                    className="mt-1.5"
                    aria-invalid={Boolean(fieldErrors.root_cause_id)}
                  >
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">Not identified</SelectItem>
                    {activeRootCauses.map((rootCause) => (
                      <SelectItem key={rootCause.id} value={rootCause.id}>{rootCause.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                {fieldErrors.root_cause_id && <p className="mt-2 text-sm text-danger">{fieldErrors.root_cause_id}</p>}
              </div>
            )}

            <div className="mt-5">
              <Label htmlFor="review-note">Review note <span className="font-normal text-text-secondary">(optional)</span></Label>
              <Textarea
                id="review-note"
                className="mt-1.5"
                value={note}
                onChange={(event) => setNote(event.target.value)}
                maxLength={2000}
                placeholder="Add context for the next reviewer."
                aria-invalid={Boolean(fieldErrors.note)}
                aria-describedby={fieldErrors.note ? "note-error" : undefined}
              />
              <div className="mt-1 flex justify-between gap-3 text-xs text-text-secondary">
                <span>{fieldErrors.note && <span id="note-error" className="text-danger">{fieldErrors.note}</span>}</span>
                <span className="tabular-nums">{note.length}/2,000</span>
              </div>
            </div>

            <div className="mt-5" aria-live="polite">
              {error && <p className="mb-3 text-sm text-danger" role="alert">{error}</p>}
              {success && <p className="mb-3 text-sm font-medium text-success">{success}</p>}
              <Button type="submit" className="w-full" disabled={submitting || !availableCategories.length}>
                {submitting ? "Saving review…" : currentReview ? "Update classification" : "Save review"}
              </Button>
            </div>
          </form>
        )}
      </CardContent>
    </Card>
  );
}

function CurrentReview({
  review,
  categories,
  rootCauses,
  timezone,
}: {
  review: ReworkReview;
  categories: ReworkCategory[];
  rootCauses: RootCause[];
  timezone: string;
}) {
  const category = categories.find((item) => item.id === review.category_id);
  const rootCause = rootCauses.find((item) => item.id === review.root_cause_id);
  return (
    <div>
      <p className="text-xs font-medium uppercase tracking-wide text-text-secondary">Current outcome</p>
      <p className="mt-1 text-base font-semibold text-text-primary">{DECISION_LABELS[review.decision]}</p>
      <dl className="mt-3 grid grid-cols-2 gap-3 text-sm">
        <div>
          <dt className="text-xs text-text-secondary">Category</dt>
          <dd className="mt-0.5 font-medium text-text-primary">{category?.label ?? "Not assigned"}</dd>
        </div>
        <div>
          <dt className="text-xs text-text-secondary">Root cause</dt>
          <dd className="mt-0.5 font-medium text-text-primary">{rootCause?.label ?? "Not identified"}</dd>
        </div>
      </dl>
      {review.note && <p className="mt-3 text-sm leading-6 text-text-secondary">“{review.note}”</p>}
      <p className="mt-3 text-xs text-text-secondary">Reviewed {formatReviewDate(review.decided_at, timezone)}</p>
    </div>
  );
}
