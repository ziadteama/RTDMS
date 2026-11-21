import type { IncomingMessage } from "node:http";

export const MAX_BODY_BYTES = 8192;

export interface BodyParseSuccess {
  ok: true;
  data: unknown;
}

export interface BodyParseFailure {
  ok: false;
  error: string;
}

export type BodyParseResult = BodyParseSuccess | BodyParseFailure;

export async function parseJsonBody(req: IncomingMessage): Promise<BodyParseResult> {
  const contentLength = req.headers["content-length"];
  if (contentLength && parseInt(contentLength, 10) > MAX_BODY_BYTES) {
    return { ok: false, error: "payload_too_large" };
  }

  return new Promise<BodyParseResult>((resolve) => {
    let bytesRead = 0;
    const chunks: Buffer[] = [];

    req.on("data", (chunk: Buffer) => {
      bytesRead += chunk.length;
      if (bytesRead > MAX_BODY_BYTES) {
        req.destroy();
        resolve({ ok: false, error: "payload_too_large" });
        return;
      }
      chunks.push(chunk);
    });

    req.on("end", () => {
      if (bytesRead > MAX_BODY_BYTES) {
        resolve({ ok: false, error: "payload_too_large" });
        return;
      }
      const raw = Buffer.concat(chunks).toString("utf8").trim();
      if (!raw) {
        resolve({ ok: false, error: "invalid_body" });
        return;
      }
      try {
        const parsed = JSON.parse(raw);
        resolve({ ok: true, data: parsed });
      } catch {
        resolve({ ok: false, error: "invalid_json" });
      }
    });

    req.on("error", () => {
      resolve({ ok: false, error: "invalid_body" });
    });
  });
}
