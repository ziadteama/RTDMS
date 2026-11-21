import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { setupTestContext, type TestContext } from "./testHarness.ts";

describe("POST and DELETE /v1/register", () => {
  let ctx: TestContext;
  const installId = "a1111111-1111-4111-8111-111111111111";

  beforeEach(async () => {
    ctx = await setupTestContext();
  });

  afterEach(async () => {
    await ctx.teardown();
  });

  it("registers new contact and sends opt-in message once", async () => {
    const res = await ctx.request("/v1/register", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${ctx.apiKey}`,
        "X-Install-Id": installId,
      },
      body: {
        driver_name: "Ziad",
        contacts: [{ name: "Mum", phone: "+201000000001" }],
      },
    });

    expect(res.status).toBe(200);
    const data = (await res.json()) as { contacts: Array<{ phone_last4: string; status: string }> };
    expect(data.contacts).toEqual([{ phone_last4: "0001", status: "pending" }]);
    expect(ctx.transport.sent.length).toBe(1);
    expect(ctx.transport.sent[0]?.to).toBe("+201000000001");
    expect(ctx.transport.sent[0]?.text).toContain("Ziad added you as an emergency contact in Sahi");
  });

  it("re-registering same contact sends no duplicate opt-in", async () => {
    const authHeaders = {
      Authorization: `Bearer ${ctx.apiKey}`,
      "X-Install-Id": installId,
    };

    await ctx.request("/v1/register", {
      method: "POST",
      headers: authHeaders,
      body: {
        driver_name: "Ziad",
        contacts: [{ name: "Mum", phone: "+201000000001" }],
      },
    });
    expect(ctx.transport.sent.length).toBe(1);

    const res2 = await ctx.request("/v1/register", {
      method: "POST",
      headers: authHeaders,
      body: {
        driver_name: "Ziad",
        contacts: [{ name: "Mum", phone: "+201000000001" }],
      },
    });
    expect(res2.status).toBe(200);
    // Still exactly 1 message sent!
    expect(ctx.transport.sent.length).toBe(1);
  });

  it("collapses duplicate numbers in one request to one contact", async () => {
    const res = await ctx.request("/v1/register", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${ctx.apiKey}`,
        "X-Install-Id": installId,
      },
      body: {
        driver_name: "Ziad",
        contacts: [
          { name: "Mum", phone: "+201000000001" },
          { name: "Mother", phone: "+201000000001" },
        ],
      },
    });

    expect(res.status).toBe(200);
    const data = (await res.json()) as { contacts: Array<{ phone_last4: string; status: string }> };
    expect(data.contacts.length).toBe(1);
    expect(ctx.transport.sent.length).toBe(1);
  });

  it("returns 400 when more than 5 contacts are provided", async () => {
    const res = await ctx.request("/v1/register", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${ctx.apiKey}`,
        "X-Install-Id": installId,
      },
      body: {
        driver_name: "Ziad",
        contacts: [
          { name: "C1", phone: "+201000000001" },
          { name: "C2", phone: "+201000000002" },
          { name: "C3", phone: "+201000000003" },
          { name: "C4", phone: "+201000000004" },
          { name: "C5", phone: "+201000000005" },
          { name: "C6", phone: "+201000000006" },
        ],
      },
    });

    expect(res.status).toBe(400);
    expect(await res.json()).toEqual({ error: "too_many_contacts" });
  });

  it("returns 400 for bad E.164 phone numbers", async () => {
    const res = await ctx.request("/v1/register", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${ctx.apiKey}`,
        "X-Install-Id": installId,
      },
      body: {
        driver_name: "Ziad",
        contacts: [{ name: "Mum", phone: "01000000001" }],
      },
    });

    expect(res.status).toBe(400);
    expect(await res.json()).toEqual({ error: "invalid_phone" });
  });

  it("returns 400 for invalid X-Install-Id UUID", async () => {
    const res = await ctx.request("/v1/register", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${ctx.apiKey}`,
        "X-Install-Id": "invalid-uuid",
      },
      body: {
        driver_name: "Ziad",
        contacts: [{ name: "Mum", phone: "+201000000001" }],
      },
    });

    expect(res.status).toBe(400);
    expect(await res.json()).toEqual({ error: "invalid_install_id" });
  });

  it("marks status as invalid when transport reports not_on_whatsapp", async () => {
    ctx.transport.markNotOnWhatsApp("+201000000001");

    const res = await ctx.request("/v1/register", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${ctx.apiKey}`,
        "X-Install-Id": installId,
      },
      body: {
        driver_name: "Ziad",
        contacts: [{ name: "Mum", phone: "+201000000001" }],
      },
    });

    expect(res.status).toBe(200);
    const data = (await res.json()) as { contacts: Array<{ phone_last4: string; status: string }> };
    expect(data.contacts).toEqual([{ phone_last4: "0001", status: "invalid" }]);
  });

  it("marks status as failed when transport send rejects with generic error", async () => {
    ctx.transport.failNextSend(new Error("socket timeout"));

    const res = await ctx.request("/v1/register", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${ctx.apiKey}`,
        "X-Install-Id": installId,
      },
      body: {
        driver_name: "Ziad",
        contacts: [{ name: "Mum", phone: "+201000000001" }],
      },
    });

    expect(res.status).toBe(200);
    const data = (await res.json()) as { contacts: Array<{ phone_last4: string; status: string }> };
    expect(data.contacts).toEqual([{ phone_last4: "0001", status: "failed" }]);
  });

  it("DELETE /v1/register removes install and its contacts", async () => {
    const authHeaders = {
      Authorization: `Bearer ${ctx.apiKey}`,
      "X-Install-Id": installId,
    };

    await ctx.request("/v1/register", {
      method: "POST",
      headers: authHeaders,
      body: {
        driver_name: "Ziad",
        contacts: [{ name: "Mum", phone: "+201000000001" }],
      },
    });

    const delRes = await ctx.request("/v1/register", {
      method: "DELETE",
      headers: authHeaders,
    });
    expect(delRes.status).toBe(200);
    expect(await delRes.json()).toEqual({ ok: true });

    // Since install was deleted, register again will treat contact as new and send opt-in again
    ctx.transport.sent = [];
    const reRegisterRes = await ctx.request("/v1/register", {
      method: "POST",
      headers: authHeaders,
      body: {
        driver_name: "Ziad",
        contacts: [{ name: "Mum", phone: "+201000000001" }],
      },
    });
    expect(reRegisterRes.status).toBe(200);
    expect(ctx.transport.sent.length).toBe(1);
  });
});
