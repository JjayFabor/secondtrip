"use client";

import { ArrowRight, SearchX } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { useAppShell } from "@/components/dashboard/app-shell";
import {
  ReviewStatusBadge,
  ScoreBadge,
  customerLabel,
  equipmentLabel,
  formatServiceDate,
} from "@/components/rework/rework-ui";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import {
  api,
  getApiErrorMessage,
  type CandidateList,
  type CandidateWorkflowStatus,
  type ScoreBand,
} from "@/lib/api";

type StatusFilter = CandidateWorkflowStatus;
type BandFilter = ScoreBand | "all";

export function CandidateListView({
  initialOrganizationId,
  initialPage,
  initialError,
}: {
  initialOrganizationId?: string;
  initialPage?: CandidateList;
  initialError?: string;
}) {
  const { organization } = useAppShell();
  const [page, setPage] = useState<CandidateList | undefined>(initialPage);
  const [pageOrganizationId, setPageOrganizationId] = useState(initialOrganizationId);
  const [status, setStatus] = useState<StatusFilter>("open");
  const [band, setBand] = useState<BandFilter>("all");
  const [cursor, setCursor] = useState<string>();
  const [cursorHistory, setCursorHistory] = useState<(string | undefined)[]>([]);
  const [queryVersion, setQueryVersion] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(initialError);

  useEffect(() => {
    if (!organization) return;
    if (
      queryVersion === 0 &&
      organization.id === initialOrganizationId &&
      pageOrganizationId === organization.id
    ) return;

    let active = true;
    api.listCandidates(organization.id, {
      cursor,
      limit: 25,
      status,
      band: band === "all" ? undefined : band,
    })
      .then((result) => {
        if (!active) return;
        setPage(result);
        setPageOrganizationId(organization.id);
        setError(undefined);
      })
      .catch((requestError: unknown) => {
        if (active) setError(getApiErrorMessage(requestError));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => { active = false; };
  }, [band, cursor, initialOrganizationId, organization, pageOrganizationId, queryVersion, status]);

  function updateFilters(nextStatus: StatusFilter, nextBand: BandFilter) {
    setStatus(nextStatus);
    setBand(nextBand);
    setCursor(undefined);
    setCursorHistory([]);
    setLoading(true);
    setQueryVersion((value) => value + 1);
  }

  const filtersActive = status !== "open" || band !== "all";

  return (
    <div className="mx-auto w-full max-w-[1440px] space-y-5">
      <header className="border-b border-border-subtle pb-5">
        <h1 className="text-[30px] font-bold leading-tight text-text-primary sm:text-[36px]">
          Possible callbacks
        </h1>
        <p className="mt-2 max-w-2xl text-sm leading-6 text-text-secondary">
          Visit pairs with deterministic signals awaiting human judgement. A high score is evidence strength, not a final decision.
        </p>
      </header>

      <section className="flex flex-wrap items-end gap-3" aria-label="Callback filters">
        <div className="min-w-44">
          <label htmlFor="callback-status-filter" className="mb-1.5 block text-sm font-medium text-text-primary">
            Review state
          </label>
          <Select
            value={status}
            onValueChange={(value) => updateFilters(value as StatusFilter, band)}
          >
            <SelectTrigger id="callback-status-filter"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="open">Awaiting review</SelectItem>
              <SelectItem value="in_review">In review</SelectItem>
              <SelectItem value="reviewed">Reviewed</SelectItem>
              <SelectItem value="dismissed">Dismissed</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div className="min-w-40">
          <label htmlFor="callback-band-filter" className="mb-1.5 block text-sm font-medium text-text-primary">
            Score band
          </label>
          <Select
            value={band}
            onValueChange={(value) => updateFilters(status, value as BandFilter)}
          >
            <SelectTrigger id="callback-band-filter"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All bands</SelectItem>
              <SelectItem value="high">High</SelectItem>
              <SelectItem value="medium">Medium</SelectItem>
              <SelectItem value="low">Low</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <Button
          type="button"
          variant="ghost"
          disabled={!filtersActive}
          onClick={() => updateFilters("open", "all")}
        >
          Reset filters
        </Button>
      </section>

      {!organization ? (
        <Card className="p-6">
          <h2 className="text-lg font-semibold text-text-primary">No workspace selected</h2>
          <p className="mt-2 text-sm text-text-secondary">Create or join an organization to review possible callbacks.</p>
        </Card>
      ) : loading || (pageOrganizationId !== organization.id && !error) ? (
        <CandidateListLoading />
      ) : error ? (
        <Card className="border-danger bg-[var(--danger-bg)] p-5" role="alert">
          <p className="font-semibold text-danger">The review queue is unavailable</p>
          <p className="mt-1 text-sm text-text-primary">{error}</p>
          <Button
            className="mt-4"
            variant="secondary"
            onClick={() => {
              setLoading(true);
              setError(undefined);
              setQueryVersion((value) => value + 1);
            }}
          >
            Try again
          </Button>
        </Card>
      ) : !page?.data.length ? (
        <Card className="flex min-h-56 flex-col items-center justify-center p-8 text-center">
          <SearchX size={20} strokeWidth={1.75} className="text-brand-primary" aria-hidden="true" />
          <h2 className="mt-4 text-lg font-semibold text-text-primary">
            {filtersActive ? "No callbacks match these filters" : "No possible callbacks yet"}
          </h2>
          <p className="mt-1 max-w-md text-sm leading-6 text-text-secondary">
            {filtersActive
              ? "Reset the filters to return to the full review queue."
              : "Candidates will appear after imported job history has been analyzed."}
          </p>
          {filtersActive && (
            <Button className="mt-5" variant="secondary" onClick={() => updateFilters("open", "all")}>
              Reset filters
            </Button>
          )}
        </Card>
      ) : (
        <>
          <Card className="overflow-hidden">
            <Table className="min-w-[1160px]" scrollLabel="Possible callback review queue">
              <TableHeader>
                <TableRow>
                  <TableHead>Customer / equipment</TableHead>
                  <TableHead>Visit pair</TableHead>
                  <TableHead align="right">Gap</TableHead>
                  <TableHead>Evidence score</TableHead>
                  <TableHead>Top evidence</TableHead>
                  <TableHead>Review state</TableHead>
                  <TableHead><span className="sr-only">Open</span></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {page.data.map((candidate) => (
                  <TableRow key={candidate.id} className="[&>td]:py-2">
                    <TableCell className="max-w-60">
                      <p className="truncate font-semibold" title={customerLabel(candidate)}>{customerLabel(candidate)}</p>
                      <p className="mt-0.5 truncate text-xs text-text-secondary" title={equipmentLabel(candidate)}>{equipmentLabel(candidate)}</p>
                    </TableCell>
                    <TableCell className="whitespace-nowrap">
                      <div className="flex items-center gap-2 tabular-nums text-sm">
                        <span>{formatServiceDate(candidate.prior_job.service_date, organization.timezone)}</span>
                        <ArrowRight size={15} className="text-brand-primary" aria-hidden="true" />
                        <span>{formatServiceDate(candidate.followup_job.service_date, organization.timezone)}</span>
                      </div>
                    </TableCell>
                    <TableCell align="right" className="whitespace-nowrap">{candidate.days_between} days</TableCell>
                    <TableCell><ScoreBadge score={candidate.score} band={candidate.band} /></TableCell>
                    <TableCell className="max-w-80">
                      {candidate.top_signals.length ? (
                        <p
                          className="max-w-80 truncate text-sm text-text-secondary"
                          title={candidate.top_signals.slice(0, 3).map((signal) => signal.label).join(" · ")}
                        >
                          {candidate.top_signals.slice(0, 3).map((signal) => signal.label).join(" · ")}
                        </p>
                      ) : <span className="text-sm text-text-secondary">No matched signals</span>}
                    </TableCell>
                    <TableCell>
                      <ReviewStatusBadge review={candidate.current_review} workflowStatus={candidate.workflow_status} />
                    </TableCell>
                    <TableCell>
                      <Link
                        href={`/app/rework/${candidate.id}?org=${encodeURIComponent(organization.id)}`}
                        className="inline-flex min-h-10 items-center font-semibold text-brand-primary underline-offset-4 hover:underline focus-visible:rounded-[var(--radius-control)]"
                        aria-label={`Review callback for ${customerLabel(candidate)}`}
                      >
                        Review
                      </Link>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Card>

          <nav className="flex items-center justify-between gap-3" aria-label="Callback queue pagination">
            <Button
              variant="secondary"
              disabled={!cursorHistory.length}
              onClick={() => {
                const previous = cursorHistory.at(-1);
                setCursorHistory(cursorHistory.slice(0, -1));
                setCursor(previous);
                setLoading(true);
                setQueryVersion((value) => value + 1);
              }}
            >
              Previous
            </Button>
            <span className="text-center text-sm text-text-secondary">{page.data.length} candidates on this page</span>
            <Button
              variant="secondary"
              disabled={!page.page.has_more || !page.page.next_cursor}
              onClick={() => {
                setCursorHistory([...cursorHistory, cursor]);
                setCursor(page.page.next_cursor ?? undefined);
                setLoading(true);
                setQueryVersion((value) => value + 1);
              }}
            >
              Next
            </Button>
          </nav>
        </>
      )}
    </div>
  );
}

function CandidateListLoading() {
  return (
    <div className="space-y-2" aria-label="Loading possible callbacks" aria-live="polite">
      <Skeleton className="h-11 w-full" />
      <Skeleton className="h-16 w-full" />
      <Skeleton className="h-16 w-full" />
      <Skeleton className="h-16 w-full" />
      <Skeleton className="h-16 w-full" />
    </div>
  );
}
