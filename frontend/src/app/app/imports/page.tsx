import type { Metadata } from "next";

import { ImportListView } from "@/components/imports/import-list";
import { getApiErrorMessage, type ImportList } from "@/lib/api";
import { getAuthenticatedBootstrap, selectOrganization, serverApi } from "@/lib/api-server";

export const metadata: Metadata = { title: "Imports — SecondTrip" };

export default async function ImportsPage({ searchParams }: PageProps<"/app/imports">) {
  const [{ org }, { organizations }] = await Promise.all([
    searchParams,
    getAuthenticatedBootstrap(),
  ]);
  const organization = selectOrganization(
    organizations,
    typeof org === "string" ? org : undefined,
  );

  if (!organization) return <ImportListView />;

  let initialPage: ImportList | undefined;
  let initialError: string | undefined;
  try {
    initialPage = await serverApi.listImports(organization.id);
  } catch (error) {
    initialError = getApiErrorMessage(error);
  }

  return (
    <ImportListView
      key={organization.id}
      initialOrganizationId={organization.id}
      initialPage={initialPage}
      initialError={initialError}
    />
  );
}
