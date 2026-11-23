#!/usr/bin/env python3
import glob
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pymodule_common import load_config, record_version
import pss_file

highlightregions_autop2_version = "2.0.0"
highlightregions_docker_version = "1.0.0"
highlightregions_ref = ""
highlightregions_doi = ""
pymol_docker_version = "2.3.0"
pymol_ref = ""
pymol_doi = ""


def main():
    global highlightregions_autop2_version, highlightregions_docker_version
    global highlightregions_ref, highlightregions_doi
    global pymol_docker_version, pymol_ref, pymol_doi

    if len(sys.argv) < 4:
        sys.exit("Usage: highlight_regions.py <input_dir> <out_dir> <prefix>")

    input_dir, out_dir, prefix = sys.argv[1], sys.argv[2], sys.argv[3]
    load_config()

    if os.environ.get("highlightregions_docker_c_version"):
        highlightregions_autop2_version = "?"
        highlightregions_docker_version = os.environ["highlightregions_docker_c_version"]
        highlightregions_ref = "?"
        highlightregions_doi = "?"

    if os.environ.get("pymol_docker_c_version"):
        pymol_docker_version = os.environ["pymol_docker_c_version"]
        pymol_ref = "?"
        pymol_doi = "?"

    host_dir = os.environ.get("dir", "")
    work_dir = f"/data/{prefix}highlight_regions"
    pymol_dir = os.path.join(work_dir, "pymol")
    final_dir = f"/data/{out_dir}"

    os.makedirs(work_dir, exist_ok=True)
    os.makedirs(pymol_dir, exist_ok=True)
    os.makedirs(final_dir, exist_ok=True)

    # Track only the structures actually received as inputs. This prevents
    # previously generated mapped.*.pdb files from being reprocessed.
    input_pdb_names = set()
    for path in sorted(glob.glob(f"/data/{input_dir}/*")):
        if os.path.isfile(path):
            shutil.copy2(path, work_dir)
            if path.lower().endswith(".pdb"):
                input_pdb_names.add(os.path.basename(path))

    for path in sorted(glob.glob("/data/files_to_keep/pisa_*_extract*/*/*.pdb")):
        shutil.copy2(path, work_dir)
        input_pdb_names.add(os.path.basename(path))

    pss_path = os.path.join(work_dir, "pss.txt")
    if os.path.isfile(pss_path):
        os.remove(pss_path)

    input_path = os.path.join(work_dir, "pattern_positions.txt")
    background_path = os.path.join(work_dir, "background.txt")
    with open(background_path, "w") as f:
        f.write("A 0\n")
        f.write("B 50\n")

    results = pss_file.process_positions(input_path)
    pss_file.write_to_file(pss_path, results)

    if not input_pdb_names:
        raise RuntimeError("No input PDB structures found for highlight_regions.")

    # For each input PDB, use only its canonical mapped.<original>.pdb result.
    # PSS-3D may also leave mapped.mapped.* files, which must not be exported
    # or sent to PyMOL as additional structures.
    pymol_pdb_paths = []
    for pdb_name in sorted(input_pdb_names):
        mapped_name = f"mapped.{pdb_name}"
        mapped_path = os.path.join(work_dir, mapped_name)
        if os.path.isfile(mapped_path):
            os.remove(mapped_path)

        result = subprocess.run(
            [
                "docker", "run", "--rm",
                "-v", f"/{host_dir}/{prefix}highlight_regions:/data",
                f"pegi3s/pss-3d:{highlightregions_docker_version}",
                "map",
                f"/data/{pdb_name}",
                "/data/pss.txt",
                "/data/background.txt",
            ],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            raise RuntimeError(
                f"PSS-3D failed for {pdb_name} (exit code {result.returncode}):\n"
                f"{result.stdout}\n{result.stderr}"
            )
        if not os.path.isfile(mapped_path) or os.path.getsize(mapped_path) == 0:
            raise RuntimeError(
                f"PSS-3D did not generate {mapped_name}.\n"
                f"{result.stdout}\n{result.stderr}"
            )

        # Preserve the original input filename for downstream modules.
        final_pdb_path = os.path.join(final_dir, pdb_name)
        shutil.copy2(mapped_path, final_pdb_path)
        pymol_pdb_path = os.path.join(pymol_dir, pdb_name)
        shutil.copy2(final_pdb_path, pymol_pdb_path)
        pymol_pdb_paths.append(pymol_pdb_path)

    # Render only the PDBs processed above, not every file in the PyMOL folder.
    for pdb_path in pymol_pdb_paths:
        pdb_name = os.path.basename(pdb_path)
        png_name = f"{os.path.splitext(pdb_name)[0]}.png"
        png_path = os.path.join(pymol_dir, png_name)
        pymolrc_path = os.path.join(pymol_dir, "pymolrc")

        if os.path.isfile(png_path):
            os.remove(png_path)

        with open(pymolrc_path, "w") as f:
            f.write(f"load /data/{pdb_name}\n")
            f.write("spectrum b, green_blue_red, minimum=0, maximum=99\n")
            f.write(
                f"png /data/{png_name}, "
                "width=4000, dpi=300, ray=1\n"
            )
            f.write("quit\n")

        result = subprocess.run(
            [
                "docker", "run", "--rm",
                "-e", f"USERID={os.getuid()}",
                "-e", f"USER={os.environ.get('USER', '')}",
                "-v", "/tmp/.X11-unix:/tmp/.X11-unix",
                "-v",
                f"{os.environ.get('HOME', '')}/.Xauthority:"
                "/home/developer/.Xauthority",
                "--device", "/dev/dri/",
                "-v",
                f"/{host_dir}/{prefix}highlight_regions/pymol:/data",
                f"pegi3s/pymol:{pymol_docker_version}",
                "bash",
                "-c",
                "cp /data/pymolrc ~/.pymolrc && pymol -qc",
            ],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            raise RuntimeError(
                f"PyMOL failed for {pdb_name} (exit code {result.returncode}):\n"
                f"{result.stdout}\n{result.stderr}"
            )
        if not os.path.isfile(png_path) or os.path.getsize(png_path) == 0:
            raise RuntimeError(
                f"PyMOL did not produce a valid PNG for {pdb_name}.\n"
                f"{result.stdout}\n{result.stderr}"
            )

        shutil.copy2(png_path, final_dir)

    record_version(
        f"highlight_regions {highlightregions_autop2_version},"
        f"pegi3s/pss-3d:{highlightregions_docker_version}"
    )
    record_version(f",pegi3s/pymol:{pymol_docker_version}")


if __name__ == "__main__":
    print("Running highlight_regions", flush=True)
    main()
