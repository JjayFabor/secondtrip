import type { Metadata } from "next";

import { CandidateListView } from "@/components/rework/candidate-list";
import { getApiErrorMessage, type CandidateList } from "@/lib/api";
import { getAuthenticatedBootstrap, selectOrganization, serverApi } from "@/lib/api-server";

export const metadata: Metadata = { title: "Possible callbacks" };

interface ReworkPageProps {
  searchParams: Promise<{ org?: string | string[] }>;
}

export default async function ReworkPage({ searchParams }: ReworkPageProps) {
  const [{ org }, { organizations }] = await Promise.all([
    searchParams,
    getAuthenticatedBootstrap(),
  ]);
  const organization = selectOrganization(
    organizations,
    typeof org === "string" ? org : undefined,
  );

  if (!organization) return <CandidateListView />;

  let initialPage: CandidateList | undefined;
  let initialError: string | undefined;
  try {
    initialPage = await serverApi.listCandidates(organization.id);
  } catch (error) {
    initialError = getApiErrorMessage(error);
  }

  return (
    <CandidateListView
      key={organization.id}
      initialOrganizationId={organization.id}
      initialPage={initialPage}
      initialError={initialError}
    />
  );
}
