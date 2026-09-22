import "server-only";

import { cache } from "react";
import { headers } from "next/headers";
import { redirect } from "next/navigation";

import {
  ApiError,
  type CandidateDetail,
  type CandidateList,
  type ImportBatch,
  type ImportIssues,
  type ImportList,
  type ImportPreview,
  type Organization,
  type ReworkCategory,
  type ReworkReview,
  type RootCause,
  type User,
} from "@/lib/api";

const apiBaseUrl = (
  process.env.API_INTERNAL_URL ||
  process.env.NEXT_PUBLIC_API_URL ||
  "http://127.0.0.1:8000"
).replace(/\/$/, "");

async function serverRequest<T>(path: string): Promise<T> {
  const incomingHeaders = await headers();
  const requestHeaders = new Headers({ Accept: "application/json" });
  const cookie = incomingHeaders.get("cookie");
  const requestId = incomingHeaders.get("x-request-id");

  if (cookie) requestHeaders.set("Cookie", cookie);
  if (requestId) requestHeaders.set("X-Request-Id", requestId);

  let response: Response;
  try {
    response = await fetch(`${apiBaseUrl}${path}`, {
      cache: "no-store",
      headers: requestHeaders,
    });
  } catch {
    throw new ApiError("The API is unavailable. Please try again.", 0);
  }

  const contentType = response.headers.get("content-type") ?? "";
  const payload = response.status === 204
    ? undefined
    : contentType.includes("json")
      ? await response.json().catch(() => undefined)
      : undefined;

  if (!response.ok) throw ApiError.fromResponse(response.status, payload);
  return payload as T;
}

export const getAuthenticatedBootstrap = cache(async () => {
  try {
    const [user, organizations] = await Promise.all([
      serverRequest<User>("/api/v1/me"),
      serverRequest<Organization[]>("/api/v1/orgs"),
    ]);
    return { user, organizations };
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) redirect("/login");
    throw error;
  }
});

export function selectOrganization(
  organizations: Organization[],
  organizationId?: string,
): Organization | undefined {
  return organizations.find((organization) => organization.id === organizationId) ?? organizations[0];
}

export const serverApi = {
  listImports(organizationId: string) {
    return serverRequest<ImportList>(
      `/api/v1/orgs/${encodeURIComponent(organizationId)}/imports?limit=25`,
    );
  },

  getImport(organizationId: string, batchId: string) {
    return serverRequest<ImportBatch>(
      `/api/v1/orgs/${encodeURIComponent(organizationId)}/imports/${encodeURIComponent(batchId)}`,
    );
  },

  getImportPreview(organizationId: string, batchId: string) {
    return serverRequest<ImportPreview>(
      `/api/v1/orgs/${encodeURIComponent(organizationId)}/imports/${encodeURIComponent(batchId)}/preview`,
    );
  },

  listImportIssues(organizationId: string, batchId: string) {
    return serverRequest<ImportIssues>(
      `/api/v1/orgs/${encodeURIComponent(organizationId)}/imports/${encodeURIComponent(batchId)}/issues?limit=50`,
    );
  },

  listCandidates(organizationId: string) {
    return serverRequest<CandidateList>(
      `/api/v1/orgs/${encodeURIComponent(organizationId)}/rework?status=open&limit=25`,
    );
  },

  getCandidate(organizationId: string, candidateId: string) {
    return serverRequest<CandidateDetail>(
      `/api/v1/orgs/${encodeURIComponent(organizationId)}/rework/${encodeURIComponent(candidateId)}`,
    );
  },

  listReviewHistory(organizationId: string, candidateId: string) {
    return serverRequest<ReworkReview[]>(
      `/api/v1/orgs/${encodeURIComponent(organizationId)}/rework/${encodeURIComponent(candidateId)}/reviews`,
    );
  },

  listReviewCategories(organizationId: string) {
    return serverRequest<ReworkCategory[]>(
      `/api/v1/orgs/${encodeURIComponent(organizationId)}/settings/categories`,
    );
  },

  listRootCauses(organizationId: string) {
    return serverRequest<RootCause[]>(
      `/api/v1/orgs/${encodeURIComponent(organizationId)}/settings/root-causes`,
    );
  },
};
