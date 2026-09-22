"use client";

import { useState } from "react";

import { ArrowRight, MailCheck, RefreshCw, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";

import { AuthDivider, FormAlert } from "@/components/auth/auth-shell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { ApiError, api, getApiErrorMessage, type User } from "@/lib/api";

type ConfirmationState = "ready" | "confirming" | "success" | "error";

export function ConfirmEmailChangeForm() {
  const searchParams = useSearchParams();
  const token = searchParams.get("token")?.trim() ?? "";
  const [state, setState] = useState<ConfirmationState>("ready");
  const [updatedUser, setUpdatedUser] = useState<User>();
  const [error, setError] = useState<string>();
  const [canRetry, setCanRetry] = useState(false);

  async function handleConfirm() {
    if (!token) return;

    setState("confirming");
    setError(undefined);
    setCanRetry(false);

    try {
      const user = await api.confirmEmailChange(token);
      setUpdatedUser(user);
      setState("success");
    } catch (confirmationError: unknown) {
      setError(getConfirmationErrorMessage(confirmationError));
      setCanRetry(confirmationError instanceof ApiError && confirmationError.status === 0);
      setState("error");
    }
  }

  if (!token) {
    return (
      <>
        <FormAlert kind="error">
          This confirmation link is missing its token. Open the latest email again or start a new email change after signing in.
        </FormAlert>
        <Button asChild variant="secondary" className="mt-5 w-full">
          <Link href="/login">Back to sign in</Link>
        </Button>
      </>
    );
  }

  if (state === "success") {
    return (
      <>
        <FormAlert kind="success">
          Your email address has been updated{updatedUser?.email ? ` to ${updatedUser.email}` : ""}. Your new session is ready.
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

  if (state === "error") {
    return (
      <>
        <FormAlert kind="error">{error}</FormAlert>
        {canRetry && (
          <Button type="button" variant="secondary" className="mt-5 w-full" onClick={() => setState("ready")}>
            <RefreshCw size={16} aria-hidden="true" />
            Try again
          </Button>
        )}
        <Button asChild variant={canRetry ? "ghost" : "secondary"} className="mt-4 w-full">
          <Link href="/login">Back to sign in</Link>
        </Button>
        <p className="mt-4 text-center text-xs leading-5 text-text-secondary">
          This link can only be used once and expires shortly. Request a new email change after signing in if needed.
        </p>
      </>
    );
  }

  return (
    <>
      <Card className="bg-surface-canvas p-4 sm:p-5">
        <div className="flex items-start gap-3">
          <div
            className="flex h-11 w-11 shrink-0 items-center justify-center rounded-[var(--radius-control)] bg-brand-deep text-text-inverse"
            aria-hidden="true"
          >
            <MailCheck size={21} />
          </div>
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <p className="font-semibold text-text-primary">Email change request</p>
              <Badge variant="neutral">Secure link</Badge>
            </div>
            <p className="mt-2 text-sm leading-5 text-text-secondary">
              Confirming will update your sign-in address and refresh your session on this device.
            </p>
          </div>
        </div>

        <div className="mt-4 flex items-start gap-2 border-t border-border-subtle pt-4 text-xs leading-5 text-text-secondary">
          <ShieldCheck className="mt-0.5 shrink-0 text-brand-primary" size={15} aria-hidden="true" />
          <span>This confirmation is single-use and tied to your account.</span>
        </div>
      </Card>

      <Button type="button" className="mt-5 w-full" onClick={handleConfirm} disabled={state === "confirming"}>
        {state === "confirming" ? (
          <>
            <span
              className="h-4 w-4 animate-spin rounded-full border-2 border-text-inverse/40 border-t-text-inverse"
              aria-hidden="true"
            />
            Confirming email change…
          </>
        ) : (
          <>
            Confirm email change
            <ArrowRight size={17} aria-hidden="true" />
          </>
        )}
      </Button>

      <AuthDivider>Need to use a different account?</AuthDivider>
      <Button asChild variant="ghost" className="mt-4 w-full">
        <Link href="/login">Back to sign in</Link>
      </Button>
    </>
  );
}

function getConfirmationErrorMessage(error: unknown): string {
  if (error instanceof ApiError && error.status === 0) {
    return "We couldn’t reach the account service. Check your connection and try again.";
  }

  return error instanceof ApiError
    ? "This email-change link is invalid, expired, or has already been used. Sign in to request a new one."
    : getApiErrorMessage(error);
}
