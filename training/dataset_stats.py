"""Objects per class, label format and image sizes of a YOLO dataset. Usage: python dataset_stats.py <folder>"""
import collections
import glob
import os
import random
import sys

import cv2
import yaml

root = sys.argv[1]
names = yaml.safe_load(open(os.path.join(root, "data.yaml")))["names"]
for split in ("train", "valid", "test"):
    files = glob.glob(os.path.join(root, split, "labels", "*.txt"))
    if not files:
        continue
    cnt, cols, empty = collections.Counter(), collections.Counter(), 0
    for f in files:
        lines = [l.split() for l in open(f) if l.strip()]
        empty += not lines
        for l in lines:
            cnt[names[int(l[0])]] += 1
            cols[len(l)] += 1
    print(f"{split:<5} {len(files)} images, {empty} with no objects, values per label line {dict(cols)}")
    print("      " + ", ".join(f"{n} {cnt[n]}" for n in names))
imgs = glob.glob(os.path.join(root, "train", "images", "*"))
print("image sizes (sample of 40):", dict(collections.Counter(cv2.imread(p).shape[:2] for p in random.sample(imgs, 40))))
