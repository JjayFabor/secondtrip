import type { Metadata } from "next";

import { CandidateDetailError, CandidateDetailView } from "@/components/rework/candidate-detail";
import { Card } from "@/components/ui/card";
import {
  getApiErrorMessage,
  type CandidateDetail,
  type ReworkCategory,
  type ReworkReview,
  type RootCause,
} from "@/lib/api";
import { getAuthenticatedBootstrap, selectOrganization, serverApi } from "@/lib/api-server";

export const metadata: Metadata = { title: "Callback evidence" };

interface CandidatePageProps {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ org?: string | string[] }>;
}

export default async function CandidatePage({ params, searchParams }: CandidatePageProps) {
  const [{ id }, { org }, { organizations }] = await Promise.all([
    params,
    searchParams,
    getAuthenticatedBootstrap(),
  ]);
  const organization = selectOrganization(
    organizations,
    typeof org === "string" ? org : undefined,
  );

  if (!organization) {
    return (
      <Card className="mx-auto max-w-2xl p-6">
        <h1 className="text-lg font-semibold text-text-primary">No workspace selected</h1>
        <p className="mt-2 text-sm text-text-secondary">Create or join an organization before reviewing callback evidence.</p>
      </Card>
    );
  }

  let candidate: CandidateDetail | undefined;
  let categories: ReworkCategory[] = [];
  let rootCauses: RootCause[] = [];
  let reviews: ReworkReview[] = [];
  let errorMessage: string | undefined;
  try {
    [candidate, categories, rootCauses, reviews] = await Promise.all([
      serverApi.getCandidate(organization.id, id),
      serverApi.listReviewCategories(organization.id),
      serverApi.listRootCauses(organization.id),
      serverApi.listReviewHistory(organization.id, id),
    ]);
  } catch (error) {
    errorMessage = getApiErrorMessage(error);
  }

  if (!candidate || errorMessage) {
    return (
      <CandidateDetailError
        message={errorMessage ?? "The callback candidate could not be found."}
        organizationId={organization.id}
      />
    );
  }

  return (
    <CandidateDetailView
      initialCandidate={candidate}
      categories={categories}
      rootCauses={rootCauses}
      initialReviews={reviews}
      organizationId={organization.id}
    />
  );
}
