import type { components } from "@secondtrip/contracts";

type Schemas = components["schemas"];

export type User = Schemas["UserOut"];
export type OrganizationRole = Schemas["OrganizationRole"];
export type InvitationPreview = Schemas["InvitationPreviewOut"];
export type Membership = Schemas["MembershipOut"];
export type Organization = Schemas["MyOrganizationOut"];
export type ImportStatus = Schemas["ImportStatus"];
export type ImportRowStatus = Schemas["ImportRowStatus"];
export type ImportIssueSeverity = Schemas["IssueSeverity"];
export type ImportIssueCode = Schemas["IssueCode"];
export type DateTransform = Schemas["DateTransform"];
export type MoneyTransform = Schemas["MoneyTransform"];
export type BooleanTransform = Schemas["BooleanTransform"];
export type ValueMapTransform = Schemas["ValueMapTransform"];
export type ImportTransform =
  | DateTransform
  | MoneyTransform
  | BooleanTransform
  | ValueMapTransform;
export type ImportFieldMapping = Schemas["FieldMapping"];
export type ImportSkipFilter = Schemas["SkipFilter"];
export type ImportMappingDocument = Schemas["MappingDocument"];
export type ImportBatch = Schemas["ImportBatchOut"];
export type CursorPage = Schemas["ImportPageOut"];
export type ImportList = Schemas["ImportListOut"];
export type PresignedUpload = Schemas["PresignedUploadOut"];
export type CreateImportResult = Schemas["CreateImportOut"];
export type ImportIssue = Schemas["ProfileIssueOut"];
export type ImportDetectedColumn = Schemas["DetectedColumnOut"];
export type ImportMappingSuggestion = Schemas["MappingSuggestionOut"];
export type ImportPreview = Schemas["ImportPreviewOut"];
export type ImportIssueRow = Schemas["ImportIssueRowOut"];
export type ImportIssues = Schemas["ImportIssuesOut"];
export type ScoreBand = Schemas["ScoreBand"];
export type CandidateWorkflowStatus = Schemas["CandidateWorkflowStatus"];
export type CandidateSignal = Schemas["CandidateSignalOut"];
export type CandidateSummary = Schemas["CandidateSummaryOut"];
export type CandidateList = Schemas["CandidateListOut"];
export type CandidateDetail = Schemas["CandidateDetailOut"];
export type ReworkCategory = Schemas["ReworkCategoryOut"];
export type RootCause = Schemas["RootCauseOut"];
export type ReviewDecision = Schemas["ReviewDecision"];
export type ReworkReview = Schemas["ReworkReviewOut"];
export type CreateReviewInput = Schemas["CreateReviewRequest"];

type RegisterInput = Schemas["RegisterRequest"];
type LoginInput = Schemas["LoginRequest"];

interface ProblemField {
  field?: string;
  message?: string;
}

interface ProblemDocument {
  detail?: string;
  code?: string;
  errors?: ProblemField[];
}

export class ApiError extends Error {
  readonly status: number;
  readonly code?: string;
  readonly fields: ProblemField[];

  constructor(message: string, status: number, code?: string, fields: ProblemField[] = []) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.fields = fields;
  }

  static fromResponse(status: number, body: unknown): ApiError {
    const problem = body && typeof body === "object" ? (body as ProblemDocument) : {};
    return new ApiError(
      problem.detail ?? "Something went wrong. Please try again.",
      status,
      problem.code,
      problem.errors ?? [],
    );
  }
}

type RequestOptions = Omit<RequestInit, "body"> & {
  body?: unknown;
};

const apiBaseUrl = (process.env.NEXT_PUBLIC_API_URL ?? "").replace(/\/$/, "");
const csrfCookieName = "st_csrf";
let csrfBootstrap: Promise<string> | null = null;

function apiUrl(path: string): string {
  return `${apiBaseUrl}${path}`;
}

function readCookie(name: string): string | undefined {
  if (typeof document === "undefined") return undefined;

  const encodedName = `${encodeURIComponent(name)}=`;
  const cookie = document.cookie.split("; ").find((part) => part.startsWith(encodedName));
  if (!cookie) return undefined;

  return decodeURIComponent(cookie.slice(encodedName.length));
}

async function getCsrfToken(): Promise<string> {
  const existing = readCookie(csrfCookieName);
  if (existing) return existing;

  if (!csrfBootstrap) {
    csrfBootstrap = fetch(apiUrl("/api/v1/me"), {
      credentials: "include",
      headers: { Accept: "application/json" },
    })
      .then(() => readCookie(csrfCookieName) ?? "")
      .finally(() => {
        csrfBootstrap = null;
      });
  }

  const token = await csrfBootstrap;
  if (!token) {
    throw new ApiError("Could not initialize a secure form session. Please refresh and try again.", 0);
  }
  return token;
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const method = (options.method ?? "GET").toUpperCase();
  const headers = new Headers(options.headers);
  headers.set("Accept", "application/json");

  let body: BodyInit | undefined;
  if (options.body !== undefined) {
    headers.set("Content-Type", "application/json");
    body = JSON.stringify(options.body);
  }

  if (!new Set(["GET", "HEAD", "OPTIONS"]).has(method)) {
    headers.set("X-CSRF-Token", await getCsrfToken());
  }

  let response: Response;
  try {
    response = await fetch(apiUrl(path), {
      ...options,
      method,
      body,
      credentials: "include",
      headers,
    });
  } catch {
    throw new ApiError("The local API is unavailable. Start it and try again.", 0);
  }

  const contentType = response.headers.get("content-type") ?? "";
  const payload = response.status === 204
    ? undefined
    : contentType.includes("json")
      ? await response.json().catch(() => undefined)
      : undefined;

  if (!response.ok) {
    throw ApiError.fromResponse(response.status, payload);
  }

  return payload as T;
}

export const api = {
  register(input: RegisterInput) {
    return request<{ detail: string }>("/api/v1/auth/register", {
      method: "POST",
      body: input,
    });
  },

  login(input: LoginInput) {
    return request<User>("/api/v1/auth/login", {
      method: "POST",
      body: input,
    });
  },

  resendVerification(email: string) {
    return request<{ detail: string }>("/api/v1/auth/resend-verification", {
      method: "POST",
      body: { email },
    });
  },

  verifyEmail(token: string) {
    return request<User>("/api/v1/auth/verify-email", {
      method: "POST",
      body: { token },
    });
  },

  requestPasswordReset(email: string) {
    return request<{ detail: string }>("/api/v1/auth/password-reset/request", {
      method: "POST",
      body: { email },
    });
  },

  confirmPasswordReset(token: string, newPassword: string) {
    return request<User>("/api/v1/auth/password-reset/confirm", {
      method: "POST",
      body: { token, new_password: newPassword },
    });
  },

  confirmEmailChange(token: string) {
    return request<User>("/api/v1/auth/email-change/confirm", {
      method: "POST",
      body: { token },
    });
  },

  organizations() {
    return request<Organization[]>("/api/v1/orgs");
  },

  previewInvitation(token: string) {
    return request<InvitationPreview>(`/api/v1/auth/invitations/${encodeURIComponent(token)}`);
  },

  acceptInvitation(token: string) {
    return request<Membership>("/api/v1/auth/invitations/accept", {
      method: "POST",
      body: { token },
    });
  },

  me() {
    return request<User>("/api/v1/me");
  },

  logout() {
    return request<void>("/api/v1/auth/logout", { method: "POST" });
  },

  listImports(organizationId: string, options: { cursor?: string; limit?: number } = {}) {
    const params = new URLSearchParams();
    if (options.cursor) params.set("cursor", options.cursor);
    if (options.limit) params.set("limit", String(options.limit));
    const query = params.size ? `?${params.toString()}` : "";
    return request<ImportList>(
      `/api/v1/orgs/${encodeURIComponent(organizationId)}/imports${query}`,
    );
  },

  createImport(organizationId: string, originalFilename: string) {
    return request<CreateImportResult>(
      `/api/v1/orgs/${encodeURIComponent(organizationId)}/imports`,
      { method: "POST", body: { original_filename: originalFilename } },
    );
  },

  uploadImportFile(upload: PresignedUpload, file: File) {
    return uploadFile(upload, file);
  },

  confirmImportUpload(organizationId: string, batchId: string, allowDuplicate = false) {
    return request<ImportBatch>(
      `/api/v1/orgs/${encodeURIComponent(organizationId)}/imports/${encodeURIComponent(batchId)}/uploaded`,
      { method: "POST", body: { allow_duplicate: allowDuplicate } },
    );
  },

  getImport(organizationId: string, batchId: string) {
    return request<ImportBatch>(
      `/api/v1/orgs/${encodeURIComponent(organizationId)}/imports/${encodeURIComponent(batchId)}`,
    );
  },

  getImportPreview(organizationId: string, batchId: string) {
    return request<ImportPreview>(
      `/api/v1/orgs/${encodeURIComponent(organizationId)}/imports/${encodeURIComponent(batchId)}/preview`,
    );
  },

  saveImportMapping(
    organizationId: string,
    batchId: string,
    mapping: ImportMappingDocument,
  ) {
    return request<ImportBatch>(
      `/api/v1/orgs/${encodeURIComponent(organizationId)}/imports/${encodeURIComponent(batchId)}/mapping`,
      { method: "PUT", body: mapping },
    );
  },

  validateImport(organizationId: string, batchId: string) {
    return request<ImportBatch>(
      `/api/v1/orgs/${encodeURIComponent(organizationId)}/imports/${encodeURIComponent(batchId)}/validate`,
      { method: "POST" },
    );
  },

  listImportIssues(
    organizationId: string,
    batchId: string,
    options: { cursor?: string; limit?: number } = {},
  ) {
    const params = new URLSearchParams();
    if (options.cursor) params.set("cursor", options.cursor);
    if (options.limit) params.set("limit", String(options.limit));
    const query = params.size ? `?${params.toString()}` : "";
    return request<ImportIssues>(
      `/api/v1/orgs/${encodeURIComponent(organizationId)}/imports/${encodeURIComponent(batchId)}/issues${query}`,
    );
  },

  getImportIssueExport(organizationId: string, batchId: string) {
    return request<{ url: string }>(
      `/api/v1/orgs/${encodeURIComponent(organizationId)}/imports/${encodeURIComponent(batchId)}/issues/export`,
    );
  },

  commitImport(organizationId: string, batchId: string, idempotencyKey: string) {
    return request<ImportBatch>(
      `/api/v1/orgs/${encodeURIComponent(organizationId)}/imports/${encodeURIComponent(batchId)}/commit`,
      { method: "POST", headers: { "Idempotency-Key": idempotencyKey } },
    );
  },

  cancelImport(organizationId: string, batchId: string) {
    return request<ImportBatch>(
      `/api/v1/orgs/${encodeURIComponent(organizationId)}/imports/${encodeURIComponent(batchId)}/cancel`,
      { method: "POST" },
    );
  },

  listCandidates(
    organizationId: string,
    options: {
      cursor?: string;
      limit?: number;
      band?: ScoreBand;
      status?: CandidateWorkflowStatus;
    } = {},
  ) {
    const params = new URLSearchParams();
    if (options.cursor) params.set("cursor", options.cursor);
    if (options.limit) params.set("limit", String(options.limit));
    if (options.band) params.set("band", options.band);
    if (options.status) params.set("status", options.status);
    const query = params.size ? `?${params.toString()}` : "";
    return request<CandidateList>(
      `/api/v1/orgs/${encodeURIComponent(organizationId)}/rework${query}`,
    );
  },

  getCandidate(organizationId: string, candidateId: string) {
    return request<CandidateDetail>(
      `/api/v1/orgs/${encodeURIComponent(organizationId)}/rework/${encodeURIComponent(candidateId)}`,
    );
  },

  listReviewHistory(organizationId: string, candidateId: string) {
    return request<ReworkReview[]>(
      `/api/v1/orgs/${encodeURIComponent(organizationId)}/rework/${encodeURIComponent(candidateId)}/reviews`,
    );
  },

  listReviewCategories(organizationId: string) {
    return request<ReworkCategory[]>(
      `/api/v1/orgs/${encodeURIComponent(organizationId)}/settings/categories`,
    );
  },

  listRootCauses(organizationId: string) {
    return request<RootCause[]>(
      `/api/v1/orgs/${encodeURIComponent(organizationId)}/settings/root-causes`,
    );
  },

  createReview(organizationId: string, candidateId: string, input: CreateReviewInput) {
    return request<ReworkReview>(
      `/api/v1/orgs/${encodeURIComponent(organizationId)}/rework/${encodeURIComponent(candidateId)}/review`,
      { method: "POST", body: input },
    );
  },
};

async function uploadFile(upload: PresignedUpload, file: File): Promise<void> {
  const headers = new Headers(upload.headers);
  let response: Response;
  try {
    response = await fetch(upload.url, {
      method: upload.method,
      headers,
      body: file,
    });
  } catch {
    throw new ApiError("The file upload could not reach storage. Please try again.", 0);
  }

  if (!response.ok) {
    throw new ApiError("Storage rejected the file upload. Please request a new upload URL.", response.status);
  }
}

export function getApiErrorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  return "Something went wrong. Please try again.";
}
