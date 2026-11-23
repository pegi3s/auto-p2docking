#!/usr/bin/env python3
import glob
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pymodule_common import load_config, record_refs, record_version, remove_empty_files

getditasserpdb_autop2_version = "2.0.0"
getditasserpdb_docker_version = "1.1.0"
getditasserpdb_ref = "Zheng et al. (2022)"
getditasserpdb_doi = ""


def main():
    global getditasserpdb_autop2_version, getditasserpdb_docker_version
    global getditasserpdb_ref, getditasserpdb_doi

    if len(sys.argv) < 4:
        sys.exit("Usage: getditasserpdb.py <input_dir> <out_dir> <prefix>")

    input_dir, out_dir, prefix = sys.argv[1], sys.argv[2], sys.argv[3]
    load_config()

    if os.environ.get("getditasserpdb_docker_c_version"):
        getditasserpdb_autop2_version = "?"
        getditasserpdb_docker_version = os.environ["getditasserpdb_docker_c_version"]
        getditasserpdb_ref = "?"
        getditasserpdb_doi = "?"

    host_dir = os.environ.get("dir", "")
    work_dir = f"/data/{prefix}HPmod"
    pdb_dir = os.path.join(work_dir, "pdb")
    final_dir = f"/data/{out_dir}"
    os.makedirs(work_dir, exist_ok=True)
    os.makedirs(final_dir, exist_ok=True)
    os.makedirs(pdb_dir, exist_ok=True)

    for path in sorted(glob.glob(f"/data/{input_dir}/*")):
        if os.path.isfile(path):
            shutil.copy2(path, work_dir)

    uniprot_id_file = os.path.join(work_dir, "uniprotIDFile")
    with open(uniprot_id_file, "w") as out_f:
        for path in sorted(glob.glob(os.path.join(work_dir, "*"))):
            if os.path.isfile(path) and os.path.basename(path) != "uniprotIDFile":
                with open(path) as in_f:
                    out_f.write(in_f.read())

    subprocess.run(
        [
            "docker", "run", "--rm",
            "-v", f"{host_dir}/{prefix}HPmod:/data",
            f"pegi3s/ditasser_db:{getditasserpdb_docker_version}",
            "bash", "-c", "/opt/getditasserpdb uniprotIDFile",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    remove_empty_files(work_dir)

    for pdb_path in sorted(glob.glob(os.path.join(work_dir, "*.pdb"))):
        shutil.copy2(pdb_path, pdb_dir)

    for name in sorted(os.listdir(pdb_dir)):
        path = os.path.join(pdb_dir, name)
        new_name = name.replace(".pdb", "") + "_ditasser.pdb"
        os.replace(path, os.path.join(pdb_dir, new_name))

    for path in sorted(glob.glob(os.path.join(pdb_dir, "*"))):
        shutil.copy2(path, final_dir)

    record_version(
        f'getditasserpdb {getditasserpdb_autop2_version},'
        f'pegi3s/ditasser_db:{getditasserpdb_docker_version},,'
        f'"{getditasserpdb_ref}","{getditasserpdb_doi}"'
    )
    record_refs(
        f'getditasserpdb_ref="{getditasserpdb_ref}"\n'
        f'getditasserpdb_doi="{getditasserpdb_doi}"\n'
    )


if __name__ == "__main__":
    print("Getting PDBs from the HPmod  (D-I-TASSER) database", flush=True)
    main()
