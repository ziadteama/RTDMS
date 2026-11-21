const E164_REGEX = /^\+[1-9]\d{7,14}$/;
const UUID_REGEX = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export interface ValidContact {
  name: string;
  phone: string;
}

export interface ValidRegisterPayload {
  driverName: string;
  contacts: ValidContact[];
}

export interface ValidSosPayload {
  clientId: string;
  kind: "crash" | "manual";
  tCrash: number;
  lat: number | null;
  lon: number | null;
}

export function isValidUuid(val: unknown): val is string {
  return typeof val === "string" && UUID_REGEX.test(val.trim());
}

export function isValidPhone(val: unknown): val is string {
  return typeof val === "string" && E164_REGEX.test(val.trim());
}

export function isValidName(val: unknown): val is string {
  if (typeof val !== "string") return false;
  const trimmed = val.trim();
  return trimmed.length >= 1 && trimmed.length <= 40;
}

export function isValidKind(val: unknown): val is "crash" | "manual" {
  return val === "crash" || val === "manual";
}

export function validateCoordinates(
  lat: unknown,
  lon: unknown,
): { lat: number | null; lon: number | null } | null {
  if (lat === null && lon === null) {
    return { lat: null, lon: null };
  }
  if (typeof lat !== "number" || typeof lon !== "number") {
    return null;
  }
  if (Number.isNaN(lat) || Number.isNaN(lon)) {
    return null;
  }
  if (lat < -90 || lat > 90 || lon < -180 || lon > 180) {
    return null;
  }
  return { lat, lon };
}

function parseAndDeduplicateContacts(
  rawList: unknown,
): { contacts: ValidContact[] } | { error: string } {
  if (!Array.isArray(rawList)) {
    return { error: "invalid_contacts" };
  }
  const seenPhones = new Set<string>();
  const contacts: ValidContact[] = [];

  for (const item of rawList) {
    if (!item || typeof item !== "object") {
      return { error: "invalid_contact" };
    }
    const c = item as Record<string, unknown>;
    if (!isValidName(c["name"])) {
      return { error: "invalid_contact_name" };
    }
    if (!isValidPhone(c["phone"])) {
      return { error: "invalid_phone" };
    }
    const phone = (c["phone"] as string).trim();
    if (!seenPhones.has(phone)) {
      seenPhones.add(phone);
      contacts.push({ name: (c["name"] as string).trim(), phone });
    }
  }

  if (contacts.length > 5) {
    return { error: "too_many_contacts" };
  }
  return { contacts };
}

export function validateRegisterPayload(
  body: unknown,
): { ok: true; data: ValidRegisterPayload } | { ok: false; error: string } {
  if (!body || typeof body !== "object") {
    return { ok: false, error: "invalid_body" };
  }
  const b = body as Record<string, unknown>;
  if (!isValidName(b["driver_name"])) {
    return { ok: false, error: "invalid_driver_name" };
  }

  const parsed = parseAndDeduplicateContacts(b["contacts"]);
  if ("error" in parsed) {
    return { ok: false, error: parsed.error };
  }

  return {
    ok: true,
    data: {
      driverName: (b["driver_name"] as string).trim(),
      contacts: parsed.contacts,
    },
  };
}

export function validateSosPayload(
  body: unknown,
): { ok: true; data: ValidSosPayload } | { ok: false; error: string } {
  if (!body || typeof body !== "object") {
    return { ok: false, error: "invalid_body" };
  }
  const b = body as Record<string, unknown>;
  if (!isValidUuid(b["client_id"])) {
    return { ok: false, error: "invalid_client_id" };
  }
  if (!isValidKind(b["kind"])) {
    return { ok: false, error: "invalid_kind" };
  }
  const tCrash = b["t_crash"];
  if (typeof tCrash !== "number" || !Number.isInteger(tCrash)) {
    return { ok: false, error: "invalid_crash_time" };
  }
  const coords = validateCoordinates(b["lat"], b["lon"]);
  if (!coords) {
    return { ok: false, error: "invalid_coordinates" };
  }

  return {
    ok: true,
    data: {
      clientId: (b["client_id"] as string).trim(),
      kind: b["kind"],
      tCrash,
      lat: coords.lat,
      lon: coords.lon,
    },
  };
}
