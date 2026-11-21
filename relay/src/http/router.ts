import type { IncomingMessage, ServerResponse } from "node:http";
import type { DatabaseSync } from "node:sqlite";
import type { WhatsAppTransport } from "../transport/WhatsAppTransport.ts";
import type { Logger } from "../log/Logger.ts";
import type { RateLimiter } from "../domain/limiter.ts";
import type { SosMemoryStore } from "../store/sosMemory.ts";
import { checkAuth, validateInstallIdHeader } from "./auth.ts";
import { parseJsonBody } from "./bodyParser.ts";
import { validateRegisterPayload, validateSosPayload, isValidUuid } from "../domain/validate.ts";
import { handleRegister } from "../service/registerService.ts";
import { handleSos } from "../service/sosService.ts";
import { deleteInstall } from "../store/db.ts";

export interface RouterDependencies {
  apiKey: string;
  tz: string;
  db: DatabaseSync;
  memoryStore: SosMemoryStore;
  transport: WhatsAppTransport;
  keyLimiter: RateLimiter;
  sosLimiter: RateLimiter;
  logger: Logger;
  clock?: () => number;
}

const KEY_RATE_LIMIT = 60;
const ONE_MINUTE_MS = 60 * 1000;

function sendJson(
  res: ServerResponse,
  status: number,
  body: unknown,
  extraHeaders?: Record<string, string>,
): void {
  const payload = JSON.stringify(body);
  res.writeHead(status, {
    "content-type": "application/json",
    ...extraHeaders,
  });
  res.end(payload);
}

async function handleRegisterRoute(
  req: IncomingMessage,
  res: ServerResponse,
  installId: string,
  deps: RouterDependencies,
): Promise<void> {
  const parsed = await parseJsonBody(req);
  if (!parsed.ok) {
    sendJson(res, 400, { error: parsed.error });
    return;
  }
  const validated = validateRegisterPayload(parsed.data);
  if (!validated.ok) {
    sendJson(res, 400, { error: validated.error });
    return;
  }
  const result = await handleRegister({
    installId,
    driverName: validated.data.driverName,
    contacts: validated.data.contacts,
    db: deps.db,
    transport: deps.transport,
    logger: deps.logger,
    now: deps.clock ? deps.clock() : Date.now(),
  });
  sendJson(res, 200, result);
}

async function handleSosRoute(
  req: IncomingMessage,
  res: ServerResponse,
  installId: string,
  deps: RouterDependencies,
): Promise<void> {
  const parsed = await parseJsonBody(req);
  if (!parsed.ok) {
    sendJson(res, 400, { error: parsed.error });
    return;
  }
  const validated = validateSosPayload(parsed.data);
  if (!validated.ok) {
    sendJson(res, 400, { error: validated.error });
    return;
  }
  const result = await handleSos({
    installId,
    clientId: validated.data.clientId,
    kind: validated.data.kind,
    tCrash: validated.data.tCrash,
    lat: validated.data.lat,
    lon: validated.data.lon,
    db: deps.db,
    memoryStore: deps.memoryStore,
    transport: deps.transport,
    limiter: deps.sosLimiter,
    logger: deps.logger,
    now: deps.clock ? deps.clock() : Date.now(),
    tz: deps.tz,
  });
  if (!result.ok) {
    const headers = result.retryAfterSec
      ? { "Retry-After": String(result.retryAfterSec) }
      : undefined;
    sendJson(res, result.status, { error: result.error }, headers);
    return;
  }
  sendJson(res, 200, { ok: true, client_id: result.clientId, results: result.results });
}

function handleGetSosRoute(
  res: ServerResponse,
  installId: string,
  clientId: string,
  deps: RouterDependencies,
): void {
  if (!isValidUuid(clientId)) {
    sendJson(res, 400, { error: "invalid_client_id" });
    return;
  }
  const record = deps.memoryStore.getByInstallAndClient(installId, clientId);
  if (!record) {
    sendJson(res, 404, { error: "not_found" });
    return;
  }
  sendJson(res, 200, {
    results: record.results.map((r) => ({ phone_last4: r.phone_last4, status: r.status })),
  });
}

function handleDeleteRegisterRoute(
  res: ServerResponse,
  installId: string,
  deps: RouterDependencies,
): void {
  deleteInstall(deps.db, installId);
  deps.memoryStore.deleteByInstall(installId);
  sendJson(res, 200, { ok: true });
}

function verifyAuthAndLimits(
  req: IncomingMessage,
  res: ServerResponse,
  deps: RouterDependencies,
): string | null {
  if (!checkAuth(req.headers["authorization"], deps.apiKey)) {
    sendJson(res, 401, { error: "unauthorized" });
    return null;
  }
  const keyRate = deps.keyLimiter.check(deps.apiKey, KEY_RATE_LIMIT, ONE_MINUTE_MS);
  if (!keyRate.allowed) {
    sendJson(res, 429, { error: "rate_limited" }, { "Retry-After": String(keyRate.retryAfterSec) });
    return null;
  }
  const installResult = validateInstallIdHeader(req.headers["x-install-id"]);
  if (!installResult.ok) {
    sendJson(res, 400, { error: installResult.error });
    return null;
  }
  return installResult.installId;
}

export async function routeRequest(
  req: IncomingMessage,
  res: ServerResponse,
  deps: RouterDependencies,
): Promise<void> {
  const method = req.method?.toUpperCase();
  const rawUrl = req.url ?? "/";
  const [pathname] = rawUrl.split("?");

  if (method === "GET" && pathname === "/v1/health") {
    sendJson(res, 200, { whatsapp: deps.transport.status(), version: "1" });
    return;
  }

  const installId = verifyAuthAndLimits(req, res, deps);
  if (!installId) return;

  if (method === "POST" && pathname === "/v1/register") {
    await handleRegisterRoute(req, res, installId, deps);
  } else if (method === "DELETE" && pathname === "/v1/register") {
    handleDeleteRegisterRoute(res, installId, deps);
  } else if (method === "POST" && pathname === "/v1/sos") {
    await handleSosRoute(req, res, installId, deps);
  } else if (method === "GET" && pathname?.startsWith("/v1/sos/")) {
    const clientId = pathname.slice("/v1/sos/".length);
    handleGetSosRoute(res, installId, clientId, deps);
  } else {
    sendJson(res, 404, { error: "not_found" });
  }
}
