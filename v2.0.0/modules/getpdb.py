#!/usr/bin/env python3
import glob
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pymodule_common import load_config, record_refs, record_version, remove_empty_files

getpdb_autop2_version = "2.0.0"
getpdb_docker_version = "1.0.0"
getpdb_ref = "Crystallography: Protein Data Bank. Nature New Biology, 233, 223 (1971)"
getpdb_doi = "10.1038/newbio233223b0"


def main():
    global getpdb_autop2_version, getpdb_docker_version, getpdb_ref, getpdb_doi

    if len(sys.argv) < 4:
        sys.exit("Usage: getpdb.py <input_dir> <out_dir> <prefix>")

    input_dir, out_dir, prefix = sys.argv[1], sys.argv[2], sys.argv[3]
    load_config()

    if os.environ.get("getpdb_docker_c_version"):
        getpdb_autop2_version = "?"
        getpdb_docker_version = os.environ["getpdb_docker_c_version"]
        getpdb_ref = "?"
        getpdb_doi = "?"

    host_dir = os.environ.get("dir", "")
    work_dir = f"/data/{prefix}PDB"
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

    with open(uniprot_id_file) as f:
        uniprot_numbers = f.read().splitlines()

    single_id_path = os.path.join(work_dir, "uniprotIDFile_1")
    for uniprot_number in uniprot_numbers:
        with open(single_id_path, "w") as f:
            f.write(uniprot_number + "\n")

        subprocess.run(
            [
                "docker", "run", "--rm",
                "-v", f"{host_dir}/{prefix}PDB:/data",
                f"pegi3s/getpdb:{getpdb_docker_version}",
                "bash", "-c", "/opt/getpdb uniprotIDFile_1",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        remove_empty_files(work_dir)

        for pdb_path in sorted(glob.glob(os.path.join(work_dir, "*.pdb"))):
            shutil.copy2(pdb_path, pdb_dir)

    if os.path.isfile(single_id_path):
        os.remove(single_id_path)

    for name in sorted(os.listdir(pdb_dir)):
        path = os.path.join(pdb_dir, name)
        new_name = name.replace(".pdb", "").replace("-", "_") + "_PDB.pdb"
        os.replace(path, os.path.join(pdb_dir, new_name))

    for path in sorted(glob.glob(os.path.join(pdb_dir, "*"))):
        shutil.copy2(path, final_dir)

    record_version(
        f'getpdb {getpdb_autop2_version},'
        f'pegi3s/getpdb:{getpdb_docker_version},,'
        f'"{getpdb_ref}","{getpdb_doi}"'
    )

    record_refs(
        f'getpdb_ref="{getpdb_ref}"\n'
        f'getpdb_doi="{getpdb_doi}"\n'
    )


if __name__ == "__main__":
    print("Getting PDBs from PDB database", flush=True)
    main()
