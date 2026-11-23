#!/usr/bin/env python3
import glob
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pymodule_common import load_config, record_version

pisaxmlextract_autop2_version = "2.0.0"
pisaxmlextract_docker_version = "0.24.0"


def main():
    global pisaxmlextract_autop2_version, pisaxmlextract_docker_version

    if len(sys.argv) < 4:
        sys.exit("Usage: pisa_xml_extract.py <input_dir> <out_dir> <prefix>")

    input_dir, out_dir, prefix = sys.argv[1], sys.argv[2], sys.argv[3]
    load_config()

    if os.environ.get("pisaxmlextract_docker_c_version"):
        pisaxmlextract_autop2_version = "?"
        pisaxmlextract_docker_version = os.environ["pisaxmlextract_docker_c_version"]

    host_dir = os.environ.get("dir", "")
    project = os.environ.get("project", "")

    work_input_dir = f"/data/{prefix}PISA_XML_extract/input"
    xml_dir = f"/data/{prefix}XML_file"
    out_path = f"/data/{out_dir}"
    os.makedirs(work_input_dir, exist_ok=True)
    os.makedirs(xml_dir, exist_ok=True)
    os.makedirs(out_path, exist_ok=True)
    os.makedirs(f"/data/{project}/PDBs", exist_ok=True)

    for path in sorted(glob.glob(f"/data/{input_dir}/*")):
        dest = os.path.join(work_input_dir, os.path.basename(path))
        if os.path.isdir(path):
            shutil.copytree(path, dest, dirs_exist_ok=True)
        else:
            shutil.copy2(path, work_input_dir)

    # run xml extract
    subprocess.run(
        [
            "docker", "run", "--rm",
            "-v", f"{host_dir}:/data",
            f"pegi3s/utilities:{pisaxmlextract_docker_version}",
            "pisa_xml_extract", f"/data/{prefix}PISA_XML_extract/input", f"/data/{prefix}XML_file",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    # copy files
    # NOTE: the bash original reuses the loop variable name "dir" here, which
    # shadows the global $dir config variable (host data directory) used for
    # the docker -v mount above. It is harmless in this script since $dir is
    # not referenced again after this point, but a distinct name is used here
    # (entry_path) to avoid any confusion in the Python port.
    for entry_path in sorted(glob.glob(f"/data/{input_dir}/*")):
        name = os.path.basename(entry_path)

        selection_dir = os.path.join(xml_dir, "selection", name)
        os.makedirs(os.path.join(selection_dir, name), exist_ok=True)

        entry_out_dir = os.path.join(out_path, name)
        if not os.path.isdir(entry_out_dir):
            os.mkdir(entry_out_dir)

        # NOTE: the dummy "name" subdirectory created just above also shows up
        # in this glob alongside any real output folder produced by the
        # docker tool. The bash original captures every "ls -d" match into a
        # single (possibly multi-line) string and runs it through "basename",
        # which effectively keeps only the alphabetically-last match. This is
        # replicated here by sorting and taking the last entry.
        candidates = sorted(glob.glob(os.path.join(selection_dir, "*")))
        folder_name = os.path.basename(candidates[-1])

        solution_dir = os.path.join(selection_dir, folder_name)
        os.rename(os.path.join(solution_dir, "summary"), os.path.join(solution_dir, f"{name}.tsv"))

        shutil.copy2(os.path.join(solution_dir, f"{name}.tsv"), os.path.join(entry_out_dir, f"{name}.tsv"))

    record_version(f"pisa_xml_extract {pisaxmlextract_autop2_version},pegi3s/utilities:{pisaxmlextract_docker_version}")


if __name__ == "__main__":
    print("PISA XML extract", flush=True)
    main()
