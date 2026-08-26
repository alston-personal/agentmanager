import { NextRequest } from "next/server";

const UPSTREAM = "http://127.0.0.1:8780";

const ALLOWED: Record<string, Set<string>> = {
  GET: new Set(["/v1/health", "/v1/tasks"]),
  POST: new Set([
    "/v1/join/request",
    "/v1/join/status",
    "/v1/join/claim",
    "/v1/enroll",
    "/v1/heartbeat",
    "/v1/receipts",
  ]),
};

function safePath(parts: string[]): string {
  const path = "/" + parts.map((part) => encodeURIComponent(decodeURIComponent(part))).join("/");
  if (!path.startsWith("/v1/")) throw new Error("invalid Realm path");
  return path;
}

async function proxy(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
) {
  const method = request.method.toUpperCase();
  const { path: parts } = await context.params;
  const path = safePath(parts || []);
  if (!ALLOWED[method]?.has(path)) {
    return Response.json({ ok: false, error: "Realm gateway route not allowlisted" }, { status: 404 });
  }

  const incoming = new URL(request.url);
  const target = new URL(path + incoming.search, UPSTREAM);
  const headers = new Headers({ Accept: "application/json" });
  const authorization = request.headers.get("authorization");
  const contentType = request.headers.get("content-type");
  if (authorization) headers.set("authorization", authorization);
  if (contentType) headers.set("content-type", contentType);

  const init: RequestInit = { method, headers, cache: "no-store", redirect: "manual" };
  if (method !== "GET" && method !== "HEAD") init.body = await request.arrayBuffer();

  try {
    const upstream = await fetch(target, init);
    const body = await upstream.arrayBuffer();
    return new Response(body, {
      status: upstream.status,
      headers: {
        "content-type": upstream.headers.get("content-type") || "application/json; charset=utf-8",
        "cache-control": "no-store",
        "x-agentos-realm-gateway": "v0.1",
      },
    });
  } catch (error) {
    return Response.json(
      { ok: false, error: `Realm upstream unavailable: ${error instanceof Error ? error.message : "unknown"}` },
      { status: 502, headers: { "cache-control": "no-store", "x-agentos-realm-gateway": "v0.1" } },
    );
  }
}

export async function GET(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  return proxy(request, context);
}

export async function POST(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  return proxy(request, context);
}
