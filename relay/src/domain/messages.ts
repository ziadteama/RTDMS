export interface SosMessageOptions {
  kind: "crash" | "manual";
  driverName: string;
  tCrash: number;
  lat: number | null;
  lon: number | null;
  tz?: string;
}

export function buildOptInMessage(driverName: string): string {
  const driver = driverName.trim();
  return `${driver} added you as an emergency contact in Sahi. You will get a message if their car's crash alert fires. Reply STOP to opt out.`;
}

export function formatCrashTime(tCrash: number, tz = "Africa/Cairo"): string {
  const d = new Date(tCrash);
  const formatter = new Intl.DateTimeFormat("en-US", {
    timeZone: tz,
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
  });
  return formatter.format(d).replace(/\u202f/g, " ");
}

export function buildSosMessage(opts: SosMessageOptions): string {
  const time = formatCrashTime(opts.tCrash, opts.tz);
  const driver = opts.driverName.trim();

  let locationStr = "Location unknown";
  let hasLocation = false;
  if (opts.lat !== null && opts.lon !== null) {
    const latStr = opts.lat.toFixed(5);
    const lonStr = opts.lon.toFixed(5);
    hasLocation = true;
    locationStr = `${latStr},${lonStr} https://maps.google.com/?q=${latStr},${lonStr}`;
  }

  if (opts.kind === "crash") {
    return `SAHI crash alert ${time}. ${driver} may need help. ${hasLocation ? "Location: " : ""}${locationStr}`;
  }

  return `SAHI alert ${time}. ${driver} needs help. ${hasLocation ? "Location: " : ""}${locationStr}`;
}
