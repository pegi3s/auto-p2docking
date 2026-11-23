#!/usr/bin/env python3
import glob
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pymodule_common import load_config, record_version

intersect_autop2_version = "2.0.0"


def main():
    if len(sys.argv) < 4:
        sys.exit("Usage: intersect.py <input_dir> <out_dir> <prefix>")

    input_dir, out_dir, prefix = sys.argv[1], sys.argv[2], sys.argv[3]

    load_config()

    work_dir = f"/data/{prefix}UniprotKB_or_GI_intersection"
    final_dir = f"/data/{out_dir}"
    os.makedirs(work_dir, exist_ok=True)
    os.makedirs(final_dir, exist_ok=True)

    lines = []
    for path in sorted(glob.glob(f"/data/{input_dir}/*")):
        if os.path.isfile(path):
            with open(path) as f:
                lines.extend(f.read().splitlines())

    counts = Counter(lines)
    duplicates = sorted(line for line, count in counts.items() if count > 1)

    extension = "unp" if any(c.isalpha() for line in duplicates for c in line) else "gi"

    intersection_path = os.path.join(work_dir, f"intersection.{extension}")
    with open(intersection_path, "w") as f:
        for line in duplicates:
            f.write(line + "\n")

    dest_path = os.path.join(final_dir, f"intersection.{extension}")
    with open(intersection_path, "rb") as src, open(dest_path, "wb") as dst:
        dst.write(src.read())

    record_version(f"intersect {intersect_autop2_version}")


if __name__ == "__main__":
    print("Intersecting UniprotKB/GI lists", flush=True)
    main()
