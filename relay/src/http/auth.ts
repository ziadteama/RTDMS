import crypto from "node:crypto";
import { isValidUuid } from "../domain/validate.ts";

export function checkAuth(header: string | undefined, expectedKey: string): boolean {
  if (!header || !header.startsWith("Bearer ")) {
    return false;
  }
  const token = header.slice("Bearer ".length).trim();
  const tokenBuf = Buffer.from(token, "utf8");
  const expectedBuf = Buffer.from(expectedKey, "utf8");

  if (tokenBuf.length !== expectedBuf.length) {
    crypto.timingSafeEqual(expectedBuf, expectedBuf);
    return false;
  }

  return crypto.timingSafeEqual(tokenBuf, expectedBuf);
}

export function validateInstallIdHeader(
  header: string | string[] | undefined,
): { ok: true; installId: string } | { ok: false; error: string } {
  if (typeof header !== "string") {
    return { ok: false, error: "invalid_install_id" };
  }
  const trimmed = header.trim();
  if (!isValidUuid(trimmed)) {
    return { ok: false, error: "invalid_install_id" };
  }
  return { ok: true, installId: trimmed };
}
