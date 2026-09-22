"use client";

import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { LogOut } from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

import { DashboardLayout } from "@/components/dashboard/dashboard-layout";
import { type SidebarItem } from "@/components/dashboard/sidebar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { api, type Organization, type User } from "@/lib/api";

interface AppShellContextValue {
  user: User;
  organizations: Organization[];
  organization: Organization | null;
  canManageImports: boolean;
  canReviewCallbacks: boolean;
}

const AppShellContext = createContext<AppShellContextValue | null>(null);

export function useAppShell(): AppShellContextValue {
  const value = useContext(AppShellContext);
  if (!value) throw new Error("useAppShell must be used within AppShell.");
  return value;
}

export function AppShell({
  children,
  user,
  organizations,
}: {
  children: React.ReactNode;
  user: User;
  organizations: Organization[];
}) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const selectedOrganizationId = searchParams.get("org");
  const [loggingOut, setLoggingOut] = useState(false);

  const organization = useMemo(
    () =>
      organizations.find((item) => item.id === selectedOrganizationId) ??
      organizations[0] ??
      null,
    [organizations, selectedOrganizationId],
  );

  useEffect(() => {
    if (!organization || organization.id === selectedOrganizationId) return;
    const nextParams = new URLSearchParams(searchParams.toString());
    nextParams.set("org", organization.id);
    router.replace(`${pathname}?${nextParams.toString()}`, { scroll: false });
  }, [organization, pathname, router, searchParams, selectedOrganizationId]);

  const sidebarItems = useMemo<SidebarItem[] | undefined>(() => {
    if (!organization) return undefined;
    const orgQuery = `?org=${encodeURIComponent(organization.id)}`;
    return [
      { label: "Overview", href: `/app/dashboard${orgQuery}`, icon: "overview" },
      { label: "Callbacks", href: `/app/rework${orgQuery}`, icon: "callbacks" },
      { label: "Imports", href: `/app/imports${orgQuery}`, icon: "imports" },
    ];
  }, [organization]);

  async function handleLogout() {
    setLoggingOut(true);
    try {
      await api.logout();
    } finally {
      router.replace("/login");
    }
  }

  function switchOrganization(organizationId: string) {
    const nextParams = new URLSearchParams(searchParams.toString());
    nextParams.set("org", organizationId);
    const isImportDetail = /^\/app\/imports\/[^/]+$/.test(pathname);
    const isCallbackDetail = /^\/app\/rework\/[^/]+$/.test(pathname);
    const targetPath = isImportDetail
      ? "/app/imports"
      : isCallbackDetail
        ? "/app/rework"
        : pathname;
    router.push(`${targetPath}?${nextParams.toString()}`, { scroll: false });
  }

  const roleLabel = organization
    ? organization.role.charAt(0).toUpperCase() + organization.role.slice(1)
    : null;
  const canManageImports = Boolean(
    organization && ["owner", "admin", "manager"].includes(organization.role),
  );
  const canReviewCallbacks = canManageImports;

  return (
    <AppShellContext.Provider
      value={{ user, organizations, organization, canManageImports, canReviewCallbacks }}
    >
      <DashboardLayout
        activeHref={pathname}
        primaryItems={sidebarItems}
        secondaryItems={[]}
        topBarContent={
          <div className="flex min-w-0 flex-1 items-center justify-between gap-3">
            <OrganizationControl
              organizations={organizations}
              organization={organization}
              onChange={switchOrganization}
            />
            <div className="ml-auto flex items-center gap-3">
              {roleLabel && <Badge className="hidden md:inline-flex">{roleLabel}</Badge>}
              <div className="hidden text-right sm:block">
                <p className="max-w-48 truncate text-sm font-medium text-text-primary">{user.full_name}</p>
                <p className="max-w-48 truncate text-xs text-text-secondary">{user.email}</p>
              </div>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={handleLogout}
                disabled={loggingOut}
                aria-label="Sign out"
              >
                <LogOut size={16} aria-hidden="true" />
                <span className="hidden sm:inline">Sign out</span>
              </Button>
            </div>
          </div>
        }
      >
        {children}
      </DashboardLayout>
    </AppShellContext.Provider>
  );
}

function OrganizationControl({
  organizations,
  organization,
  onChange,
}: {
  organizations: Organization[];
  organization: Organization | null;
  onChange: (organizationId: string) => void;
}) {
  if (!organization) {
    return (
      <div>
        <p className="text-sm font-semibold text-text-primary">No workspace</p>
        <p className="text-xs text-text-secondary">Create an organization to continue.</p>
      </div>
    );
  }

  if (organizations.length === 1) {
    return (
      <div className="min-w-0">
        <p className="max-w-52 truncate text-sm font-semibold text-text-primary">{organization.name}</p>
        <p className="text-xs text-text-secondary">Current workspace</p>
      </div>
    );
  }

  return (
    <div>
      <label className="sr-only" htmlFor="organization-switcher">Current organization</label>
      <Select value={organization.id} onValueChange={onChange}>
        <SelectTrigger id="organization-switcher" className="h-9 min-w-40 max-w-56 bg-surface-canvas text-sm">
          <SelectValue aria-label={organization.name} />
        </SelectTrigger>
        <SelectContent align="start">
          {organizations.map((item) => (
            <SelectItem key={item.id} value={item.id}>{item.name}</SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}
