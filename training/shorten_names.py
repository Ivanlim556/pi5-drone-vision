"""Rename a YOLO dataset's images + labels to short names (split_00001.jpg / .txt).
Roboflow exports keep the original ~200-character file names, which push paths past Windows'
260-character limit. Usage: python shorten_names.py <dataset folder>"""
import os
import sys

root = os.path.abspath(sys.argv[1])


def L(p):  # the \\?\ prefix reaches paths longer than 260 characters
    return "\\\\?\\" + os.path.join(root, p).replace("/", "\\")


for split in ("train", "valid", "test"):
    if not os.path.isdir(L(f"{split}/images")):
        continue
    imgs = sorted(f for f in os.listdir(L(f"{split}/images")) if not f.startswith(split + "_"))
    labels = set(os.listdir(L(f"{split}/labels")))
    missing = 0
    for i, img in enumerate(imgs, 1):
        stem, ext = os.path.splitext(img)
        new = f"{split}_{i:05d}"
        os.rename(L(f"{split}/images/{img}"), L(f"{split}/images/{new}{ext.lower()}"))
        if stem + ".txt" in labels:
            os.rename(L(f"{split}/labels/{stem}.txt"), L(f"{split}/labels/{new}.txt"))
        else:
            missing += 1
    orphans = [f for f in os.listdir(L(f"{split}/labels")) if not f.startswith(split + "_")]
    print(f"{split}: renamed {len(imgs)} images, {missing} without a label, {len(orphans)} orphan labels")
