"use client";

import { useEffect, useState } from "react";

import { ArrowRight, Building2, Check, Mail, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";

import { AuthDivider, FormAlert } from "@/components/auth/auth-shell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { ApiError, api, getApiErrorMessage, type InvitationPreview } from "@/lib/api";

type InviteState = "loading" | "ready" | "accepted" | "error";

export function AcceptInviteForm() {
  const searchParams = useSearchParams();
  const token = searchParams.get("token")?.trim() ?? "";
  const [invitation, setInvitation] = useState<InvitationPreview>();
  const [state, setState] = useState<InviteState>("loading");
  const [resolvedToken, setResolvedToken] = useState<string>();
  const [error, setError] = useState<string>();
  const [accepting, setAccepting] = useState(false);

  useEffect(() => {
    let cancelled = false;

    if (!token) return () => {
      cancelled = true;
    };

    api.previewInvitation(token)
      .then((preview) => {
        if (cancelled) return;
        setInvitation(preview);
        setResolvedToken(token);
        setError(undefined);
        setState("ready");
      })
      .catch((previewError: unknown) => {
        if (cancelled) return;
        setResolvedToken(token);
        setState("error");
        setError(getPreviewErrorMessage(previewError));
      });

    return () => {
      cancelled = true;
    };
  }, [token]);

  async function handleAccept() {
    if (!token || !invitation) return;

    setAccepting(true);
    setError(undefined);

    try {
      await api.acceptInvitation(token);
      setState("accepted");
    } catch (acceptError: unknown) {
      setError(getAcceptErrorMessage(acceptError));
    } finally {
      setAccepting(false);
    }
  }

  if (!token) {
    return (
      <>
        <FormAlert kind="error">
          This invitation link is missing its token. Open the email again or ask an admin to send a new one.
        </FormAlert>
        <Button asChild variant="secondary" className="mt-5 w-full">
          <Link href="/login">Sign in to continue</Link>
        </Button>
        <p className="mt-4 text-center text-xs leading-5 text-text-secondary">
          If this link has expired, ask a workspace admin to send a fresh invitation.
        </p>
      </>
    );
  }

  if (resolvedToken !== token || state === "loading") {
    return (
      <div className="flex items-center gap-2 text-sm text-text-secondary" role="status">
        <span
          className="h-4 w-4 animate-spin rounded-full border-2 border-border-strong border-t-brand-primary"
          aria-hidden="true"
        />
        Checking your invitation…
      </div>
    );
  }

  if (state === "error") {
    return (
      <>
        <FormAlert kind="error">{error}</FormAlert>
        <Button asChild variant="secondary" className="mt-5 w-full">
          <Link href="/login">Sign in to continue</Link>
        </Button>
        <p className="mt-4 text-center text-xs leading-5 text-text-secondary">
          If this link has expired, ask a workspace admin to send a fresh invitation.
        </p>
      </>
    );
  }

  if (state === "accepted") {
    return (
      <>
        <FormAlert kind="success">
          You’re in. Your membership in {invitation?.organization_name} is ready.
        </FormAlert>
        <Button asChild className="mt-5 w-full">
          <Link href="/app/dashboard">
            Continue to dashboard
            <ArrowRight size={17} aria-hidden="true" />
          </Link>
        </Button>
      </>
    );
  }

  if (!invitation) return null;

  const roleLabel = formatRole(invitation.role);
  const organizationInitials = getInitials(invitation.organization_name);

  return (
    <>
      {error && <FormAlert kind="error">{error}</FormAlert>}
      <p className="mt-5 text-sm leading-6 text-text-secondary">
        You’ve been invited to join <strong className="font-semibold text-text-primary">{invitation.organization_name}</strong> as a <strong className="font-semibold text-text-primary">{roleLabel}</strong>.
      </p>

      <Card className="mt-5 bg-surface-canvas p-4 sm:p-5">
        <div className="flex items-center gap-3">
          <div
            className="flex h-11 w-11 shrink-0 items-center justify-center rounded-[var(--radius-control)] bg-brand-deep text-sm font-bold tracking-wide text-text-inverse"
            aria-hidden="true"
          >
            {organizationInitials}
          </div>
          <div className="min-w-0">
            <p className="truncate font-semibold text-text-primary">{invitation.organization_name}</p>
            <Badge className="mt-1" variant="neutral">
              Ready to join
            </Badge>
          </div>
        </div>

        <dl className="mt-5 divide-y divide-border-subtle border-y border-border-subtle">
          <DetailRow icon={Building2} label="Organization" value={invitation.organization_name} />
          <DetailRow icon={ShieldCheck} label="Your role" value={roleLabel} />
          <DetailRow icon={Mail} label="Invited email" value={invitation.email} />
        </dl>
      </Card>

      <Button type="button" className="mt-5 w-full" onClick={handleAccept} disabled={accepting}>
        {accepting ? (
          <>
            <span
              className="h-4 w-4 animate-spin rounded-full border-2 border-text-inverse/40 border-t-text-inverse"
              aria-hidden="true"
            />
            Accepting invitation…
          </>
        ) : (
          <>
            Accept invitation
            <ArrowRight size={17} aria-hidden="true" />
          </>
        )}
      </Button>

      <AuthDivider>Not the right account?</AuthDivider>
      <Button asChild variant="ghost" className="mt-4 w-full">
        <Link href="/login">Sign in with another account</Link>
      </Button>

      <p className="mt-5 flex items-start gap-2 text-xs leading-5 text-text-secondary">
        <Check className="mt-0.5 shrink-0 text-brand-primary" size={15} aria-hidden="true" />
        This invitation is tied to the email address above.
      </p>
    </>
  );
}

function DetailRow({
  icon: Icon,
  label,
  value,
}: {
  icon: typeof Building2;
  label: string;
  value: string;
}) {
  return (
    <div className="flex items-start gap-3 py-3 first:pt-3 last:pb-3">
      <Icon className="mt-0.5 shrink-0 text-brand-primary" size={16} aria-hidden="true" />
      <dt className="w-24 shrink-0 text-xs font-medium uppercase tracking-wide text-text-secondary">{label}</dt>
      <dd className="min-w-0 break-words text-right text-sm font-medium text-text-primary">{value}</dd>
    </div>
  );
}

function formatRole(role: InvitationPreview["role"]): string {
  return role.charAt(0).toUpperCase() + role.slice(1);
}

function getInitials(name: string): string {
  const initials = name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0])
    .join("")
    .toUpperCase();

  return initials || "ST";
}

function getPreviewErrorMessage(error: unknown): string {
  const message = getApiErrorMessage(error);
  return message === "Something went wrong. Please try again."
    ? "This invitation link is no longer active. Ask an admin to send a fresh invitation."
    : message;
}

function getAcceptErrorMessage(error: unknown): string {
  const message = getApiErrorMessage(error);
  return error instanceof ApiError && error.status === 401
    ? "Sign in with the invited email address before accepting this invitation."
    : message;
}
