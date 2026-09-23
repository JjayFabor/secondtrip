"use client";

import { type FormEvent, type ReactNode, useState } from "react";
import { CheckCircle2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { ApiError, api, type ContactInput } from "@/lib/api";

type FormState = "idle" | "submitting" | "success" | "error";

const EMPTY_FORM: ContactInput = {
  name: "",
  email: "",
  company: null,
  subject: "",
  message: "",
  website: "",
};

export function ContactForm() {
  const [form, setForm] = useState<ContactInput>(EMPTY_FORM);
  const [state, setState] = useState<FormState>("idle");
  const [message, setMessage] = useState("");
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  function update<K extends keyof ContactInput>(field: K, value: ContactInput[K]) {
    setForm((current) => ({ ...current, [field]: value }));
    setFieldErrors((current) => {
      const next = { ...current };
      delete next[field];
      return next;
    });
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setState("submitting");
    setMessage("");
    setFieldErrors({});
    try {
      const response = await api.contact(form);
      setState("success");
      setMessage(response.detail);
      setForm(EMPTY_FORM);
    } catch (error) {
      setState("error");
      if (!(error instanceof ApiError)) {
        setMessage("Something went wrong. Please try again.");
        return;
      }
      setFieldErrors(
        Object.fromEntries(
          error.fields
            .filter(
              (item): item is { field: string; message: string } =>
                Boolean(item.field && item.message),
            )
            .map((item) => [item.field, item.message]),
        ),
      );
      if (error.status === 429) {
        setMessage("Too many messages were sent from this connection. Please try again later.");
      } else if (error.status === 503 || error.status === 0) {
        setMessage("The contact service is unavailable right now. Please try again later.");
      } else {
        setMessage(error.message);
      }
    }
  }

  const busy = state === "submitting";

  return (
    <form onSubmit={submit} className="space-y-5">
      <div className="grid gap-5 sm:grid-cols-2">
        <Field label="Name" name="name" error={fieldErrors.name}>
          <Input
            id="name"
            name="name"
            autoComplete="name"
            required
            maxLength={120}
            value={form.name}
            aria-invalid={Boolean(fieldErrors.name)}
            aria-describedby={fieldErrors.name ? "name-error" : undefined}
            onChange={(event) => update("name", event.target.value)}
          />
        </Field>
        <Field label="Email" name="email" error={fieldErrors.email}>
          <Input
            id="email"
            name="email"
            type="email"
            autoComplete="email"
            required
            value={form.email}
            aria-invalid={Boolean(fieldErrors.email)}
            aria-describedby={fieldErrors.email ? "email-error" : undefined}
            onChange={(event) => update("email", event.target.value)}
          />
        </Field>
      </div>
      <Field label="Company (optional)" name="company" error={fieldErrors.company}>
        <Input
          id="company"
          name="company"
          autoComplete="organization"
          maxLength={160}
          value={form.company ?? ""}
          aria-invalid={Boolean(fieldErrors.company)}
          aria-describedby={fieldErrors.company ? "company-error" : undefined}
          onChange={(event) => update("company", event.target.value || null)}
        />
      </Field>
      <Field label="Subject" name="subject" error={fieldErrors.subject}>
        <Input
          id="subject"
          name="subject"
          required
          maxLength={160}
          value={form.subject}
          aria-invalid={Boolean(fieldErrors.subject)}
          aria-describedby={fieldErrors.subject ? "subject-error" : undefined}
          onChange={(event) => update("subject", event.target.value)}
        />
      </Field>
      <Field label="Message" name="message" error={fieldErrors.message}>
        <Textarea
          id="message"
          name="message"
          required
          minLength={10}
          maxLength={5000}
          rows={7}
          value={form.message}
          aria-invalid={Boolean(fieldErrors.message)}
          aria-describedby={fieldErrors.message ? "message-error" : "message-help"}
          onChange={(event) => update("message", event.target.value)}
        />
        {!fieldErrors.message ? (
          <p id="message-help" className="mt-2 text-xs text-text-secondary">
            Please do not include customer records, passwords, or other sensitive data.
          </p>
        ) : null}
      </Field>
      <div className="sr-only" aria-hidden="true">
        <Label htmlFor="website">Website</Label>
        <Input
          id="website"
          name="website"
          tabIndex={-1}
          autoComplete="off"
          value={form.website}
          onChange={(event) => update("website", event.target.value)}
        />
      </div>
      <div className="flex flex-col gap-4 border-t border-border-subtle pt-5 sm:flex-row sm:items-center sm:justify-between">
        <Button type="submit" disabled={busy}>
          {busy ? "Sending…" : "Send message"}
        </Button>
        <div className="min-h-6 text-sm" aria-live="polite" aria-atomic="true">
          {message ? (
            <p
              className={
                state === "success" ? "flex items-center gap-2 text-success" : "text-danger"
              }
            >
              {state === "success" ? <CheckCircle2 size={16} aria-hidden="true" /> : null}
              {message}
            </p>
          ) : null}
        </div>
      </div>
    </form>
  );
}

function Field({
  label,
  name,
  error,
  children,
}: {
  label: string;
  name: string;
  error?: string;
  children: ReactNode;
}) {
  return (
    <div>
      <Label htmlFor={name}>{label}</Label>
      <div className="mt-2">{children}</div>
      {error ? (
        <p id={`${name}-error`} className="mt-2 text-xs text-danger">
          {error}
        </p>
      ) : null}
    </div>
  );
}
