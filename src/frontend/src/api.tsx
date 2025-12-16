import { Endpoints } from "./api.types";
export type ApiOptions = Omit<RequestInit, "body"> & {
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
    // Replace with your existing joinApi. This is just a placeholder.
    const base = "/api";
    const p = path.startsWith("/") ? path : `/${path}`;
    return `${base}${p}`;
}

export async function apiHelper<T = unknown>(path: string, options: ApiOptions = {}): Promise<T> {
    const url = joinApi(path);

    // Timeout + abort wiring
    const timeoutMs = options.timeoutMs ?? 15_000;
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(new DOMException("Timeout", "AbortError")), timeoutMs);

    // If caller provided a signal, abort this request too
    if (options.signal) {
        if (options.signal.aborted) controller.abort(options.signal.reason);
        else options.signal.addEventListener("abort", () => controller.abort(options.signal!.reason), { once: true });
    }

    const method = (options.method || "GET").toUpperCase();

    // Only attach JSON body for methods that allow it
    const hasBodyMethod = !["GET", "HEAD"].includes(method);
    const hasBody = options.body !== undefined;

    // Avoid forcing JSON content-type when sending FormData/Blob/etc.
    const isJsonBody =
        hasBody &&
        (options.body === null ||
            typeof options.body === "object" ||
            typeof options.body === "string" ||
            typeof options.body === "number" ||
            typeof options.body === "boolean");

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
                        ? JSON.stringify(options.body)
                        : (options.body as any) // allow FormData/Blob/etc. if you pass it
                    : undefined,
        });

        if (!res.ok) {
            // Try to read error payload safely (cap size to avoid huge throws)
            let bodyText = "";
            try {
                bodyText = await res.text();
                if (bodyText.length > 20_000) bodyText = bodyText.slice(0, 20_000) + "…";
            } catch { }
            throw new ApiError({ status: res.status, statusText: res.statusText, url: res.url || url, bodyText });
        }

        // 204/205 or empty body → undefined
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

export async function api<K extends keyof Endpoints>(
    endpoint: K,
    options: ApiOptions = {}
): Promise<Endpoints[K]> {
    return apiHelper<Endpoints[K]>(String(endpoint).replace(".", "/"), options);
}