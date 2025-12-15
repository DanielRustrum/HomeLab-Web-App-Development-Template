type ApiOptions = Omit<RequestInit, "body"> & { body?: unknown };

function joinApi(path: string) {
    const p = path.startsWith("/") ? path : `/${path}`;
    return "/api" + p
}

export async function api<T = unknown>(path: string, options: ApiOptions = {}): Promise<T> {
  const res = await fetch(joinApi(path), {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
  });

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(text || `HTTP ${res.status}`);
  }

  // Allow empty responses
  const ct = res.headers.get("content-type") || "";
  if (!ct.includes("application/json")) return undefined as T;
  return (await res.json()) as T;
}