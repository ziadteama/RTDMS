import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { setupTestContext, type TestContext } from "./testHarness.ts";

describe("API Security, Inbound STOP, Limits, Health and Masked Logging", () => {
  let ctx: TestContext;
  const installId1 = "a1111111-1111-4111-8111-111111111111";
  const installId2 = "b2222222-2222-4222-8222-222222222222";

  beforeEach(async () => {
    ctx = await setupTestContext();
  });

  afterEach(async () => {
    await ctx.teardown();
  });

  it("GET /v1/health requires no auth and returns correct status shape", async () => {
    const res = await ctx.request("/v1/health");
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({ whatsapp: "connected", version: "1" });

    ctx.transport.setStatus("pairing");
    const resPairing = await ctx.request("/v1/health");
    expect(await resPairing.json()).toEqual({ whatsapp: "pairing", version: "1" });
  });

  it("returns 401 unauthorized when auth header is missing or invalid", async () => {
    const resNoAuth = await ctx.request("/v1/register", {
      method: "POST",
      headers: { "X-Install-Id": installId1 },
      body: { driver_name: "Ziad", contacts: [] },
    });
    expect(resNoAuth.status).toBe(401);
    expect(await resNoAuth.json()).toEqual({ error: "unauthorized" });

    const resWrongAuth = await ctx.request("/v1/register", {
      method: "POST",
      headers: {
        Authorization: "Bearer wrong-api-key-here",
        "X-Install-Id": installId1,
      },
      body: { driver_name: "Ziad", contacts: [] },
    });
    expect(resWrongAuth.status).toBe(401);
    expect(await resWrongAuth.json()).toEqual({ error: "unauthorized" });
  });

  it("enforces 60 requests per minute per key rate limit (61st returns 429 with Retry-After)", async () => {
    const headers = {
      Authorization: `Bearer ${ctx.apiKey}`,
      "X-Install-Id": installId1,
    };

    for (let i = 0; i < 60; i++) {
      const res = await ctx.request("/v1/sos/c3333333-3333-4333-8333-333333333333", {
        headers,
      });
      // 404 because client_id doesn't exist, but it passed rate limiting!
      expect(res.status).toBe(404);
    }

    const res61 = await ctx.request("/v1/sos/c3333333-3333-4333-8333-333333333333", {
      headers,
    });
    expect(res61.status).toBe(429);
    expect(await res61.json()).toEqual({ error: "rate_limited" });
    expect(res61.headers.get("retry-after")).toBeTruthy();
  });

  it("inbound STOP marks contact opted_out in EVERY install and prevents SOS sending", async () => {
    const phone = "+201000000001";

    // Register contact in install 1
    await ctx.request("/v1/register", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${ctx.apiKey}`,
        "X-Install-Id": installId1,
      },
      body: { driver_name: "Driver 1", contacts: [{ name: "Contact 1", phone }] },
    });

    // Register same contact in install 2
    await ctx.request("/v1/register", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${ctx.apiKey}`,
        "X-Install-Id": installId2,
      },
      body: { driver_name: "Driver 2", contacts: [{ name: "Contact 2", phone }] },
    });

    ctx.transport.sent = [];

    // Contact replies STOP
    ctx.transport.emitInbound(phone, "  stop.  ");

    // In install 1, trigger SOS: contact should be opted_out and receive no message
    const resSos = await ctx.request("/v1/sos", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${ctx.apiKey}`,
        "X-Install-Id": installId1,
      },
      body: {
        client_id: "c3333333-3333-4333-8333-333333333333",
        kind: "crash",
        t_crash: ctx.now,
        lat: 30.0444,
        lon: 31.2357,
      },
    });

    expect(resSos.status).toBe(200);
    const sosData = (await resSos.json()) as { results: Array<{ phone_last4: string; status: string }> };
    expect(sosData.results).toEqual([{ phone_last4: "0001", status: "opted_out" }]);
    expect(ctx.transport.sent.length).toBe(0);

    // Re-registering does NOT clear opt-out and sends no opt-in
    const reRegRes = await ctx.request("/v1/register", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${ctx.apiKey}`,
        "X-Install-Id": installId1,
      },
      body: { driver_name: "Driver 1", contacts: [{ name: "Contact 1", phone }] },
    });
    const reRegData = (await reRegRes.json()) as { contacts: Array<{ phone_last4: string; status: string }> };
    expect(reRegData.contacts).toEqual([{ phone_last4: "0001", status: "opted_out" }]);
    expect(ctx.transport.sent.length).toBe(0);
  });

  it("masks logs: never logs full numbers, coordinates, message bodies, or API key", async () => {
    const fullPhone = "+201000000001";
    const lat = 30.0444;
    const lon = 31.2357;

    await ctx.request("/v1/register", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${ctx.apiKey}`,
        "X-Install-Id": installId1,
      },
      body: { driver_name: "Ziad", contacts: [{ name: "Mum", phone: fullPhone }] },
    });

    await ctx.request("/v1/sos", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${ctx.apiKey}`,
        "X-Install-Id": installId1,
      },
      body: {
        client_id: "c3333333-3333-4333-8333-333333333333",
        kind: "crash",
        t_crash: ctx.now,
        lat,
        lon,
      },
    });

    ctx.transport.emitInbound(fullPhone, "STOP");

    const serializedLogs = JSON.stringify(ctx.logs);

    // Assert NO full phone number anywhere in logs
    expect(serializedLogs).not.toContain(fullPhone);

    // Assert masked phone appears
    expect(serializedLogs).toContain("***0001");

    // Assert NO coordinates appear anywhere in logs
    expect(serializedLogs).not.toContain(String(lat));
    expect(serializedLogs).not.toContain(String(lon));

    // Assert NO message body appears in logs
    expect(serializedLogs).not.toContain("crash alert");
    expect(serializedLogs).not.toContain("emergency contact");

    // Assert NO API key appears in logs
    expect(serializedLogs).not.toContain(ctx.apiKey);

    // Assert install id is at most 8 characters
    for (const entry of ctx.logs) {
      if (entry.fields && "install_id" in entry.fields) {
        expect(String(entry.fields["install_id"]).length).toBeLessThanOrEqual(8);
      }
    }
  });
});
