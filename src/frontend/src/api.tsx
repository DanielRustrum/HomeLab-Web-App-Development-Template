import type {
  EndpointKey,
  EndpointResponse,
  EndpointBody,
  EndpointQuery,
  EndpointPath,
} from "./api.types";

export * as Contracts from './api.contracts'


/** ---------------- Core fetch helper ---------------- */

export type ApiHelperOptions = Omit<RequestInit, "body" | "signal"> & {
  body?: unknown;
  /** Request timeout (ms). Default 15s */
  timeoutMs?: number;
  /** If true, return text when response isn't JSON. Default false */
  allowText?: boolean;
  /** AbortSignal passthrough */
  signal?: AbortSignal;
};

export class ApiError extends Error {
  name = "ApiError";
  status: number;
  statusText: string;
  url: string;
  bodyText?: string;

  constructor(opts: { status: number; statusText: string; url: string; bodyText?: string }) {
    super(opts.bodyText || `HTTP ${opts.status} ${opts.statusText}`);
    this.status = opts.status;
    this.statusText = opts.statusText;
    this.url = opts.url;
    this.bodyText = opts.bodyText;
  }
}

function joinApi(path: string): string {
  const base = "/api";
  const p = path.startsWith("/") ? path : `/${path}`;
  return `${base}${p}`;
}

export async function apiHelper<T = unknown>(path: string, options: ApiHelperOptions = {}): Promise<T> {
  const url = joinApi(path);

  const timeoutMs = options.timeoutMs ?? 15_000;

  const controller = new AbortController();
  const timeoutId = setTimeout(
    () => controller.abort(new DOMException("Timeout", "AbortError")),
    timeoutMs
  );

  if (options.signal) {
    if (options.signal.aborted) controller.abort(options.signal.reason);
    else {
      options.signal.addEventListener(
        "abort",
        () => controller.abort((options.signal as AbortSignal).reason),
        { once: true }
      );
    }
  }

  const method = (options.method || "GET").toUpperCase();
  const hasBodyMethod = !["GET", "HEAD"].includes(method);
  const hasBody = options.body !== undefined;

  const body = options.body;

  const isFormLike =
    (typeof FormData !== "undefined" && body instanceof FormData) ||
    (typeof Blob !== "undefined" && body instanceof Blob) ||
    (typeof ArrayBuffer !== "undefined" && body instanceof ArrayBuffer) ||
    (typeof URLSearchParams !== "undefined" && body instanceof URLSearchParams);

  const isJsonBody =
    hasBody &&
    !isFormLike &&
    (body === null ||
      typeof body === "object" ||
      typeof body === "string" ||
      typeof body === "number" ||
      typeof body === "boolean");

  const headers = new Headers(options.headers);
  if (hasBodyMethod && hasBody && isJsonBody && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  if (!headers.has("Accept")) headers.set("Accept", "application/json");

  try {
    const res = await fetch(url, {
      ...options,
      headers,
      signal: controller.signal,
      body:
        hasBodyMethod && hasBody
          ? headers.get("Content-Type")?.includes("application/json")
            ? JSON.stringify(body)
            : (body as any)
          : undefined,
    });

    if (!res.ok) {
      let bodyText = "";
      try {
        bodyText = await res.text();
        if (bodyText.length > 20_000) bodyText = bodyText.slice(0, 20_000) + "…";
      } catch {}
      throw new ApiError({ status: res.status, statusText: res.statusText, url: res.url || url, bodyText });
    }

    if (res.status === 204 || res.status === 205) return undefined as T;

    const ct = (res.headers.get("content-type") || "").toLowerCase();

    if (ct.includes("application/json") || ct.includes("+json")) {
      return (await res.json()) as T;
    }

    if (options.allowText) {
      return (await res.text()) as unknown as T;
    }

    return undefined as T;
  } finally {
    clearTimeout(timeoutId);
  }
}

/** ---------------- Typed endpoint API ---------------- */

type MethodSuffix = "get" | "post" | "put" | "patch" | "delete" | "head" | "options";

type GetEndpoints = Extract<EndpointKey, `${string}.get`>;
type BodyEndpoints = Exclude<EndpointKey, GetEndpoints>;

type PathParamsOption<K extends EndpointKey> =
  EndpointPath<K> extends never
    ? { params?: never }
    : { params: { [P in keyof EndpointPath<K>]: string | number } };

type QueryParamsOption<K extends EndpointKey> =
  EndpointQuery<K> extends never
    ? { query?: never }
    : { query?: EndpointQuery<K> };

export type ApiEndpointOptions<K extends EndpointKey> =
  Omit<ApiHelperOptions, "body"> &
  PathParamsOption<K> &
  QueryParamsOption<K>;

function endpointToPath(endpoint: string, params?: Record<string, string | number>): string {
  const lastDot = endpoint.lastIndexOf(".");
  const pathPart = lastDot >= 0 ? endpoint.slice(0, lastDot) : endpoint;

  const segs = pathPart.split(".").filter(Boolean);
  const built = segs.map((seg) => {
    const m = seg.match(/^\[(.+)\]$/);
    if (!m) return encodeURIComponent(seg);

    const key = m[1];
    const val = params?.[key];
    if (val === undefined || val === null) {
      throw new Error(`Missing path param "${key}" for endpoint "${endpoint}"`);
    }
    return encodeURIComponent(String(val));
  });

  return `/${built.join("/")}`;
}

function endpointToMethod(endpoint: string): string {
  const lastDot = endpoint.lastIndexOf(".");
  const suffix = lastDot >= 0 ? endpoint.slice(lastDot + 1) : "";
  switch (suffix as MethodSuffix) {
    case "get": return "GET";
    case "post": return "POST";
    case "put": return "PUT";
    case "patch": return "PATCH";
    case "delete": return "DELETE";
    case "head": return "HEAD";
    case "options": return "OPTIONS";
    default: return "GET";
  }
}

function buildQueryString(query: unknown): string {
  if (!query || typeof query !== "object") return "";

  const usp = new URLSearchParams();

  for (const [key, value] of Object.entries(query as Record<string, unknown>)) {
    if (value === undefined || value === null) continue;

    const add = (v: unknown) => {
      if (v === undefined || v === null) return;
      if (v instanceof Date) usp.append(key, v.toISOString());
      else if (typeof v === "object") usp.append(key, JSON.stringify(v));
      else usp.append(key, String(v));
    };

    if (Array.isArray(value)) {
      for (const v of value) add(v);
    } else {
      add(value);
    }
  }

  const s = usp.toString();
  return s ? `?${s}` : "";
}

/**
 * - GET:  api("x.get", options?)
 * - BODY: api("x.post", body, options?)
 */
export function api<K extends GetEndpoints>(
  endpoint: K,
  options?: ApiEndpointOptions<K>
): Promise<EndpointResponse<K>>;

export function api<K extends BodyEndpoints>(
  endpoint: K,
  body: EndpointBody<K>,
  options?: ApiEndpointOptions<K>
): Promise<EndpointResponse<K>>;

export async function api<K extends EndpointKey>(
  endpoint: K,
  a?: any,
  b?: any
): Promise<EndpointResponse<K>> {
  const ep = String(endpoint);
  const method = endpointToMethod(ep);

  let body: unknown = undefined;
  let options: ApiEndpointOptions<K> = {} as any;

  if (method === "GET" || method === "HEAD") {
    options = (a ?? {}) as any;
  } else {
    body = a;
    options = (b ?? {}) as any;
  }

  const { params, query, ...rest } = options as any;
  const path = endpointToPath(ep, params);
  const qs = buildQueryString(query);

  return apiHelper<EndpointResponse<K>>(`${path}${qs}`, { ...rest, method, body });
}