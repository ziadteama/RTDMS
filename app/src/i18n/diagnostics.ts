/** Diagnostics strings table (for team and engineers, not end-user drivers). */
export const diagnostics = {
  // Title & header
  'diag.title': 'Diagnostics',
  'diag.subtitle': 'For the Sahi team',

  // Section titles
  'diag.section.unit': 'Unit health',
  'diag.section.detection': 'Detection tuning',
  'diag.section.connection': 'Connection & relay',
  'diag.section.raw': 'Raw sensor metrics',

  // Unit Health
  'diag.health.system': 'System',
  'diag.health.cpu': 'CPU',
  'diag.health.temp': 'Temperature',
  'diag.health.throttling': 'Throttling',
  'diag.health.throttleNone': 'None',
  'diag.health.underVoltage': 'Under-voltage',
  'diag.health.throttled': 'Throttled',
  'diag.health.freqCapped': 'CPU frequency capped',
  'diag.health.softTemp': 'Soft temperature limit',
  'diag.health.volts': '5 V supply',
  'diag.health.fps': 'Camera rate (fps)',
  'diag.health.camera': 'Camera',
  'diag.health.memory': 'Memory',
  'diag.health.storage': 'Storage free',
  'diag.health.uptime': 'Uptime',
  'diag.health.models': 'Models',
  'diag.health.controls': 'Controls',
  'diag.health.restart': 'Restart monitoring service',
  'diag.health.shutdown': 'Shut down unit',
  'diag.health.restartConfirm': 'Restart the monitoring service? Alerts stop for about 20 seconds.',
  'diag.health.shutdownConfirm': 'Shut down the unit? Monitoring stops until it is powered on again.',
  'diag.health.sent': 'Sent',
  'diag.health.unavailable': 'Health data not available from this unit.',
  'diag.health.ok': 'OK',
  'diag.health.lost': 'Lost',
  'diag.health.running': 'Running',
  'diag.health.off': 'Off',
  'diag.health.error': 'Error',
  'diag.health.now': 'now',
  'diag.health.sinceBoot': 'since boot',
  'diag.health.offline': 'Unit offline. Reconnecting…',
  'diag.health.offlineHint': 'Check that the unit is powered on.',

  // Detection Tuning
  'diag.det.profile': 'Profile',
  'diag.det.calibrate': 'Calibrate driving position',
  'diag.det.sensitivity': 'Sensitivity',
  'diag.det.sens.low': 'Low',
  'diag.det.sens.normal': 'Normal',
  'diag.det.sens.high': 'High',
  'diag.det.eyeClosure': 'Eye closure threshold',
  'diag.det.offroad': 'Eyes off road threshold',
  'diag.det.phoneDuration': 'Phone use threshold',
  'diag.det.drowsiness': 'Drowsiness detector',
  'diag.det.distraction': 'Distraction detector',
  'diag.det.phone': 'Phone use detector',
  'diag.det.physiology': 'Heart rate detector',
  'diag.det.footer': 'Saved on the unit. Used by fusion to decide alerts.',
  'diag.det.offlineFooter': 'Connect to the unit to modify parameters.',
  'diag.det.unsupported': 'Detection parameters not supported by this unit.',

  // Connection
  'diag.conn.address': 'Unit address',
  'diag.conn.pair': 'Pair via QR code',
  'diag.conn.demo': 'Demo replay mode',
  'diag.conn.demoFooter': 'Replays a recorded drive inside the app. No unit needed.',
  'diag.conn.fakeCrash': 'Simulate crash',
  'diag.conn.relayUrl': 'Relay service URL',
  'diag.conn.relayKey': 'Relay auth key',
  'diag.conn.badUrl': 'Invalid URL',
  'diag.link.label': 'Link',
  'diag.link.ble': 'Bluetooth',
  'diag.link.http': 'Wi-Fi',
  'diag.link.open': 'Open link (no code)',
  'diag.link.none': 'none',
  'diag.link.signal': 'Signal',
  'diag.link.dbm': '{dbm} dBm',
  'diag.link.last': 'Last update',
  'diag.link.ago': '{s} s ago',
  'diag.link.unknown': '-',

  // Raw Metrics
  'diag.raw.eyes': 'Raw eye metrics',
  'diag.raw.openness': 'Eye openness (EAR)',
  'diag.raw.perclos': 'PERCLOS',
  'diag.raw.perclosWarming': 'warming up',
  'diag.raw.blinks': 'Blink rate',
  'diag.raw.closure': 'Eye closure',
  'diag.raw.heart': 'Raw physiology metrics',
  'diag.raw.hr': 'Heart rate (HR)',
  'diag.raw.rr': 'Beat interval (RR)',
  'diag.raw.quality': 'HR quality',
  'diag.raw.worn': 'Worn',
  'diag.raw.baseline': 'HR baseline',
  'diag.raw.delta': 'HR delta',
  'diag.raw.trend': 'HR trend',
  'diag.raw.prv': 'PRV state',
  'diag.raw.watchOff': 'Watch not connected',
  'diag.raw.phone': 'Raw hybrid / phone metrics',
  'diag.raw.call': 'In call',
  'diag.raw.texting': 'Texting',
  'diag.raw.detected': 'Detected',
  'diag.raw.none': 'None',
  'diag.raw.perMin': '/min',
  'diag.raw.bpm': 'bpm',
  'diag.raw.ms': 'ms',
  'diag.raw.s': 's',
} as const;

export type DiagnosticsKey = keyof typeof diagnostics;

export function dx(key: DiagnosticsKey, params?: Record<string, string | number>): string {
  let str: string = diagnostics[key];
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      str = str.replaceAll(`{${k}}`, String(v));
    }
  }
  return str;
}
