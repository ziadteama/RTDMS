"""Make public, colour, pinhole images look like our camera: grayscale, head-and-shoulders crop,
160-degree fisheye geometry, IR appearance, objects partly hidden by hands.

Boxes are (cls, x1, y1, x2, y2) in pixels throughout. Every function takes an explicit
numpy Generator so a split can be converted reproducibly.

Note on geometry: at runtime the driver ROI is rectified (roi.py), so the detector sees a
near-pinhole view whose remaining traits are off-axis stretch and LOW RESOLUTION (the periphery
of a 160-degree lens has few pixels per degree, upsampled by the remap). barrel() therefore
models the raw lens and is applied at moderate strength on part of the data; resolution loss in
ir_look() matters more and is always applied.
"""

from __future__ import annotations

import math

import cv2
import numpy as np

from .calibration import FisheyeCalibration

Box = tuple[int, float, float, float, float]


def to_gray3(img: np.ndarray) -> np.ndarray:
    g = img if img.ndim == 2 else cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return cv2.cvtColor(g, cv2.COLOR_GRAY2BGR)


def clip_boxes(boxes: list[Box], w: int, h: int, min_size: float = 4.0,
               min_keep: float = 0.4, orig: list[Box] | None = None) -> list[Box]:
    """Clip to the image; drop boxes that become tiny or lose most of their area."""
    out = []
    for i, (c, x1, y1, x2, y2) in enumerate(boxes):
        nx1, ny1, nx2, ny2 = max(0.0, x1), max(0.0, y1), min(float(w), x2), min(float(h), y2)
        if nx2 - nx1 < min_size or ny2 - ny1 < min_size:
            continue
        area0 = (x2 - x1) * (y2 - y1) if orig is None else \
            (orig[i][3] - orig[i][1]) * (orig[i][4] - orig[i][2])
        if area0 > 0 and (nx2 - nx1) * (ny2 - ny1) / area0 < min_keep:
            continue
        out.append((c, nx1, ny1, nx2, ny2))
    return out


# --------------------------------------------------------------------------- crop


def head_shoulders_crop(img: np.ndarray, boxes: list[Box], faces: list[tuple], rng,
                        object_classes=(0, 1, 2)) -> tuple[np.ndarray, list[Box]]:
    """Square crop framed like our driver ROI: the face (if known) in the upper part, the
    objects inside, about 3-5 face widths across. Falls back to a square around the objects."""
    h, w = img.shape[:2]
    objs = [b for b in boxes if b[0] in object_classes] or boxes
    if not objs:
        return img, boxes
    ox1 = min(b[1] for b in objs)
    oy1 = min(b[2] for b in objs)
    ox2 = max(b[3] for b in objs)
    oy2 = max(b[4] for b in objs)
    use_face = False
    if faces:  # nearest face to the objects, in pixels
        cx, cy = (ox1 + ox2) / 2, (oy1 + oy2) / 2
        f = min(faces, key=lambda fb: (((fb[0] + fb[2]) / 2) * w - cx) ** 2 +
                (((fb[1] + fb[3]) / 2) * h - cy) ** 2)
        fx1, fy1, fx2, fy2 = f[0] * w, f[1] * h, f[2] * w, f[3] * h
        fw = fx2 - fx1
        ux1, uy1 = min(ox1, fx1), max(0.0, min(oy1, fy1 - 0.4 * fw))
        ux2, uy2 = max(ox2, fx2), max(oy2, fy2)
        # The window must hold face AND objects; a face far from the objects (someone else, or
        # a wide shot) would make the crop unlike a driver ROI, so it is ignored.
        use_face = fw > 0 and max(ux2 - ux1, uy2 - uy1) <= 6 * fw
    if use_face:
        side = max(fw * rng.uniform(3.0, 5.0), ux2 - ux1, uy2 - uy1) * 1.05
    else:
        ux1, uy1, ux2, uy2 = ox1, oy1, ox2, oy2
        side = max(ox2 - ox1, oy2 - oy1) * rng.uniform(1.6, 3.0)
    side = min(side, float(min(w, h)))
    if side < max(ux2 - ux1, uy2 - uy1):  # cannot fit everything in a square: keep the image
        return img, boxes
    # Place the window so it contains the union box where possible, with random slack.
    x0 = rng.uniform(ux2 - side, ux1) if ux2 - ux1 < side else ux1
    y0 = rng.uniform(uy2 - side, uy1) if uy2 - uy1 < side else uy1
    x0 = float(np.clip(x0, 0, max(0.0, w - side)))
    y0 = float(np.clip(y0, 0, max(0.0, h - side)))
    x1i, y1i = int(x0), int(y0)
    x2i, y2i = int(min(w, x0 + side)), int(min(h, y0 + side))
    crop = img[y1i:y2i, x1i:x2i]
    moved = [(c, a - x1i, b - y1i, d - x1i, e - y1i) for c, a, b, d, e in boxes]
    return crop, clip_boxes(moved, crop.shape[1], crop.shape[0], orig=moved)


# --------------------------------------------------------------------------- fisheye


def barrel(img: np.ndarray, boxes: list[Box], rng, fov_deg: float | None = None,
           calib: FisheyeCalibration | None = None) -> tuple[np.ndarray, list[Box]]:
    """Re-project a pinhole image through an equidistant fisheye with a random off-centre
    optical axis (the driver sits off-axis). With `calib`, the real lens's D coefficients shape
    the radial curve; otherwise a generic equidistant lens is used.

    fov_deg is the horizontal field of view assumed for the INPUT pinhole image; wider = stronger
    distortion. Output keeps the input size."""
    h, w = img.shape[:2]
    fov = fov_deg if fov_deg is not None else rng.uniform(60, 100)
    f_p = (w / 2) / math.tan(math.radians(fov) / 2)
    # Optical centre placed off the image centre, like the driver region of a mirror camera.
    cx = w / 2 + rng.uniform(-0.35, 0.35) * w
    cy = h / 2 + rng.uniform(-0.25, 0.25) * h
    corners = np.array([[0, 0], [w, 0], [0, h], [w, h]], np.float64) - (cx, cy)
    theta_max = math.atan(np.linalg.norm(corners, axis=1).max() / f_p)
    d = calib.D.ravel() if calib is not None else np.zeros(4)

    def distort(theta):
        t2 = theta * theta
        return theta * (1 + d[0] * t2 + d[1] * t2**2 + d[2] * t2**3 + d[3] * t2**4)

    r_max = np.linalg.norm(corners, axis=1).max()
    f_f = r_max / distort(theta_max)  # keep the content in frame
    # Inverse map: output pixel -> source pixel. Invert theta_d -> theta with a lookup table.
    tt = np.linspace(0, theta_max, 2048)
    td = distort(tt)
    ys, xs = np.mgrid[0:h, 0:w].astype(np.float64)
    dx, dy = xs - cx, ys - cy
    rho = np.hypot(dx, dy)
    theta = np.interp(rho / f_f, td, tt)
    r_src = f_p * np.tan(theta)
    scale = np.divide(r_src, rho, out=np.ones_like(rho), where=rho > 1e-9)
    map_x = (cx + dx * scale).astype(np.float32)
    map_y = (cy + dy * scale).astype(np.float32)
    out = cv2.remap(img, map_x, map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)

    def fwd(px, py):  # source pixel -> output pixel
        ddx, ddy = px - cx, py - cy
        r = np.hypot(ddx, ddy)
        rho_o = f_f * distort(np.arctan(r / f_p))
        s = np.divide(rho_o, r, out=np.ones_like(r), where=r > 1e-9)
        return cx + ddx * s, cy + ddy * s

    new = []
    t = np.linspace(0, 1, 12)
    for c, x1, y1, x2, y2 in boxes:
        ex = np.concatenate([x1 + t * (x2 - x1), x1 + t * (x2 - x1), np.full(12, x1),
                             np.full(12, x2)])
        ey = np.concatenate([np.full(12, y1), np.full(12, y2), y1 + t * (y2 - y1),
                             y1 + t * (y2 - y1)])
        qx, qy = fwd(ex, ey)
        new.append((c, float(qx.min()), float(qy.min()), float(qx.max()), float(qy.max())))
    return out, clip_boxes(new, w, h, orig=new)


# --------------------------------------------------------------------------- IR look


def ir_look(img: np.ndarray, rng, strength: float = 1.0) -> np.ndarray:
    """Grayscale NoIR/IR appearance. Photometric only: boxes are unchanged."""
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0
    h, w = g.shape
    s = strength
    # Bright skin: IR reflectance of skin is high, so mid-to-bright tones get lifted.
    lift = rng.uniform(0.0, 0.35) * s
    g = g + lift * np.clip((g - 0.35) / 0.4, 0, 1) * (1 - g)
    # Low contrast + exposure / gamma shifts.
    g = (g - g.mean()) * rng.uniform(1 - 0.5 * s, 1.0) + g.mean() + rng.uniform(-0.08, 0.12) * s
    g = np.clip(g, 0, 1) ** rng.uniform(0.7, 1.4)
    # Vignetting (wide lens).
    yy, xx = np.mgrid[0:h, 0:w]
    r2 = ((xx - w * rng.uniform(0.3, 0.7)) / w) ** 2 + ((yy - h * rng.uniform(0.3, 0.7)) / h) ** 2
    g *= 1 - rng.uniform(0.0, 0.6) * s * np.clip(r2 / 0.5, 0, 1)
    # Resolution loss (rectified periphery of a 160-degree lens) and blur.
    f = rng.uniform(0.35, 0.9)
    small = cv2.resize(g, (max(8, int(w * f)), max(8, int(h * f))), interpolation=cv2.INTER_AREA)
    g = cv2.resize(small, (w, h), interpolation=cv2.INTER_LINEAR)
    if rng.random() < 0.5:
        k = int(rng.integers(1, 3)) * 2 + 1
        g = cv2.GaussianBlur(g, (k, k), 0)
    if rng.random() < 0.3:  # motion blur
        k = int(rng.integers(3, 9))
        kern = np.zeros((k, k), np.float32)
        kern[k // 2, :] = 1.0 / k
        rot = cv2.getRotationMatrix2D((k / 2 - 0.5, k / 2 - 0.5), rng.uniform(0, 180), 1)
        kern = cv2.warpAffine(kern, rot, (k, k))
        g = cv2.filter2D(g, -1, kern / max(kern.sum(), 1e-6))
    # Sensor noise: shot (signal-dependent) + read noise.
    g = g + rng.normal(0, 1, g.shape).astype(np.float32) * (
        np.sqrt(np.clip(g, 0, 1)) * rng.uniform(0.0, 0.05) * s + rng.uniform(0.005, 0.03) * s)
    out = (np.clip(g, 0, 1) * 255).astype(np.uint8)
    if rng.random() < 0.5:  # JPEG / H.264-ish blocking
        ok, enc = cv2.imencode(".jpg", out, [cv2.IMWRITE_JPEG_QUALITY, int(rng.integers(35, 85))])
        out = cv2.imdecode(enc, cv2.IMREAD_GRAYSCALE)
    return cv2.cvtColor(out, cv2.COLOR_GRAY2BGR)


# --------------------------------------------------------------------------- occlusion


def occlude(img: np.ndarray, boxes: list[Box], rng, p: float = 0.5,
            classes=(0, 1, 2)) -> np.ndarray:
    """Hand-sized blobs partly covering phones / drinks / food (fingers around a phone, a hand
    around a cup). Covers 15-55 % of the box, so the label stays valid. Bright, low-texture
    tone, like skin under IR."""
    out = img.copy()
    h, w = img.shape[:2]
    for c, x1, y1, x2, y2 in boxes:
        if c not in classes or rng.random() > p:
            continue
        bw, bh = x2 - x1, y2 - y1
        frac = rng.uniform(0.15, 0.55)
        # Blob enters from a random side of the box, like fingers wrapping it.
        side = int(rng.integers(4))
        ax, ay = (bw * rng.uniform(0.35, 0.8), bh * math.sqrt(frac)) if side < 2 else \
            (bw * math.sqrt(frac), bh * rng.uniform(0.35, 0.8))
        cx = {0: (x1 + x2) / 2, 1: (x1 + x2) / 2, 2: x1, 3: x2}[side] + rng.normal(0, 0.1) * bw
        cy = {0: y1, 1: y2, 2: (y1 + y2) / 2, 3: (y1 + y2) / 2}[side] + rng.normal(0, 0.1) * bh
        mask = np.zeros((h, w), np.uint8)
        cv2.ellipse(mask, (int(cx), int(cy)), (max(2, int(ax)), max(2, int(ay))),
                    rng.uniform(-30, 30), 0, 360, 255, -1)
        mask = cv2.GaussianBlur(mask, (7, 7), 0).astype(np.float32)[..., None] / 255.0
        tone = rng.uniform(140, 235)
        tex = np.clip(tone + rng.normal(0, 6, (h, w, 1)), 0, 255).astype(np.float32)
        tex = np.repeat(tex, 3, axis=2)
        out = (out.astype(np.float32) * (1 - mask) + tex * mask).astype(np.uint8)
    return out


def convert(img: np.ndarray, boxes: list[Box], faces: list[tuple], rng, *,
            out_size: int = 640, crop: bool = True, p_barrel: float = 0.5,
            p_occlude: float = 0.5, calib: FisheyeCalibration | None = None
            ) -> tuple[np.ndarray, list[Box]]:
    """Full offline conversion of one image."""
    if crop:
        img, boxes = head_shoulders_crop(img, boxes, faces, rng)
    if rng.random() < p_barrel:
        img, boxes = barrel(img, boxes, rng, calib=calib)
    img = occlude(img, boxes, rng, p=p_occlude)
    img = ir_look(img, rng)
    h, w = img.shape[:2]
    s = out_size / max(h, w)
    if s < 1:
        img = cv2.resize(img, (round(w * s), round(h * s)), interpolation=cv2.INTER_AREA)
        boxes = [(c, a * s, b * s, d * s, e * s) for c, a, b, d, e in boxes]
    return img, boxes
