"""Extra training augmentations for the gray crops (applied before Ultralytics' own crop / flip /
erasing): fisheye or barrel lens warp, perspective tilt up to +-15 deg, brightness / contrast, blur,
noise. Works on a PIL image, returns a PIL image (Ultralytics' classify pipeline is PIL based)."""
import math
import random

import cv2
import numpy as np
from PIL import Image


def lens(img, k):
    """Radial warp: k > 0 barrel / fisheye look, k < 0 pincushion."""
    h, w = img.shape[:2]
    yy, xx = np.indices((h, w), dtype=np.float32)
    x = (xx - w / 2) / (w / 2)
    y = (yy - h / 2) / (h / 2)
    r2 = x * x + y * y
    f = (1 + k * r2) / (1 + k)  # edge midpoints stay in place
    mx = (x * f) * (w / 2) + w / 2
    my = (y * f) * (h / 2) + h / 2
    return cv2.remap(img, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)


def tilt(img, max_deg=15):
    """Perspective as if the camera were turned up to max_deg about a random axis."""
    h, w = img.shape[:2]
    a = math.radians(random.uniform(-max_deg, max_deg))
    b = math.radians(random.uniform(-max_deg, max_deg))
    f = 1.2 * max(w, h)
    rx = np.array([[1, 0, 0], [0, math.cos(a), -math.sin(a)], [0, math.sin(a), math.cos(a)]])
    ry = np.array([[math.cos(b), 0, math.sin(b)], [0, 1, 0], [-math.sin(b), 0, math.cos(b)]])
    k = np.array([[f, 0, w / 2], [0, f, h / 2], [0, 0, 1]])
    hm = k @ ry @ rx @ np.linalg.inv(k)
    rot = random.uniform(-10, 10)
    r2 = cv2.getRotationMatrix2D((w / 2, h / 2), rot, 1.15)  # zoom in: fewer empty borders
    hm = np.vstack([r2, [0, 0, 1]]) @ hm
    return cv2.warpPerspective(img, hm, (w, h), borderMode=cv2.BORDER_REPLICATE)


def photometric(img):
    x = img.astype(np.float32)
    x = (x - 128) * random.uniform(0.6, 1.4) + 128 + random.uniform(-40, 40)
    if random.random() < 0.3:  # gamma, mimics IR auto-exposure
        x = 255 * (np.clip(x, 0, 255) / 255) ** random.uniform(0.6, 1.6)
    return np.clip(x, 0, 255).astype(np.uint8)


def blur(img):
    if random.random() < 0.5:
        s = random.choice((3, 5, 7))
        return cv2.GaussianBlur(img, (s, s), 0)
    n = random.choice((5, 7, 9))
    kern = np.zeros((n, n), np.float32)
    kern[n // 2] = 1.0 / n
    m = cv2.getRotationMatrix2D((n / 2 - 0.5, n / 2 - 0.5), random.uniform(0, 180), 1.0)
    kern = cv2.warpAffine(kern, m, (n, n))
    return cv2.filter2D(img, -1, kern / max(kern.sum(), 1e-6))


def noise(img):
    sd = random.uniform(3, 15)
    return np.clip(img.astype(np.float32) + np.random.normal(0, sd, img.shape), 0,
                   255).astype(np.uint8)


class CropAug:
    """p = probability of each op. Picklable (DataLoader workers on Windows)."""

    def __init__(self, p_lens=0.4, p_tilt=0.5, p_photo=0.8, p_blur=0.3, p_noise=0.3):
        self.p = (p_lens, p_tilt, p_photo, p_blur, p_noise)

    def __call__(self, im):
        g = np.asarray(im.convert("L"))
        pl, pt, pp, pb, pn = self.p
        if random.random() < pl:
            g = lens(g, random.uniform(-0.1, 0.3))
        if random.random() < pt:
            g = tilt(g)
        if random.random() < pp:
            g = photometric(g)
        if random.random() < pb:
            g = blur(g)
        if random.random() < pn:
            g = noise(g)
        return Image.fromarray(g).convert("RGB")
