export interface Config {
  readonly apiKey: string;
  readonly port: number;
  readonly dbPath: string;
  readonly authDir: string;
  readonly tz: string;
  readonly isDryRun: boolean;
}

export function loadConfig(
  env: NodeJS.ProcessEnv = process.env,
  argv: string[] = process.argv,
): Config {
  const apiKey = env["RELAY_API_KEY"]?.trim();
  if (!apiKey || apiKey.length < 16) {
    throw new Error("RELAY_API_KEY is required and must be at least 16 characters");
  }

  const rawPort = env["PORT"]?.trim();
  const port = rawPort ? parseInt(rawPort, 10) : 8787;
  if (!Number.isInteger(port) || port <= 0 || port > 65535) {
    throw new Error(`Invalid PORT: ${rawPort}`);
  }

  const dbPath = env["RELAY_DB_PATH"]?.trim() || "./data/relay.db";
  const authDir = env["RELAY_AUTH_DIR"]?.trim() || "./auth";
  const tz = env["RELAY_TZ"]?.trim() || "Africa/Cairo";
  const isDryRun = env["RELAY_DRY_RUN"] === "true" || argv.includes("--dry-run");

  return {
    apiKey,
    port,
    dbPath,
    authDir,
    tz,
    isDryRun,
  };
}
