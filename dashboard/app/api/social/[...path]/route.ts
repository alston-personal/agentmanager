import { readFileSync } from "node:fs";
import { NextRequest } from "next/server";

const UPSTREAM = "http://127.0.0.1:8771";
const PUBLIC_CALLBACK_PATH = "/dashboard/api/social/v1/social/oauth/threads/callback";
const INTERNAL_CALLBACK_PATH = "/v1/social/oauth/threads/callback";
const INTERNAL_START_PATH = "/v1/social/oauth/threads/start";
const THREADS_DEAUTHORIZE_PATH = "/v1/social/webhooks/threads/deauthorize";
const THREADS_DATA_DELETION_PATH = "/v1/social/webhooks/threads/data-deletion";
const THREADS_DATA_DELETION_STATUS_PATH = "/v1/social/webhooks/threads/data-deletion/status";
const SOCIAL_RUNTIME_ENV_FILE = process.env.AGENTOS_SOCIAL_RUNTIME_ENV_FILE || "/home/ubuntu/.config/agentos/social-runtime.env";
const GALAXY_PRODUCT_ID = "galaxy";
const GALAXY_STATUS_OPERATIONS = new Set(["status", "identity.read", "post.read", "replies.read"]);

const ALLOWED: Record<string, Set<string>> = {
  GET: new Set(["/healthz", INTERNAL_START_PATH, INTERNAL_CALLBACK_PATH, THREADS_DATA_DELETION_STATUS_PATH]),
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

function parseEnvValue(raw: string): string {
  const value = raw.trim();
  if (value.length >= 2 && ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'")))) {
    return value.slice(1, -1);
  }
  return value;
}

function galaxyProductKey(): string {
  const text = readFileSync(SOCIAL_RUNTIME_ENV_FILE, "utf8");
  const line = text.split(/\r?\n/).find((entry) => entry.startsWith("AGENTOS_SOCIAL_PRODUCTS_JSON="));
  if (!line) throw new Error("social_product_registry_unavailable");
  const raw = parseEnvValue(line.slice("AGENTOS_SOCIAL_PRODUCTS_JSON=".length));
  const registry = JSON.parse(raw) as Record<string, { api_key?: unknown }>;
  const key = String(registry?.[GALAXY_PRODUCT_ID]?.api_key || "");
  if (!key) throw new Error("galaxy_product_not_registered");
  return key;
}

function browserBridgeAllowed(path: string, contentType: string | null, body: ArrayBuffer | undefined): boolean {
  if (!body || !contentType?.toLowerCase().startsWith("application/json")) return false;
  if (path !== "/v1/social/status" && path !== "/v1/social/connect") return false;
  try {
    const value = JSON.parse(new TextDecoder().decode(body)) as Record<string, unknown>;
    if (value.product_id !== GALAXY_PRODUCT_ID || value.platform !== "threads") return false;
    const operation = String(value.operation || "");
    return path === "/v1/social/connect" ? operation === "connect" : GALAXY_STATUS_OPERATIONS.has(operation);
  } catch {
    return false;
  }
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
      { status: 404, headers: { "cache-control": "no-store", "x-agentos-social-gateway": "v0.2" } },
    );
  }

  const incoming = new URL(request.url);
  const target = new URL(path + incoming.search, UPSTREAM);
  const headers = new Headers({ Accept: "application/json" });
  const contentType = request.headers.get("content-type");
  const acceptanceId = request.headers.get("x-agentos-acceptance-id");
  const body = method !== "GET" && method !== "HEAD" ? await request.arrayBuffer() : undefined;
  if (contentType) headers.set("content-type", contentType);
  if (acceptanceId) headers.set("x-agentos-acceptance-id", acceptanceId);

  const suppliedProductKey = request.headers.get("x-agentos-product-key");
  if (suppliedProductKey) {
    headers.set("x-agentos-product-key", suppliedProductKey);
  } else if (browserBridgeAllowed(path, contentType, body)) {
    try {
      headers.set("x-agentos-product-key", galaxyProductKey());
    } catch {
      return Response.json(
        { ok: false, error: "Galaxy social bridge unavailable" },
        { status: 503, headers: { "cache-control": "no-store", "x-agentos-social-gateway": "v0.2" } },
      );
    }
  }

  if (method === "GET" && path === INTERNAL_CALLBACK_PATH) {
    const cookie = request.headers.get("cookie");
    if (cookie) headers.set("cookie", cookie);
  }

  const init: RequestInit = { method, headers, cache: "no-store", redirect: "manual" };
  if (body) init.body = body;

  try {
    const upstream = await fetch(target, init);
    const responseBody = await upstream.arrayBuffer();
    const responseHeaders = new Headers({
      "content-type": upstream.headers.get("content-type") || "application/json; charset=utf-8",
      "cache-control": "no-store",
      "x-agentos-social-gateway": "v0.2",
    });
    const location = upstream.headers.get("location");
    if (location) responseHeaders.set("location", location);
    const setCookie = upstream.headers.get("set-cookie");
    if (setCookie) responseHeaders.set("set-cookie", rewriteCookiePath(setCookie));
    return new Response(responseBody, { status: upstream.status, headers: responseHeaders });
  } catch (error) {
    return Response.json(
      { ok: false, error: `Social upstream unavailable: ${error instanceof Error ? error.message : "unknown"}` },
      { status: 502, headers: { "cache-control": "no-store", "x-agentos-social-gateway": "v0.2" } },
    );
  }
}

export async function GET(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  return proxy(request, context);
}

export async function POST(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  return proxy(request, context);
}
