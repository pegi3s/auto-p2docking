#!/usr/bin/env python3
"""auto-p2docking copy module, with receptor list generation added."""
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pymodule_common import load_config, record_version

copy_autop2_version = "2.0.0"


def _copy_tree_contents(src_dir, dest_dir):
    os.makedirs(dest_dir, exist_ok=True)
    for name in sorted(os.listdir(src_dir)):
        src_path = os.path.join(src_dir, name)
        dest_path = os.path.join(dest_dir, name)
        if os.path.isdir(src_path):
            shutil.copytree(src_path, dest_path, dirs_exist_ok=True)
        else:
            shutil.copy2(src_path, dest_path)


def _write_pdb_list(directory, destination):
    """Generate a list for just the PDBs copied into their canonical folder."""
    os.makedirs(os.path.dirname(destination), exist_ok=True)
    names = sorted(
        name for name in os.listdir(directory)
        if name.lower().endswith(".pdb") and os.path.isfile(os.path.join(directory, name))
    )
    with open(destination, "w", encoding="utf-8", newline="\n") as output:
        for name in names:
            output.write(name + "\n")


def main():
    if len(sys.argv) < 4:
        sys.exit("Usage: copy.py <input_dir> <out_dir> <prefix>")

    input_dir, out_dir, prefix = sys.argv[1], sys.argv[2], sys.argv[3]
    load_config()

    input_path = f"/data/{input_dir}"
    work_dir = f"/data/{prefix}Copy_files"
    final_dir = f"/data/{out_dir}"

    if not os.path.isdir(input_path):
        sys.exit(f"Error: copy input directory does not exist: {input_path}")

    _copy_tree_contents(input_path, work_dir)
    _copy_tree_contents(input_path, final_dir)

    project = os.environ.get("project", "")
    if out_dir == f"{project}/PDBs/Ligands":
        _write_pdb_list(final_dir, f"/data/{project}/PDBs/ligands_list.txt")
    elif out_dir == f"{project}/PDBs/Receptor":
        _write_pdb_list(final_dir, f"/data/{project}/PDBs/receptors_list.txt")

    record_version(f"copy {copy_autop2_version}")


if __name__ == "__main__":
    print("Copy files", flush=True)
    main()
