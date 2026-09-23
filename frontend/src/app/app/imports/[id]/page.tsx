import type { Metadata } from "next";

import { ImportDetailView } from "@/components/imports/import-detail";
import {
  getApiErrorMessage,
  type ImportBatch,
  type ImportIssues,
  type ImportPreview,
} from "@/lib/api";
import { getAuthenticatedBootstrap, selectOrganization, serverApi } from "@/lib/api-server";

export const metadata: Metadata = { title: "Import detail — SecondTrip" };

interface ImportDetailPageProps {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ org?: string | string[] }>;
}

export default async function ImportDetailPage({
  params,
  searchParams,
}: ImportDetailPageProps) {
  const [{ id }, { org }, { organizations }] = await Promise.all([
    params,
    searchParams,
    getAuthenticatedBootstrap(),
  ]);
  const organization = selectOrganization(
    organizations,
    typeof org === "string" ? org : undefined,
  );

  if (!organization) return <ImportDetailView batchId={id} />;

  let initialBatch: ImportBatch | undefined;
  let initialPreview: ImportPreview | undefined;
  let initialIssues: ImportIssues | undefined;
  let initialError: string | undefined;
  let initialActionError: string | undefined;
  let initialIssuesError: string | undefined;

  try {
    initialBatch = await serverApi.getImport(organization.id, id);
    const canManageImports = ["owner", "admin", "manager"].includes(organization.role);

    if (initialBatch.status === "awaiting_mapping" && canManageImports) {
      try {
        initialPreview = await serverApi.getImportPreview(organization.id, id);
      } catch (error) {
        initialActionError = getApiErrorMessage(error);
      }
    }

    const showsIssues = initialBatch.status === "validated" || (
      ["completed", "completed_with_errors", "failed", "cancelled"].includes(initialBatch.status) &&
      (initialBatch.error_rows > 0 || initialBatch.warning_rows > 0 || initialBatch.skipped_rows > 0)
    );
    if (showsIssues) {
      try {
        initialIssues = await serverApi.listImportIssues(organization.id, id);
      } catch (error) {
        initialIssuesError = getApiErrorMessage(error);
      }
    }
  } catch (error) {
    initialError = getApiErrorMessage(error);
  }

  return (
    <ImportDetailView
      key={`${organization.id}:${id}`}
      batchId={id}
      initialOrganizationId={organization.id}
      initialBatch={initialBatch}
      initialPreview={initialPreview}
      initialIssues={initialIssues}
      initialError={initialError}
      initialActionError={initialActionError}
      initialIssuesError={initialIssuesError}
    />
  );
}
