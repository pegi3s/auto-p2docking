#!/usr/bin/env python3
import glob
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pymodule_common import load_config, record_refs, record_version, remove_empty_files

getalphafoldpdb_autop2_version = "2.0.0"
getalphafoldpdb_docker_version = "1.0.1-docker29.0.1"
getalphafoldpdb_ref = "Jumper, J et al. (2021)"
getalphafoldpdb_doi = "10.1038/s41586-021-03819-2"


def main():
    global getalphafoldpdb_autop2_version, getalphafoldpdb_docker_version
    global getalphafoldpdb_ref, getalphafoldpdb_doi

    if len(sys.argv) < 4:
        sys.exit("Usage: getalphafoldpdb.py <input_dir> <out_dir> <prefix>")

    input_dir, out_dir, prefix = sys.argv[1], sys.argv[2], sys.argv[3]
    load_config()

    if os.environ.get("getalphafoldpdb_docker_c_version"):
        getalphafoldpdb_autop2_version = "?"
        getalphafoldpdb_docker_version = os.environ["getalphafoldpdb_docker_c_version"]
        getalphafoldpdb_ref = "?"
        getalphafoldpdb_doi = "?"

    host_dir = os.environ.get("dir", "")
    work_dir = f"/data/{prefix}alphafold"
    final_dir = f"/data/{out_dir}"
    os.makedirs(work_dir, exist_ok=True)
    os.makedirs(final_dir, exist_ok=True)

    for path in sorted(glob.glob(f"/data/{input_dir}/*")):
        if os.path.isfile(path):
            shutil.copy2(path, work_dir)

    uniprot_id_file = os.path.join(work_dir, "uniprotIDFile")
    with open(uniprot_id_file, "w") as out_f:
        for path in sorted(glob.glob(os.path.join(work_dir, "*"))):
            if os.path.isfile(path) and path != uniprot_id_file:
                with open(path) as in_f:
                    out_f.write(in_f.read())

    subprocess.run(
        [
            "docker", "run", "--rm",
            "-v", f"{host_dir}/{prefix}alphafold:/data",
            f"pegi3s/alphafold_db:{getalphafoldpdb_docker_version}",
            "bash", "-c", "/opt/run /data/uniprotIDFile",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    structures_dir = os.path.join(work_dir, "Structures_from_AlphaFold")
    names = sorted(os.listdir(structures_dir)) if os.path.isdir(structures_dir) else []

    for name in names:
        name_dir = os.path.join(structures_dir, name)
        if not os.path.isdir(name_dir):
            continue
        entries = sorted(os.listdir(name_dir))
        if not entries:
            continue
        src_file = os.path.join(name_dir, entries[0])
        dest_name = f"{name}_AF.pdb"
        renamed_path = os.path.join(name_dir, dest_name)
        shutil.move(src_file, renamed_path)
        shutil.copy2(renamed_path, os.path.join(final_dir, dest_name))
        remove_empty_files(final_dir)

    record_version(
        f'getalphafoldpdb {getalphafoldpdb_autop2_version},'
        f'pegi3s/alphafold_db:{getalphafoldpdb_docker_version},,'
        f'"{getalphafoldpdb_ref}","{getalphafoldpdb_doi}"'
    )
    record_refs(
        f'getalphafoldpdb_ref="{getalphafoldpdb_ref}"\n'
        f'getalphafoldpdb_doi="{getalphafoldpdb_doi}"\n'
    )


if __name__ == "__main__":
    print("Downloading PDBs from Alphafold database", flush=True)
    main()
