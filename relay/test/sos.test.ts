import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { setupTestContext, type TestContext } from "./testHarness.ts";

describe("POST and GET /v1/sos", () => {
  let ctx: TestContext;
  const installId = "a1111111-1111-4111-8111-111111111111";
  const otherInstallId = "b2222222-2222-4222-8222-222222222222";
  const clientId = "c3333333-3333-4333-8333-333333333333";

  beforeEach(async () => {
    ctx = await setupTestContext();
  });

  afterEach(async () => {
    await ctx.teardown();
  });

  async function registerInstall(instId = installId): Promise<void> {
    await ctx.request("/v1/register", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${ctx.apiKey}`,
        "X-Install-Id": instId,
      },
      body: {
        driver_name: "Ziad",
        contacts: [
          { name: "Mum", phone: "+201000000001" },
          { name: "Dad", phone: "+201000000002" },
        ],
      },
    });
    ctx.transport.sent = [];
  }

  it("returns 404 not_registered when install is not registered", async () => {
    const res = await ctx.request("/v1/sos", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${ctx.apiKey}`,
        "X-Install-Id": installId,
      },
      body: {
        client_id: clientId,
        kind: "crash",
        t_crash: ctx.now,
        lat: 30.0444,
        lon: 31.2357,
      },
    });

    expect(res.status).toBe(404);
    expect(await res.json()).toEqual({ error: "not_registered" });
  });

  it("sends to registered contacts only; ignores any to/phone field in body", async () => {
    await registerInstall();

    const res = await ctx.request("/v1/sos", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${ctx.apiKey}`,
        "X-Install-Id": installId,
      },
      body: {
        client_id: clientId,
        kind: "crash",
        t_crash: ctx.now,
        lat: 30.0444,
        lon: 31.2357,
        to: "+201000000999",
        phone: "+201000000888",
      },
    });

    expect(res.status).toBe(200);
    const data = (await res.json()) as { ok: boolean; results: Array<{ phone_last4: string; status: string }> };
    expect(data.ok).toBe(true);
    expect(data.results.length).toBe(2);
    // Sent to the two registered contacts only!
    const sentNumbers = ctx.transport.sent.map((s) => s.to).sort();
    expect(sentNumbers).toEqual(["+201000000001", "+201000000002"]);
  });

  it("idempotent retry returns identical result and does not resend", async () => {
    await registerInstall();

    const payload = {
      client_id: clientId,
      kind: "crash",
      t_crash: ctx.now,
      lat: 30.0444,
      lon: 31.2357,
    };
    const headers = {
      Authorization: `Bearer ${ctx.apiKey}`,
      "X-Install-Id": installId,
    };

    const res1 = await ctx.request("/v1/sos", { method: "POST", headers, body: payload });
    expect(res1.status).toBe(200);
    expect(ctx.transport.sent.length).toBe(2);

    const res2 = await ctx.request("/v1/sos", { method: "POST", headers, body: payload });
    expect(res2.status).toBe(200);
    expect(await res2.json()).toEqual(await res1.json());
    // Still only 2 messages sent, no second dispatch
    expect(ctx.transport.sent.length).toBe(2);
  });

  it("enforces 5 SOS per install per hour rate limit (6th returns 429 with Retry-After)", async () => {
    await registerInstall();
    const headers = {
      Authorization: `Bearer ${ctx.apiKey}`,
      "X-Install-Id": installId,
    };

    for (let i = 1; i <= 5; i++) {
      const res = await ctx.request("/v1/sos", {
        method: "POST",
        headers,
        body: {
          client_id: `c3333333-3333-4333-8333-33333333330${i}`,
          kind: "crash",
          t_crash: ctx.now,
          lat: null,
          lon: null,
        },
      });
      expect(res.status).toBe(200);
    }

    // 6th unique SOS returns 429
    const res6 = await ctx.request("/v1/sos", {
      method: "POST",
      headers,
      body: {
        client_id: "c3333333-3333-4333-8333-333333333306",
        kind: "crash",
        t_crash: ctx.now,
        lat: null,
        lon: null,
      },
    });
    expect(res6.status).toBe(429);
    expect(await res6.json()).toEqual({ error: "rate_limited" });
    expect(res6.headers.get("retry-after")).toBeTruthy();

    // Idempotent retry of 5th SOS does NOT count against rate limit and returns 200
    const retryRes = await ctx.request("/v1/sos", {
      method: "POST",
      headers,
      body: {
        client_id: "c3333333-3333-4333-8333-333333333305",
        kind: "crash",
        t_crash: ctx.now,
        lat: null,
        lon: null,
      },
    });
    expect(retryRes.status).toBe(200);
  });

  it("advances status with receipts and receipts never move backwards", async () => {
    await registerInstall();
    const res = await ctx.request("/v1/sos", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${ctx.apiKey}`,
        "X-Install-Id": installId,
      },
      body: {
        client_id: clientId,
        kind: "crash",
        t_crash: ctx.now,
        lat: 30.0444,
        lon: 31.2357,
      },
    });
    expect(res.status).toBe(200);

    const firstMsg = ctx.transport.sent[0];
    expect(firstMsg).toBeDefined();
    if (!firstMsg) return;

    // Emit delivered
    ctx.transport.emitReceipt(firstMsg.messageId, "delivered");

    const getRes1 = await ctx.request(`/v1/sos/${clientId}`, {
      headers: {
        Authorization: `Bearer ${ctx.apiKey}`,
        "X-Install-Id": installId,
      },
    });
    expect(getRes1.status).toBe(200);
    const data1 = (await getRes1.json()) as { results: Array<{ phone_last4: string; status: string }> };
    const firstStatus = data1.results.find((r) => r.phone_last4 === firstMsg.to.slice(-4));
    expect(firstStatus?.status).toBe("delivered");

    // Emit sent afterwards - should NOT move backwards
    ctx.transport.emitReceipt(firstMsg.messageId, "sent");
    const getRes2 = await ctx.request(`/v1/sos/${clientId}`, {
      headers: {
        Authorization: `Bearer ${ctx.apiKey}`,
        "X-Install-Id": installId,
      },
    });
    const data2 = (await getRes2.json()) as { results: Array<{ phone_last4: string; status: string }> };
    const secondStatus = data2.results.find((r) => r.phone_last4 === firstMsg.to.slice(-4));
    expect(secondStatus?.status).toBe("delivered");
  });

  it("expires SOS entries after 24 hours (GET returns 404)", async () => {
    await registerInstall();
    await ctx.request("/v1/sos", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${ctx.apiKey}`,
        "X-Install-Id": installId,
      },
      body: {
        client_id: clientId,
        kind: "crash",
        t_crash: ctx.now,
        lat: 30.0444,
        lon: 31.2357,
      },
    });

    // Advance clock past 24 hours (24h + 1 second)
    ctx.advanceTime(24 * 60 * 60 * 1000 + 1000);

    const getRes = await ctx.request(`/v1/sos/${clientId}`, {
      headers: {
        Authorization: `Bearer ${ctx.apiKey}`,
        "X-Install-Id": installId,
      },
    });
    expect(getRes.status).toBe(404);
    expect(await getRes.json()).toEqual({ error: "not_found" });
  });

  it("returns 404 when GET /v1/sos/{client_id} is queried by a different install", async () => {
    await registerInstall();
    await ctx.request("/v1/sos", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${ctx.apiKey}`,
        "X-Install-Id": installId,
      },
      body: {
        client_id: clientId,
        kind: "crash",
        t_crash: ctx.now,
        lat: 30.0444,
        lon: 31.2357,
      },
    });

    const getRes = await ctx.request(`/v1/sos/${clientId}`, {
      headers: {
        Authorization: `Bearer ${ctx.apiKey}`,
        "X-Install-Id": otherInstallId,
      },
    });
    expect(getRes.status).toBe(404);
    expect(await getRes.json()).toEqual({ error: "not_found" });
  });
});
