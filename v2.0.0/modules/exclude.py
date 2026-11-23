#!/usr/bin/env python3

import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pymodule_common import load_config, record_version

exclude_autop2_version = "2.0.0"


def main():
    if len(sys.argv) < 4:
        sys.exit("Usage: exclude.py <input_dir> <out_dir> <prefix>")

    input_dir, out_dir, prefix = sys.argv[1], sys.argv[2], sys.argv[3]

    load_config()

    work_dir = f"/data/{prefix}UniprotKB_or_GI_exclude"
    final_dir = f"/data/{out_dir}"
    os.makedirs(work_dir, exist_ok=True)
    os.makedirs(final_dir, exist_ok=True)

    archives = sorted(glob.glob(f"/data/{input_dir}/*"))
    if archives and "to_be_excluded" in os.path.basename(archives[0]):
        exclude_file = archives[0]
        main_file = archives[1] if len(archives) > 1 else None
    else:
        main_file = archives[0] if archives else None
        exclude_file = archives[1] if len(archives) > 1 else None

    kept = None
    if main_file and exclude_file and os.path.isfile(main_file) and os.path.isfile(exclude_file):
        with open(exclude_file) as f:
            patterns = f.read().splitlines()
        with open(main_file) as f:
            main_lines = f.read().splitlines()
        kept = [line for line in main_lines if not any(p in line for p in patterns)]
    else:
        print("one or more files were not found")

    if kept is not None:
        extension = "unp" if any(c.isalpha() for line in kept for c in line) else "gi"

        exclude_list_path = os.path.join(work_dir, f"exclude_list.{extension}")
        with open(exclude_list_path, "w") as f:
            for line in kept:
                f.write(line + "\n")

        dest_path = os.path.join(final_dir, f"exclude_list.{extension}")
        with open(exclude_list_path, "rb") as src, open(dest_path, "wb") as dst:
            dst.write(src.read())

    record_version(f"exclude {exclude_autop2_version}")


if __name__ == "__main__":
    print("exclude UniprotKB or GI numbers", flush=True)
    main()
