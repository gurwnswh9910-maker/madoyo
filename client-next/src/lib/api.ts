const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("auth_token");
}

export async function apiFetch(path: string, options: RequestInit = {}) {
  const token = getToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(`${API}${path}`, { ...options, headers });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(body || `HTTP ${res.status}`);
  }
  return res.json();
}

export async function apiPost(path: string, body: unknown) {
  return apiFetch(path, { method: "POST", body: JSON.stringify(body) });
}

export async function apiGet(path: string) {
  return apiFetch(path, { method: "GET" });
}

/** 파일 업로드용 (multipart) */
export async function apiUpload(path: string, formData: FormData) {
  const token = getToken();
  const headers: Record<string, string> = {};
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(`${API}${path}`, {
    method: "POST",
    headers,
    body: formData,
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

/** 비동기 작업 폴링 */
export async function pollTask(taskId: string, onProgress?: (status: string) => void): Promise<unknown> {
  const maxAttempts = 120;
  for (let i = 0; i < maxAttempts; i++) {
    const data = await apiGet(`/tasks/${taskId}`);
    if (data.status === "SUCCESS") return data.result;
    if (data.status === "FAILURE") throw new Error(data.error || "작업 실패");
    if (onProgress) onProgress(data.status);
    await new Promise((r) => setTimeout(r, 2000));
  }
  throw new Error("작업 시간 초과");
}

/** 프론트 에러 자동 수집 */
export function reportBug(errorType: string, message: string, context?: Record<string, unknown>) {
  try {
    apiPost("/bug-report", { error_type: errorType, message, context }).catch(() => {});
  } catch {}
}
