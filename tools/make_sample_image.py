"""Write a synthetic test photo (forearm with wheals and a 20 mm scale marker).

Usage:  python tools/make_sample_image.py data/sample_forearm.jpg [--tone light|medium|dark] [--seed N]
"""
import argparse
import sys
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from tests.synthetic import make_photo  # noqa: E402

p = argparse.ArgumentParser()
p.add_argument("out")
p.add_argument("--tone", default="light", choices=["light", "medium", "dark"])
p.add_argument("--seed", type=int, default=7)
args = p.parse_args()

photo = make_photo(seed=args.seed, n_isolated=14, n_pairs=3, tone=args.tone)
Path(args.out).parent.mkdir(parents=True, exist_ok=True)
cv2.imwrite(args.out, photo.image_bgr, [cv2.IMWRITE_JPEG_QUALITY, 92])
print(f"Wrote {args.out}: {len(photo.wheals)} synthetic wheals "
      f"({photo.separate_count} isolated + {len(photo.groups)} touching pairs)")
