"""Write a printable ArUco scale marker (DICT_4X4_50, id 0).

Print at 100% / "actual size". The black square must measure exactly MARKER_MM (default 20 mm);
check with a ruler. Place it flat on the skin, in the same plane as the area photographed.

Usage:  python tools/make_marker.py data/urtiscan_marker.png [--mm 20] [--dpi 300]
"""
import argparse

import cv2
import numpy as np

p = argparse.ArgumentParser()
p.add_argument("out")
p.add_argument("--mm", type=float, default=20.0)
p.add_argument("--dpi", type=int, default=300)
args = p.parse_args()

side = int(round(args.mm / 25.4 * args.dpi))
tag = cv2.aruco.generateImageMarker(cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50), 0, side)
pad = side // 4
canvas = np.full((side + 2 * pad, side + 2 * pad), 255, np.uint8)
canvas[pad : pad + side, pad : pad + side] = tag
cv2.imwrite(args.out, canvas)
print(f"Wrote {args.out}: {args.mm} mm marker at {args.dpi} dpi ({side}px). Print at 100% scale.")
