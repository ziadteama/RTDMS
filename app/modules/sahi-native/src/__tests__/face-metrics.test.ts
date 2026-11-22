/**
 * Tests mirroring pure math from FaceMetrics.kt (port of models/face/src/dms_face/metrics.py and headpose.py).
 */

const RIGHT_EYE_EAR = [33, 160, 158, 133, 153, 144] as const;
const LEFT_EYE_EAR = [362, 385, 387, 263, 373, 380] as const;

function dist(p1: [number, number], p2: [number, number]): number {
  return Math.hypot(p1[0] - p2[0], p1[1] - p2[1]);
}

function eyeAspectRatio(pts: [number, number][], idx: readonly number[]): number | null {
  const [i1, i2, i3, i4, i5, i6] = idx;
  const p1 = pts[i1!];
  const p2 = pts[i2!];
  const p3 = pts[i3!];
  const p4 = pts[i4!];
  const p5 = pts[i5!];
  const p6 = pts[i6!];
  if (!p1 || !p2 || !p3 || !p4 || !p5 || !p6) return null;

  const horizontal = dist(p1, p4);
  if (horizontal < 1e-6) return null;

  return (dist(p2, p6) + dist(p3, p5)) / (2.0 * horizontal);
}

function combineEar(right: number | null, left: number | null): number | null {
  const vals = [right, left].filter((v): v is number => v !== null);
  if (vals.length === 0) return null;
  return vals.reduce((a, b) => a + b, 0) / vals.length;
}

function isEarValid(yaw: number | null, pitch: number | null, ear: number | null): boolean {
  if (ear === null) return false;
  const y = yaw ?? 0;
  const p = pitch ?? 0;
  return Math.abs(y) <= 30.0 && Math.abs(p) <= 25.0;
}

function normaliseAngles(yaw: number, pitch: number, roll: number): [number, number, number] {
  function wrap(a: number): number {
    let x = a;
    while (x > 180.0) x -= 360.0;
    while (x < -180.0) x += 360.0;
    return x;
  }
  let y = wrap(yaw);
  let p = wrap(pitch);
  let r = wrap(roll);

  if (Math.abs(p) > 90.0) {
    p = p > 0 ? wrap(180.0 - p) : wrap(-180.0 - p);
  }
  if (Math.abs(r) > 90.0) {
    r = r > 0 ? wrap(r - 180.0) : wrap(r + 180.0);
  }
  return [y, p, r];
}

function headPoseFromMatrix(matrix: number[]): [number, number, number] | null {
  if (matrix.length < 16) return null;

  // 3x3 rotation matrix, column-major: matrix[col * 4 + row]
  const rmat: number[][] = [
    [matrix[0]!, matrix[4]!, matrix[8]!],
    [matrix[1]!, matrix[5]!, matrix[9]!],
    [matrix[2]!, matrix[6]!, matrix[10]!],
  ];

  // Normalize columns
  for (let c = 0; c < 3; c++) {
    const norm = Math.hypot(rmat[0]![c]!, rmat[1]![c]!, rmat[2]![c]!);
    if (norm > 1e-9) {
      rmat[0]![c]! /= norm;
      rmat[1]![c]! /= norm;
      rmat[2]![c]! /= norm;
    }
  }

  const sy = Math.hypot(rmat[0]![0]!, rmat[1]![0]!);
  let yaw: number;
  let pitch: number;
  let roll: number;

  if (sy > 1e-6) {
    yaw = Math.atan2(-rmat[2]![0]!, sy);
    pitch = Math.atan2(rmat[2]![1]!, rmat[2]![2]!);
    roll = Math.atan2(rmat[1]![0]!, rmat[0]![0]!);
  } else {
    yaw = Math.atan2(-rmat[2]![0]!, sy);
    pitch = Math.atan2(-rmat[1]![2]!, rmat[1]![1]!);
    roll = 0.0;
  }

  return normaliseAngles(
    (yaw * 180) / Math.PI,
    (pitch * 180) / Math.PI,
    (roll * 180) / Math.PI
  );
}

describe('FaceMetrics Math Port', () => {
  it('computes EAR correctly for standard eye landmark coordinates', () => {
    // Synthetic eye: horizontal corners at x=10, x=30 (width=20)
    // Vertical lids: p2(15, 12), p6(15, 18) -> dist=6
    //               p3(25, 12), p5(25, 18) -> dist=6
    // EAR = (6 + 6) / (2 * 20) = 12 / 40 = 0.30
    const pts: [number, number][] = new Array(500).fill([0, 0]);
    pts[RIGHT_EYE_EAR[0]] = [10, 15]; // p1
    pts[RIGHT_EYE_EAR[1]] = [15, 12]; // p2
    pts[RIGHT_EYE_EAR[2]] = [25, 12]; // p3
    pts[RIGHT_EYE_EAR[3]] = [30, 15]; // p4
    pts[RIGHT_EYE_EAR[4]] = [25, 18]; // p5
    pts[RIGHT_EYE_EAR[5]] = [15, 18]; // p6

    const ear = eyeAspectRatio(pts, RIGHT_EYE_EAR);
    expect(ear).toBeCloseTo(0.30, 5);

    // Also verify with LEFT_EYE_EAR
    pts[LEFT_EYE_EAR[0]] = [10, 15];
    pts[LEFT_EYE_EAR[1]] = [15, 12];
    pts[LEFT_EYE_EAR[2]] = [25, 12];
    pts[LEFT_EYE_EAR[3]] = [30, 15];
    pts[LEFT_EYE_EAR[4]] = [25, 18];
    pts[LEFT_EYE_EAR[5]] = [15, 18];
    const leftEar = eyeAspectRatio(pts, LEFT_EYE_EAR);
    expect(leftEar).toBeCloseTo(0.30, 5);
  });

  it('returns null for collapsed eye landmarks (horizontal < 1e-6)', () => {
    const pts: [number, number][] = new Array(500).fill([10, 10]);
    const ear = eyeAspectRatio(pts, RIGHT_EYE_EAR);
    expect(ear).toBeNull();
  });

  it('combineEar uses mean of both when valid, else whichever survives', () => {
    expect(combineEar(0.30, 0.34)).toBeCloseTo(0.32, 5);
    expect(combineEar(0.30, null)).toBeCloseTo(0.30, 5);
    expect(combineEar(null, 0.28)).toBeCloseTo(0.28, 5);
    expect(combineEar(null, null)).toBeNull();
  });

  it('gates ear validity on yaw <= 30 and pitch <= 25', () => {
    expect(isEarValid(0, 0, 0.30)).toBe(true);
    expect(isEarValid(29, 20, 0.30)).toBe(true);
    expect(isEarValid(35, 10, 0.30)).toBe(false);
    expect(isEarValid(-31, 10, 0.30)).toBe(false);
    expect(isEarValid(10, 26, 0.30)).toBe(false);
    expect(isEarValid(10, -26, 0.30)).toBe(false);
    expect(isEarValid(0, 0, null)).toBe(false);
  });

  it('normaliseAngles leaves normal angles alone and wraps degenerates', () => {
    const [y, p, r] = normaliseAngles(-20.0, 15.0, -8.0);
    expect(y).toBeCloseTo(-20.0, 4);
    expect(p).toBeCloseTo(15.0, 4);
    expect(r).toBeCloseTo(-8.0, 4);

    const [, pWrap] = normaliseAngles(0, 175.0, 0);
    expect(Math.abs(pWrap)).toBeLessThanOrEqual(90.0);
  });

  it('decomposes identity matrix to 0 yaw, pitch, roll', () => {
    // Identity 4x4 matrix
    const identity = [
      1, 0, 0, 0,
      0, 1, 0, 0,
      0, 0, 1, 0,
      0, 0, 0, 1,
    ];
    const pose = headPoseFromMatrix(identity);
    expect(pose).not.toBeNull();
    expect(pose![0]).toBeCloseTo(0, 4);
    expect(pose![1]).toBeCloseTo(0, 4);
    expect(pose![2]).toBeCloseTo(0, 4);
  });
});
