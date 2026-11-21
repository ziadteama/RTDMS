import { createRequire } from "node:module";
import type { DatabaseSync as DatabaseSyncType } from "node:sqlite";
import { initDb } from "../src/store/db.ts";
import { SosMemoryStore } from "../src/store/sosMemory.ts";
import { SlidingWindowLimiter } from "../src/domain/limiter.ts";
import { FakeTransport } from "../src/transport/FakeTransport.ts";
import { setupInboundAndReceipts } from "../src/service/inboundHandler.ts";
import { createRelayServer, type RelayServer } from "../src/http/server.ts";
import type { Logger } from "../src/log/Logger.ts";

const require = createRequire(import.meta.url);
const { DatabaseSync } = require("node:sqlite") as {
  DatabaseSync: new (path: string) => DatabaseSyncType;
};

export interface LogEntry {
  level: string;
  event: string;
  fields?: Record<string, string | number | boolean>;
}

export interface TestContext {
  apiKey: string;
  db: DatabaseSyncType;
  transport: FakeTransport;
  memoryStore: SosMemoryStore;
  logs: LogEntry[];
  logger: Logger;
  now: number;
  advanceTime(ms: number): void;
  server: RelayServer;
  baseUrl: string;
  request(
    path: string,
    options?: {
      method?: string;
      headers?: Record<string, string>;
      body?: unknown;
    },
  ): Promise<{ status: number; headers: Headers; json: () => Promise<unknown> }>;
  teardown(): Promise<void>;
}

export async function setupTestContext(opts: { apiKey?: string; tz?: string } = {}): Promise<TestContext> {
  const apiKey = opts.apiKey ?? "valid-test-relay-api-key-12345";
  const tz = opts.tz ?? "Africa/Cairo";

  let currentTime = 1795189200000;
  const clock = () => currentTime;

  const logs: LogEntry[] = [];
  const logger: Logger = {
    info(event, fields) {
      logs.push({ level: "INFO", event, fields });
    },
    warn(event, fields) {
      logs.push({ level: "WARN", event, fields });
    },
    error(event, fields) {
      logs.push({ level: "ERROR", event, fields });
    },
  };

  const db = new DatabaseSync(":memory:");
  initDb(db);

  const transport = new FakeTransport();
  const memoryStore = new SosMemoryStore({ clock, ttlMs: 24 * 60 * 60 * 1000 });
  const keyLimiter = new SlidingWindowLimiter(clock);
  const sosLimiter = new SlidingWindowLimiter(clock);

  setupInboundAndReceipts({ db, memoryStore, transport, logger });

  const server = createRelayServer({
    apiKey,
    tz,
    db,
    memoryStore,
    transport,
    keyLimiter,
    sosLimiter,
    logger,
    clock,
  });

  const port = await server.start(0);
  const baseUrl = `http://127.0.0.1:${port}`;

  const request: TestContext["request"] = async (path, options = {}) => {
    const headers: Record<string, string> = { ...(options.headers ?? {}) };
    let body: string | undefined;
    if (options.body !== undefined) {
      if (typeof options.body === "string") {
        body = options.body;
      } else {
        body = JSON.stringify(options.body);
        if (!headers["content-type"]) {
          headers["content-type"] = "application/json";
        }
      }
    }

    const res = await fetch(`${baseUrl}${path}`, {
      method: options.method ?? "GET",
      headers,
      body,
    });

    return {
      status: res.status,
      headers: res.headers,
      json: () => res.json(),
    };
  };

  const teardown = async () => {
    memoryStore.close();
    await server.close();
    db.close();
  };

  return {
    apiKey,
    db,
    transport,
    memoryStore,
    logs,
    logger,
    get now() {
      return currentTime;
    },
    advanceTime(ms: number) {
      currentTime += ms;
    },
    server,
    baseUrl,
    request,
    teardown,
  };
}
