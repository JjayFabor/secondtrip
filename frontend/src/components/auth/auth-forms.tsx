"use client";

import type { FormEvent } from "react";
import { useState } from "react";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";

import { AuthDivider, FormAlert } from "@/components/auth/auth-shell";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api, getApiErrorMessage } from "@/lib/api";

function SubmitButton({ children, pending }: { children: string; pending: boolean }) {
  return (
    <Button type="submit" className="w-full" disabled={pending}>
      {pending ? "Working…" : children}
    </Button>
  );
}

function getSafeAppReturnPath(): string {
  const fallback = "/app/dashboard";
  const requestedPath = new URLSearchParams(window.location.search).get("next");
  if (!requestedPath) return fallback;

  try {
    const target = new URL(requestedPath, window.location.origin);
    const isAppRoute = target.pathname === "/app" || target.pathname.startsWith("/app/");
    if (target.origin !== window.location.origin || !isAppRoute) return fallback;
    return `${target.pathname}${target.search}${target.hash}`;
  } catch {
    return fallback;
  }
}

export function LoginForm() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string>();
  const [pending, setPending] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(undefined);
    setPending(true);

    try {
      await api.login({ email, password });
      router.replace(getSafeAppReturnPath());
    } catch (submissionError) {
      setError(getApiErrorMessage(submissionError));
      setPending(false);
    }
  }

  return (
    <>
      {error && <FormAlert kind="error">{error}</FormAlert>}
      <form className="mt-5 space-y-4" onSubmit={handleSubmit}>
        <div className="space-y-2">
          <Label htmlFor="login-email">Email address</Label>
          <Input
            id="login-email"
            name="email"
            type="email"
            autoComplete="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            required
            aria-invalid={Boolean(error)}
          />
        </div>
        <div className="space-y-2">
          <div className="flex items-center justify-between gap-3">
            <Label htmlFor="login-password">Password</Label>
            <Link href="/forgot-password" className="text-xs font-medium text-brand-primary hover:underline">
              Forgot password?
            </Link>
          </div>
          <Input
            id="login-password"
            name="password"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            required
            aria-invalid={Boolean(error)}
          />
        </div>
        <SubmitButton pending={pending}>Sign in</SubmitButton>
      </form>

      <AuthDivider>New to SecondTrip?</AuthDivider>
      <Button asChild variant="secondary" className="mt-5 w-full">
        <Link href="/register">Create an account</Link>
      </Button>
    </>
  );
}

export function RegisterForm() {
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string>();
  const [success, setSuccess] = useState<string>();
  const [pending, setPending] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(undefined);
    setSuccess(undefined);
    setPending(true);

    try {
      const response = await api.register({ full_name: fullName, email, password });
      setSuccess(response.detail);
      setPending(false);
    } catch (submissionError) {
      setError(getApiErrorMessage(submissionError));
      setPending(false);
    }
  }

  return (
    <>
      {error && <FormAlert kind="error">{error}</FormAlert>}
      {success && (
        <FormAlert kind="success">
          {success} Check the local API console in development, then continue to verification.
        </FormAlert>
      )}
      <form className="mt-5 space-y-4" onSubmit={handleSubmit}>
        <div className="space-y-2">
          <Label htmlFor="register-name">Full name</Label>
          <Input
            id="register-name"
            name="full_name"
            autoComplete="name"
            value={fullName}
            onChange={(event) => setFullName(event.target.value)}
            required
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="register-email">Email address</Label>
          <Input
            id="register-email"
            name="email"
            type="email"
            autoComplete="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            required
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="register-password">Password</Label>
          <Input
            id="register-password"
            name="password"
            type="password"
            autoComplete="new-password"
            minLength={12}
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            required
            aria-describedby="password-hint"
          />
          <p id="password-hint" className="text-xs leading-5 text-text-secondary">
            Use at least 12 characters. You can update it later from account settings.
          </p>
        </div>
        <SubmitButton pending={pending}>Create account</SubmitButton>
      </form>

      {success && (
        <Button asChild variant="secondary" className="mt-4 w-full">
          <Link href={`/verify?email=${encodeURIComponent(email)}`}>Continue to verification</Link>
        </Button>
      )}

      <AuthDivider>Already have an account?</AuthDivider>
      <Button asChild variant="secondary" className="mt-5 w-full">
        <Link href="/login">Sign in</Link>
      </Button>
    </>
  );
}

export function ForgotPasswordForm() {
  const [email, setEmail] = useState("");
  const [error, setError] = useState<string>();
  const [success, setSuccess] = useState<string>();
  const [pending, setPending] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(undefined);
    setSuccess(undefined);
    setPending(true);

    try {
      const response = await api.requestPasswordReset(email);
      setSuccess(response.detail);
    } catch (submissionError) {
      setError(getApiErrorMessage(submissionError));
    } finally {
      setPending(false);
    }
  }

  return (
    <>
      {error && <FormAlert kind="error">{error}</FormAlert>}
      {success && (
        <FormAlert kind="success">
          {success} In local development, the reset link is printed by the API email console.
        </FormAlert>
      )}
      <form className="mt-5 space-y-4" onSubmit={handleSubmit}>
        <div className="space-y-2">
          <Label htmlFor="forgot-email">Email address</Label>
          <Input
            id="forgot-email"
            name="email"
            type="email"
            autoComplete="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            required
          />
        </div>
        <SubmitButton pending={pending}>Email reset link</SubmitButton>
      </form>
      <Button asChild variant="ghost" className="mt-4 w-full">
        <Link href="/login">Back to sign in</Link>
      </Button>
    </>
  );
}

export function VerifyForm() {
  const searchParams = useSearchParams();
  const [token, setToken] = useState(searchParams.get("token") ?? "");
  const [email, setEmail] = useState(searchParams.get("email") ?? "");
  const [error, setError] = useState<string>();
  const [success, setSuccess] = useState<string>();
  const [pending, setPending] = useState(false);
  const [resendPending, setResendPending] = useState(false);

  async function handleVerify(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(undefined);
    setSuccess(undefined);

    if (!token.trim()) {
      setError("Paste the verification token from your email to continue.");
      return;
    }

    setPending(true);
    try {
      await api.verifyEmail(token.trim());
      setSuccess("Your email is verified. Your workspace is ready when you are.");
    } catch (submissionError) {
      setError(getApiErrorMessage(submissionError));
    } finally {
      setPending(false);
    }
  }

  async function handleResend(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(undefined);
    setSuccess(undefined);
    setResendPending(true);

    try {
      const response = await api.resendVerification(email);
      setSuccess(response.detail);
    } catch (submissionError) {
      setError(getApiErrorMessage(submissionError));
    } finally {
      setResendPending(false);
    }
  }

  return (
    <>
      {error && <FormAlert kind="error">{error}</FormAlert>}
      {success && <FormAlert kind="success">{success}</FormAlert>}
      <form className="mt-5 space-y-4" onSubmit={handleVerify}>
        {!searchParams.get("token") && (
          <div className="space-y-2">
            <Label htmlFor="verification-token">Verification token</Label>
            <Input
              id="verification-token"
              name="token"
              value={token}
              onChange={(event) => setToken(event.target.value)}
              autoComplete="one-time-code"
              required
            />
          </div>
        )}
        <SubmitButton pending={pending}>Verify email</SubmitButton>
      </form>

      {success && (
        <Button asChild variant="secondary" className="mt-4 w-full">
          <Link href="/app/dashboard">Continue to dashboard</Link>
        </Button>
      )}

      <AuthDivider>Need a fresh link?</AuthDivider>
      <form className="mt-5 space-y-4" onSubmit={handleResend}>
        <div className="space-y-2">
          <Label htmlFor="resend-email">Account email</Label>
          <Input
            id="resend-email"
            name="email"
            type="email"
            autoComplete="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            required
          />
        </div>
        <Button type="submit" variant="secondary" className="w-full" disabled={resendPending}>
          {resendPending ? "Sending…" : "Resend verification email"}
        </Button>
      </form>
      <Button asChild variant="ghost" className="mt-4 w-full">
        <Link href="/login">Back to sign in</Link>
      </Button>
    </>
  );
}

export function ResetPasswordForm() {
  const searchParams = useSearchParams();
  const [token, setToken] = useState(searchParams.get("token") ?? "");
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [error, setError] = useState<string>();
  const [success, setSuccess] = useState<string>();
  const [pending, setPending] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(undefined);
    setSuccess(undefined);

    if (password !== confirmation) {
      setError("Passwords do not match.");
      return;
    }
    if (password.length < 12) {
      setError("Use at least 12 characters for your new password.");
      return;
    }
    if (!token.trim()) {
      setError("Paste the reset token from your email to continue.");
      return;
    }

    setPending(true);
    try {
      await api.confirmPasswordReset(token.trim(), password);
      setSuccess("Your password is reset and you are signed in.");
    } catch (submissionError) {
      setError(getApiErrorMessage(submissionError));
    } finally {
      setPending(false);
    }
  }

  return (
    <>
      {error && <FormAlert kind="error">{error}</FormAlert>}
      {success && <FormAlert kind="success">{success}</FormAlert>}
      <form className="mt-5 space-y-4" onSubmit={handleSubmit}>
        {!searchParams.get("token") && (
          <div className="space-y-2">
            <Label htmlFor="reset-token">Reset token</Label>
            <Input
              id="reset-token"
              name="token"
              value={token}
              onChange={(event) => setToken(event.target.value)}
              autoComplete="one-time-code"
              required
            />
          </div>
        )}
        <div className="space-y-2">
          <Label htmlFor="reset-password">New password</Label>
          <Input
            id="reset-password"
            name="new_password"
            type="password"
            autoComplete="new-password"
            minLength={12}
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            required
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="reset-password-confirmation">Confirm new password</Label>
          <Input
            id="reset-password-confirmation"
            name="password_confirmation"
            type="password"
            autoComplete="new-password"
            minLength={12}
            value={confirmation}
            onChange={(event) => setConfirmation(event.target.value)}
            required
          />
        </div>
        <SubmitButton pending={pending}>Set new password</SubmitButton>
      </form>

      {success && (
        <Button asChild variant="secondary" className="mt-4 w-full">
          <Link href="/app/dashboard">Continue to dashboard</Link>
        </Button>
      )}
      <Button asChild variant="ghost" className="mt-4 w-full">
        <Link href="/login">Back to sign in</Link>
      </Button>
    </>
  );
}
