export interface Logger {
  info(event: string, fields?: Record<string, string | number | boolean>): void;
  warn(event: string, fields?: Record<string, string | number | boolean>): void;
  error(event: string, fields?: Record<string, string | number | boolean>): void;
}

export function maskPhone(e164: string): string {
  const digits = e164.replace(/\D/g, "");
  if (digits.length <= 4) {
    return `***${digits}`;
  }
  return `***${digits.slice(-4)}`;
}

export function createConsoleLogger(): Logger {
  function log(level: "INFO" | "WARN" | "ERROR", event: string, fields?: Record<string, string | number | boolean>): void {
    const entry = {
      level,
      event,
      ts: Date.now(),
      ...fields,
    };
    process.stdout.write(`${JSON.stringify(entry)}\n`);
  }

  return {
    info(event, fields) {
      log("INFO", event, fields);
    },
    warn(event, fields) {
      log("WARN", event, fields);
    },
    error(event, fields) {
      log("ERROR", event, fields);
    },
  };
}
