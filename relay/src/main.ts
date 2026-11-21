import fs from "node:fs";
import path from "node:path";
import { DatabaseSync } from "node:sqlite";
import { loadConfig } from "./config.ts";
import { createConsoleLogger, type Logger } from "./log/Logger.ts";
import { initDb } from "./store/db.ts";
import { SosMemoryStore } from "./store/sosMemory.ts";
import { SlidingWindowLimiter } from "./domain/limiter.ts";
import { setupInboundAndReceipts } from "./service/inboundHandler.ts";
import { createRelayServer } from "./http/server.ts";
import type { WhatsAppTransport } from "./transport/WhatsAppTransport.ts";

type CreateDryRunTransportFn = (log: Logger) => WhatsAppTransport;
type CreateBaileysTransportFn = (opts: { authDir: string; log: Logger }) => WhatsAppTransport;

async function loadTransport(
  isDryRun: boolean,
  authDir: string,
  log: Logger,
): Promise<WhatsAppTransport> {
  if (isDryRun) {
    const specifier = "./transport/DryRunTransport.ts";
    const mod = (await import(specifier)) as { createDryRunTransport: CreateDryRunTransportFn };
    return mod.createDryRunTransport(log);
  }
  const specifier = "./transport/BaileysTransport.ts";
  const mod = (await import(specifier)) as { createBaileysTransport: CreateBaileysTransportFn };
  return mod.createBaileysTransport({ authDir, log });
}

export async function main(): Promise<void> {
  const config = loadConfig();
  const logger = createConsoleLogger();
  const clock = Date.now;

  if (config.dbPath !== ":memory:") {
    fs.mkdirSync(path.dirname(config.dbPath), { recursive: true });
  }

  const db = new DatabaseSync(config.dbPath);
  initDb(db);

  const memoryStore = new SosMemoryStore({ clock });
  const keyLimiter = new SlidingWindowLimiter(clock);
  const sosLimiter = new SlidingWindowLimiter(clock);

  const transport = await loadTransport(config.isDryRun, config.authDir, logger);
  setupInboundAndReceipts({ db, memoryStore, transport, logger });

  const relayServer = createRelayServer({
    apiKey: config.apiKey,
    tz: config.tz,
    db,
    memoryStore,
    transport,
    keyLimiter,
    sosLimiter,
    logger,
    clock,
  });

  const actualPort = await relayServer.start(config.port);
  logger.info("server_started", { port: actualPort });

  const shutdown = async (): Promise<void> => {
    logger.info("server_stopping");
    memoryStore.close();
    await relayServer.close();
    db.close();
    process.exit(0);
  };

  process.on("SIGINT", () => {
    void shutdown();
  });
  process.on("SIGTERM", () => {
    void shutdown();
  });
}

if (import.meta.url === `file://${process.argv[1]}`) {
  void main().catch((err) => {
    process.stderr.write(`Fatal error: ${err}\n`);
    process.exit(1);
  });
}
