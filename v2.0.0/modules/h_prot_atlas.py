#!/usr/bin/env python3
import glob
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pymodule_common import load_config, record_refs, record_version

hprotatlas_autop2_version = "2.0.0"
hprotatlas_docker_version = "1.0.0"
hprotatlas_ref = "Uhlén M et al. (2015)"
hprotatlas_doi = "10.1126/science.1260419"


def main():
    global hprotatlas_autop2_version, hprotatlas_docker_version
    global hprotatlas_ref, hprotatlas_doi

    if len(sys.argv) < 4:
        sys.exit("Usage: h_prot_atlas.py <input_dir> <out_dir> <prefix>")

    input_dir, out_dir, prefix = sys.argv[1], sys.argv[2], sys.argv[3]
    load_config()

    if os.environ.get("hprotatlas_docker_c_version"):
        hprotatlas_autop2_version = "?"
        hprotatlas_docker_version = os.environ["hprotatlas_docker_c_version"]
        hprotatlas_ref = "?"
        hprotatlas_doi = "?"

    host_dir = os.environ.get("dir", "")
    work_dir = f"/data/{prefix}h_prot_atlas"
    final_dir = f"/data/{out_dir}"
    os.makedirs(work_dir, exist_ok=True)
    os.makedirs(final_dir, exist_ok=True)

    h_prot_atlas_inc = os.environ.get("h_prot_atlas_inc", "")
    h_prot_atlas_mode = os.environ.get("h_prot_atlas_mode", "")
    h_prot_atlas_exc = os.environ.get("h_prot_atlas_exc", "")

    config_path = os.path.join(work_dir, "config")
    with open(config_path, "w") as f:
        f.write(f"human_prot_atlas_tissue_include={h_prot_atlas_inc}\n")
        f.write(f"human_prot_atlas_tissue_include_mode={h_prot_atlas_mode}\n")
        f.write(f"human_prot_atlas_tissue_exclude={h_prot_atlas_exc}\n")

    input_path = os.path.join(work_dir, "input")
    sources = sorted(p for p in glob.glob(f"/data/{input_dir}/*") if os.path.isfile(p))
    with open(input_path, "w") as out_f:
        for src in sources:
            with open(src) as in_f:
                out_f.write(in_f.read())

    output_path = os.path.join(work_dir, "h_prot_atlas_output.unp")
    subprocess.run(
        [
            "docker", "run", "--rm",
            "-v", f"{host_dir}/{prefix}h_prot_atlas:/data",
            "-w", "/data",
            f"pegi3s/human_prot_atlas:{hprotatlas_docker_version}",
            "config", "input", "h_prot_atlas_output.unp",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    if os.path.isfile(output_path):
        shutil.copy2(output_path, final_dir)

    if not os.path.isfile(output_path) or os.path.getsize(output_path) == 0:
        with open(input_path) as f:
            input_count = sum(1 for _ in f)
        print("Warning: h_prot_atlas produced an empty output file.")
        print(
            f"This is expected (not a bug) if every one of the {input_count} input "
            "UniProtKB ID(s) is also 'detected' in an excluded tissue "
            f"(human_prot_atlas_tissue_exclude={h_prot_atlas_exc}), since the Human "
            "Protein Atlas tool considers even low-level RNA detection as a match."
        )
        print(
            "Review human_prot_atlas_tissue_include/human_prot_atlas_tissue_exclude "
            "in the config below if this result is unexpected:"
        )
        with open(config_path) as f:
            print(f.read(), end="")

    record_version(
        f'h_prot_atlas {hprotatlas_autop2_version},'
        f'pegi3s/human_prot_atlas:{hprotatlas_docker_version},,'
        f'"{hprotatlas_ref}","{hprotatlas_doi}"'
    )
    record_refs(
        f'hprotatlas_ref="{hprotatlas_ref}"\n'
        f'hprotatlas_doi="{hprotatlas_doi}"\n'
    )


if __name__ == "__main__":
    print("Filtering UniProtKb numbers using the Human Protein Atlas", flush=True)
    main()
