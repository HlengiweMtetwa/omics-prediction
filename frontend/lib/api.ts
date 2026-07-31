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

export interface Site {
  id: string;
  project_id: string;
  name: string;
  country: string | null;
  region: string | null;
  latitude: number | null;
  longitude: number | null;
  site_type: string | null;
  created_at: string;
}

export interface SamplingEvent {
  id: string;
  site_id: string;
  collected_at: string;
  sample_matrix: string | null;
  collector: string | null;
  notes: string | null;
  created_at: string;
}

export interface Sample {
  id: string;
  sampling_event_id: string;
  sample_type: string | null;
  replicate: number;
  lab_identifier: string | null;
  analysis_status: string;
  created_at: string;
}

export interface Job {
  id: string;
  project_id: string;
  pipeline_name: string;
  status: string;
  error_message: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
}

export interface Upload {
  id: string;
  sample_id: string;
  original_filename: string;
  file_type: string;
  omics_type: string | null;
  size_bytes: number;
  checksum_sha256: string;
  validation_status: string;
  created_at: string;
}

export interface Report {
  id: string;
  project_id: string;
  report_type: string;
  content_hash: string;
  created_at: string;
}

export interface MLModel {
  id: string;
  project_id: string;
  job_id: string;
  name: string;
  algorithm: string;
  target_variable: string;
  metrics: string | null;
  intended_use: string;
  prohibited_use: string;
  approval_status: string;
  registered_by: string;
  approved_by: string | null;
  created_at: string;
  approved_at: string | null;
}

async function requestText(path: string, token: string): Promise<string> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) {
    throw new ApiError(res.status, `Request failed with status ${res.status}`);
  }
  return res.text();
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

  getProject: (token: string, projectId: string) =>
    request<Project>(`/api/v1/projects/${projectId}`, { token }),

  listSites: (token: string, projectId: string) =>
    request<Site[]>(`/api/v1/projects/${projectId}/sites`, { token }),

  createSite: (
    token: string,
    projectId: string,
    payload: {
      name: string;
      country?: string;
      region?: string;
      latitude?: number;
      longitude?: number;
      site_type?: string;
    }
  ) =>
    request<Site>(`/api/v1/projects/${projectId}/sites`, {
      method: "POST",
      token,
      body: JSON.stringify(payload),
    }),

  listSamplingEvents: (token: string, siteId: string) =>
    request<SamplingEvent[]>(`/api/v1/sites/${siteId}/sampling-events`, { token }),

  createSamplingEvent: (
    token: string,
    siteId: string,
    payload: {
      collected_at: string;
      sample_matrix?: string;
      collector?: string;
      notes?: string;
    }
  ) =>
    request<SamplingEvent>(`/api/v1/sites/${siteId}/sampling-events`, {
      method: "POST",
      token,
      body: JSON.stringify(payload),
    }),

  listSamples: (token: string, eventId: string) =>
    request<Sample[]>(`/api/v1/sampling-events/${eventId}/samples`, { token }),

  createSample: (
    token: string,
    eventId: string,
    payload: { sample_type?: string; replicate?: number; lab_identifier?: string }
  ) =>
    request<Sample>(`/api/v1/sampling-events/${eventId}/samples`, {
      method: "POST",
      token,
      body: JSON.stringify(payload),
    }),

  listJobs: (token: string, projectId: string) =>
    request<Job[]>(`/api/v1/projects/${projectId}/jobs`, { token }),

  createJob: (token: string, projectId: string, pipelineName?: string) =>
    request<Job>(`/api/v1/projects/${projectId}/jobs`, {
      method: "POST",
      token,
      body: JSON.stringify({ pipeline_name: pipelineName || "synthetic_omics_demo" }),
    }),

  getJob: (token: string, jobId: string) => request<Job>(`/api/v1/jobs/${jobId}`, { token }),

  listReports: (token: string, projectId: string) =>
    request<Report[]>(`/api/v1/projects/${projectId}/reports`, { token }),

  createReport: (token: string, projectId: string) =>
    request<Report>(`/api/v1/projects/${projectId}/reports`, { method: "POST", token }),

  getReportContent: (token: string, reportId: string) =>
    requestText(`/api/v1/reports/${reportId}/content`, token),

  listModels: (token: string, projectId: string) =>
    request<MLModel[]>(`/api/v1/projects/${projectId}/models`, { token }),

  registerModel: (token: string, projectId: string, payload: { job_id: string; name?: string }) =>
    request<MLModel>(`/api/v1/projects/${projectId}/models`, {
      method: "POST",
      token,
      body: JSON.stringify(payload),
    }),

  approveModel: (token: string, modelId: string) =>
    request<MLModel>(`/api/v1/models/${modelId}/approve`, { method: "POST", token }),

  listUploads: (token: string, sampleId: string) =>
    request<Upload[]>(`/api/v1/samples/${sampleId}/uploads`, { token }),

  createUpload: (token: string, sampleId: string, file: File, omicsType?: string) => {
    const form = new FormData();
    form.append("file", file);
    const query = omicsType ? `?omics_type=${encodeURIComponent(omicsType)}` : "";
    return request<Upload>(`/api/v1/samples/${sampleId}/uploads${query}`, {
      method: "POST",
      token,
      body: form,
    });
  },
};
