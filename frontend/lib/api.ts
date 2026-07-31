export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(
  path: string,
  options: RequestInit & { token?: string | null } = {}
): Promise<T> {
  const { token, headers, ...rest } = options;
  const finalHeaders: Record<string, string> = {
    ...(headers as Record<string, string>),
  };
  if (token) {
    finalHeaders["Authorization"] = `Bearer ${token}`;
  }
  if (rest.body && !(rest.body instanceof FormData)) {
    finalHeaders["Content-Type"] = "application/json";
  }

  const res = await fetch(`${API_BASE_URL}${path}`, {
    ...rest,
    headers: finalHeaders,
  });

  if (!res.ok) {
    let detail = `Request failed with status ${res.status}`;
    try {
      const body = await res.json();
      if (body?.detail) detail = body.detail;
    } catch {
      // response body wasn't JSON - keep the generic message
    }
    throw new ApiError(res.status, detail);
  }

  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export interface User {
  id: string;
  full_name: string;
  email: string;
  role: string;
  institution: string | null;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
}

export interface Project {
  id: string;
  title: string;
  description: string | null;
  disease_focus: string | null;
  amr_focus: boolean;
  status: string;
  created_at: string;
}

export interface ApprovedModelSummary {
  id: string;
  name: string;
  algorithm: string;
}

export interface ActivityEvent {
  action: string;
  resource_type: string | null;
  details: string | null;
  created_at: string;
}

export interface DashboardSummary {
  active_projects: number;
  sites: number;
  samples: number;
  jobs_queued: number;
  jobs_running: number;
  jobs_completed: number;
  jobs_failed: number;
  approved_models: ApprovedModelSummary[];
  recent_activity: ActivityEvent[];
}

export const api = {
  register: (payload: {
    full_name: string;
    email: string;
    password: string;
    institution?: string;
    role: string;
  }) =>
    request<User>("/api/v1/auth/register", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  login: (email: string, password: string) =>
    request<TokenResponse>("/api/v1/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),

  me: (token: string) => request<User>("/api/v1/auth/me", { token }),

  dashboard: (token: string) =>
    request<DashboardSummary>("/api/v1/dashboard", { token }),

  listProjects: (token: string) =>
    request<Project[]>("/api/v1/projects", { token }),

  createProject: (
    token: string,
    payload: {
      title: string;
      description?: string;
      disease_focus?: string;
      amr_focus?: boolean;
    }
  ) =>
    request<Project>("/api/v1/projects", {
      method: "POST",
      token,
      body: JSON.stringify(payload),
    }),
};
