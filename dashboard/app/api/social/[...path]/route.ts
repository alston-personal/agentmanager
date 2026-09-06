import { NextRequest } from "next/server";

const UPSTREAM = "http://127.0.0.1:8771";
const PUBLIC_CALLBACK_PATH = "/dashboard/api/social/v1/social/oauth/threads/callback";
const INTERNAL_CALLBACK_PATH = "/v1/social/oauth/threads/callback";
const THREADS_DEAUTHORIZE_PATH = "/v1/social/webhooks/threads/deauthorize";
const THREADS_DATA_DELETION_PATH = "/v1/social/webhooks/threads/data-deletion";
const THREADS_DATA_DELETION_STATUS_PATH = "/v1/social/webhooks/threads/data-deletion/status";

const ALLOWED: Record<string, Set<string>> = {
  GET: new Set(["/healthz", INTERNAL_CALLBACK_PATH, THREADS_DATA_DELETION_STATUS_PATH]),
  POST: new Set([
    "/v1/social/status",
    "/v1/social/connect",
    "/v1/social/publish",
    "/v1/social/reply",
    "/v1/social/disconnect",
    THREADS_DEAUTHORIZE_PATH,
    THREADS_DATA_DELETION_PATH,
  ]),
};

function safePath(parts: string[]): string {
  const path = "/" + parts.map((part) => encodeURIComponent(decodeURIComponent(part))).join("/");
  if (path.includes("..")) throw new Error("invalid social path");
  return path;
}

function rewriteCookiePath(value: string): string {
  return value.replace(
    /Path=\/v1\/social\/oauth\/threads\/callback(?=;|$)/i,
    `Path=${PUBLIC_CALLBACK_PATH}`,
  );
}

async function proxy(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
) {
  const method = request.method.toUpperCase();
  const { path: parts } = await context.params;
  let path: string;
  try {
    path = safePath(parts || []);
  } catch {
    return Response.json({ ok: false, error: "Social gateway path invalid" }, { status: 404 });
  }
  if (!ALLOWED[method]?.has(path)) {
    return Response.json(
      { ok: false, error: "Social gateway route not allowlisted" },
      { status: 404, headers: { "cache-control": "no-store", "x-agentos-social-gateway": "v0.1" } },
    );
  }

  const incoming = new URL(request.url);
  const target = new URL(path + incoming.search, UPSTREAM);
  const headers = new Headers({ Accept: "application/json" });
  const contentType = request.headers.get("content-type");
  const productKey = request.headers.get("x-agentos-product-key");
  const acceptanceId = request.headers.get("x-agentos-acceptance-id");
  if (contentType) headers.set("content-type", contentType);
  if (productKey) headers.set("x-agentos-product-key", productKey);
  if (acceptanceId) headers.set("x-agentos-acceptance-id", acceptanceId);
  if (method === "GET" && path === INTERNAL_CALLBACK_PATH) {
    const cookie = request.headers.get("cookie");
    if (cookie) headers.set("cookie", cookie);
  }

  const init: RequestInit = { method, headers, cache: "no-store", redirect: "manual" };
  if (method !== "GET" && method !== "HEAD") init.body = await request.arrayBuffer();

  try {
    const upstream = await fetch(target, init);
    const body = await upstream.arrayBuffer();
    const responseHeaders = new Headers({
      "content-type": upstream.headers.get("content-type") || "application/json; charset=utf-8",
      "cache-control": "no-store",
      "x-agentos-social-gateway": "v0.1",
    });
    const location = upstream.headers.get("location");
    if (location) responseHeaders.set("location", location);
    const setCookie = upstream.headers.get("set-cookie");
    if (setCookie) responseHeaders.set("set-cookie", rewriteCookiePath(setCookie));
    return new Response(body, { status: upstream.status, headers: responseHeaders });
  } catch (error) {
    return Response.json(
      { ok: false, error: `Social upstream unavailable: ${error instanceof Error ? error.message : "unknown"}` },
      { status: 502, headers: { "cache-control": "no-store", "x-agentos-social-gateway": "v0.1" } },
    );
  }
}

export async function GET(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  return proxy(request, context);
}

export async function POST(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  return proxy(request, context);
}
