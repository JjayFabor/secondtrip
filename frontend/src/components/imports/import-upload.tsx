"use client";

import { useRef, useState } from "react";
import { FileUp } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { useAppShell } from "@/components/dashboard/app-shell";
import { formatBytes, ImportPageHeader, StepRail } from "@/components/imports/import-ui";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError, api, getApiErrorMessage } from "@/lib/api";
import { cn } from "@/lib/utils";

interface DuplicateState {
  batchId: string;
  detail: string;
}

export function ImportUploadView() {
  const router = useRouter();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const { organization, canManageImports } = useAppShell();
  const [file, setFile] = useState<File>();
  const [dragging, setDragging] = useState(false);
  const [working, setWorking] = useState(false);
  const [message, setMessage] = useState("Choose a CSV file to begin.");
  const [error, setError] = useState<string>();
  const [planLimit, setPlanLimit] = useState<number>();
  const [duplicate, setDuplicate] = useState<DuplicateState>();

  function chooseFile(nextFile?: File) {
    setError(undefined);
    setDuplicate(undefined);
    setPlanLimit(undefined);
    if (!nextFile) {
      setFile(undefined);
      setMessage("Choose a CSV file to begin.");
      return;
    }
    if (!nextFile.name.toLowerCase().endsWith(".csv")) {
      setFile(undefined);
      setError("Choose a file with a .csv extension. Excel workbooks must be exported as CSV first.");
      return;
    }
    setFile(nextFile);
    setMessage(`${nextFile.name} selected, ${formatBytes(nextFile.size)}.`);
  }

  async function confirm(batchId: string, allowDuplicate: boolean) {
    if (!organization) return;
    try {
      setWorking(true);
      setError(undefined);
      setMessage(allowDuplicate ? "Confirming the duplicate import…" : "Verifying the uploaded file…");
      await api.confirmImportUpload(organization.id, batchId, allowDuplicate);
      setMessage("Upload confirmed. Opening import details…");
      router.push(`/app/imports/${batchId}?org=${encodeURIComponent(organization.id)}`);
    } catch (requestError) {
      if (requestError instanceof ApiError && requestError.code === "DUPLICATE_IMPORT") {
        setDuplicate({ batchId, detail: requestError.message });
        setMessage("This file matches an earlier import. Review the duplicate warning.");
      } else {
        setError(getApiErrorMessage(requestError));
        setMessage("Upload confirmation failed.");
      }
    } finally {
      setWorking(false);
    }
  }

  async function handleUpload() {
    if (!organization || !file || working) return;
    setWorking(true);
    setError(undefined);
    setDuplicate(undefined);
    setMessage("Requesting a secure upload destination…");
    try {
      const creation = await api.createImport(organization.id, file.name);
      setPlanLimit(creation.upload.max_bytes);
      if (file.size > creation.upload.max_bytes) {
        setError(
          `${file.name} is ${formatBytes(file.size)}. Your plan allows up to ${formatBytes(creation.upload.max_bytes)} per file.`,
        );
        setMessage("The selected file is larger than this workspace allows.");
        return;
      }
      setMessage(`Uploading ${file.name}. Your plan limit is ${formatBytes(creation.upload.max_bytes)}.`);
      await api.uploadImportFile(creation.upload, file);
      setWorking(false);
      await confirm(creation.batch.id, false);
    } catch (requestError) {
      setError(getApiErrorMessage(requestError));
      setMessage("The file was not uploaded.");
    } finally {
      setWorking(false);
    }
  }

  const historyHref = organization
    ? `/app/imports?org=${encodeURIComponent(organization.id)}`
    : "/app/imports";

  return (
    <div className="mx-auto w-full max-w-5xl space-y-6">
      <ImportPageHeader
        title="Import jobs"
        description="Upload the original CSV. SecondTrip profiles the file before you decide how any source column should be used."
        action={<Button asChild variant="secondary"><Link href={historyHref}>Back to imports</Link></Button>}
      />
      <StepRail active={1} />

      {!canManageImports ? (
        <Card className="p-6">
          <h2 className="text-lg font-semibold text-text-primary">Manager access required</h2>
          <p className="mt-2 text-sm leading-6 text-text-secondary">
            Members can review import history and results, but only owners, administrators, and managers can upload files.
          </p>
        </Card>
      ) : (
        <Card className="p-6 sm:p-8">
          <div className="max-w-2xl">
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-brand-primary">Source file</p>
            <h2 className="mt-2 text-xl font-semibold text-text-primary">Choose the CSV export</h2>
            <p className="mt-2 text-sm leading-6 text-text-secondary">
              CSV only. Keep the source file unchanged so row numbers and validation findings match your export.
            </p>
          </div>

          <div
            className={cn(
              "mt-6 flex min-h-52 flex-col items-center justify-center rounded-[var(--radius-card)] border border-dashed border-border-strong bg-surface-canvas p-6 text-center",
              dragging && "border-brand-primary bg-[var(--success-bg)]",
            )}
            onDragEnter={(event) => { event.preventDefault(); setDragging(true); }}
            onDragOver={(event) => event.preventDefault()}
            onDragLeave={(event) => { if (event.currentTarget === event.target) setDragging(false); }}
            onDrop={(event) => {
              event.preventDefault();
              setDragging(false);
              chooseFile(event.dataTransfer.files[0]);
            }}
          >
            <FileUp size={20} strokeWidth={1.75} className="text-brand-primary" aria-hidden="true" />
            <Label htmlFor="import-file" className="mt-4 text-base font-semibold">CSV file</Label>
            <p className="mt-1 text-sm text-text-secondary">Drag a file here, or choose it from your device.</p>
            <Input
              ref={fileInputRef}
              id="import-file"
              type="file"
              accept=".csv,text/csv"
              className="sr-only"
              onChange={(event) => chooseFile(event.target.files?.[0])}
            />
            <Button type="button" variant="secondary" className="mt-4" onClick={() => fileInputRef.current?.click()}>
              Choose CSV
            </Button>
          </div>

          {file && (
            <dl className="mt-5 grid gap-4 border-y border-border-subtle py-4 text-sm sm:grid-cols-3">
              <div><dt className="text-text-secondary">Selected file</dt><dd className="mt-1 truncate font-medium text-text-primary">{file.name}</dd></div>
              <div><dt className="text-text-secondary">File size</dt><dd className="mt-1 tabular-nums font-medium text-text-primary">{formatBytes(file.size)}</dd></div>
              <div><dt className="text-text-secondary">Plan file limit</dt><dd className="mt-1 tabular-nums font-medium text-text-primary">{planLimit ? formatBytes(planLimit) : "Confirmed when upload starts"}</dd></div>
            </dl>
          )}

          <div aria-live="polite" className="mt-5 text-sm text-text-secondary">{message}</div>
          {error && <p className="mt-3 text-sm font-medium text-danger" role="alert">{error}</p>}
          {duplicate && (
            <div className="mt-5 border-l-4 border-warning bg-[var(--warning-bg)] p-4 text-text-on-accent">
              <p className="font-semibold">This exact file was imported before</p>
              <p className="mt-1 text-sm leading-6">{duplicate.detail}</p>
              <Button className="mt-4" onClick={() => void confirm(duplicate.batchId, true)} disabled={working}>
                Import anyway
              </Button>
            </div>
          )}

          {!duplicate && (
            <div className="mt-6 flex justify-end">
              <Button onClick={() => void handleUpload()} disabled={!file || working || !organization}>
                {working ? "Uploading…" : "Upload CSV"}
              </Button>
            </div>
          )}
        </Card>
      )}
    </div>
  );
}
