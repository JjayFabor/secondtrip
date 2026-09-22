"use client";

import { useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ApiError, api, getApiErrorMessage, type ImportBatch, type ImportIssues, type ImportIssueSeverity } from "@/lib/api";

const SEVERITY_STYLES: Record<ImportIssueSeverity, string> = {
  error: "bg-[var(--danger-bg)] text-danger",
  warning: "bg-[var(--warning-bg)] text-text-on-accent",
  info: "border border-border-strong bg-surface-raised text-text-secondary",
};

export function ImportIssueTable({
  organizationId,
  batch,
  initialIssues,
  initialError,
}: {
  organizationId: string;
  batch: ImportBatch;
  initialIssues?: ImportIssues;
  initialError?: string;
}) {
  const hasInitialResult = initialIssues !== undefined || initialError !== undefined;
  const [issues, setIssues] = useState<ImportIssues | undefined>(initialIssues);
  const [cursor, setCursor] = useState<string>();
  const [history, setHistory] = useState<(string | undefined)[]>([]);
  const [loading, setLoading] = useState(!hasInitialResult);
  const [error, setError] = useState<string | undefined>(initialError);
  const [downloadMessage, setDownloadMessage] = useState<string>();
  const [reloadRequest, setReloadRequest] = useState(0);

  useEffect(() => {
    if (cursor === undefined && reloadRequest === 0 && hasInitialResult) return;
    let active = true;
    api.listImportIssues(organizationId, batch.id, { cursor, limit: 50 })
      .then((result) => {
        if (!active) return;
        setIssues(result);
        setError(undefined);
      })
      .catch((requestError: unknown) => {
        if (active) setError(getApiErrorMessage(requestError));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => { active = false; };
  }, [batch.id, cursor, hasInitialResult, organizationId, reloadRequest]);

  const pageCounts = useMemo(() => {
    const counts = { error: 0, warning: 0, info: 0 };
    for (const row of issues?.data ?? []) {
      for (const issue of row.issues) counts[issue.severity] += 1;
    }
    return counts;
  }, [issues]);

  async function downloadReport() {
    setDownloadMessage("Preparing download…");
    try {
      const result = await api.getImportIssueExport(organizationId, batch.id);
      window.location.assign(result.url);
      setDownloadMessage("Download started.");
    } catch (requestError) {
      if (requestError instanceof ApiError && requestError.status === 409) {
        setDownloadMessage("The error report is still being generated. Try again in a moment.");
      } else {
        setDownloadMessage(getApiErrorMessage(requestError));
      }
    }
  }

  return (
    <Card className="overflow-hidden">
      <div className="flex flex-col gap-4 border-b border-border-subtle p-5 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h2 className="text-lg font-semibold text-text-primary">Row issues</h2>
          <p className="mt-1 text-sm text-text-secondary">
            On this page: {pageCounts.error} errors · {pageCounts.warning} warnings · {pageCounts.info} information notices
          </p>
        </div>
        {(batch.error_rows > 0 || batch.warning_rows > 0) && (
          <Button variant="secondary" onClick={() => void downloadReport()}>
            {batch.error_report_ready ? "Download error report" : "Check report status"}
          </Button>
        )}
      </div>
      {downloadMessage && <p className="border-b border-border-subtle px-5 py-3 text-sm text-text-secondary" aria-live="polite">{downloadMessage}</p>}
      {loading ? (
        <div className="space-y-3 p-5" aria-label="Loading row issues"><Skeleton className="h-10" /><Skeleton className="h-10" /><Skeleton className="h-10" /></div>
      ) : error ? (
        <div className="p-5" role="alert"><p className="text-sm font-medium text-danger">{error}</p><Button className="mt-3" variant="secondary" onClick={() => { setLoading(true); setError(undefined); setReloadRequest((value) => value + 1); }}>Try again</Button></div>
      ) : !issues?.data.length ? (
        <p className="p-5 text-sm text-text-secondary">No row issues were recorded.</p>
      ) : (
        <>
          <Table className="min-w-[820px]" scrollLabel="Import row issues">
            <TableHeader><TableRow><TableHead align="right">Row</TableHead><TableHead>Severity</TableHead><TableHead>Code</TableHead><TableHead>Field</TableHead><TableHead>Message</TableHead></TableRow></TableHeader>
            <TableBody>
              {issues.data.flatMap((row) => row.issues.map((issue, issueIndex) => (
                <TableRow key={`${row.id}-${issueIndex}`}>
                  <TableCell align="right">{row.row_number.toLocaleString()}</TableCell>
                  <TableCell><span className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium ${SEVERITY_STYLES[issue.severity]}`}>{issue.severity}</span></TableCell>
                  <TableCell><code className="text-xs text-brand-deep">{issue.code}</code></TableCell>
                  <TableCell>{issue.field ?? "—"}</TableCell>
                  <TableCell className="min-w-72"><p>{issue.message}</p>{issue.raw_value && <p className="mt-1 max-w-96 truncate text-xs text-text-secondary">Source: {issue.raw_value}</p>}</TableCell>
                </TableRow>
              ))) }
            </TableBody>
          </Table>
          <nav className="flex items-center justify-between border-t border-border-subtle p-4" aria-label="Issue pagination">
            <Button variant="secondary" disabled={!history.length} onClick={() => { const previous = history.at(-1); setLoading(true); setHistory((items) => items.slice(0, -1)); setCursor(previous); }}>Previous</Button>
            <span className="text-sm text-text-secondary">{issues.data.length} affected rows on this page</span>
            <Button variant="secondary" disabled={!issues.page.has_more || !issues.page.next_cursor} onClick={() => { setLoading(true); setHistory((items) => [...items, cursor]); setCursor(issues.page.next_cursor ?? undefined); }}>Next</Button>
          </nav>
        </>
      )}
    </Card>
  );
}
