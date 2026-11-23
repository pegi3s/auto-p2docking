#!/usr/bin/env python3
import glob
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pymodule_common import convert_interface_csv_to_consensus_format, load_config, record_version, update_run_summary

scriber_autop2_version = "2.0.0"
scriber_docker_version = "latest"
scriber_program_version = "2019 webserver version"
scriber_ref = ""
scriber_doi = ""


def _select_current_protein_pdb(input_path, project):
    """Resolve the ligand or receptor selected by main.py for this iteration.

    Do not fall back to processing every input PDB when selection is missing.
    """
    role = os.environ.get("AUTO_P2DOCKING_PROTEIN_ROLE", "ligand")
    if role not in ("ligand", "receptor"):
        raise SystemExit(f"Error: invalid selected protein role: {role!r}")
    selection_filename = "input_receptor.txt" if role == "receptor" else "input_ligand.txt"
    protein_folder = "Receptor" if role == "receptor" else "Ligands"
    ligand_file = Path("/data") / project / "PDBs" / selection_filename
    if not ligand_file.is_file():
        raise SystemExit(
            f"Error: missing current BLOCK ligand file: {ligand_file}"
        )

    current_ligand = Path(ligand_file.read_text(
        encoding="utf-8", errors="replace"
    ).strip()).name
    if not current_ligand or not current_ligand.lower().endswith(".pdb"):
        raise SystemExit(
            f"Error: invalid PDB name in {ligand_file}: {current_ligand!r}"
        )

    input_root = Path(input_path)
    direct = input_root / current_ligand
    if direct.is_file():
        selected = direct
    else:
        matches = sorted(p for p in input_root.rglob(current_ligand) if p.is_file())
        if len(matches) > 1:
            raise SystemExit(
                f"Error: multiple PDBs named {current_ligand!r} in {input_root}:\n"
                + "\n".join(str(p) for p in matches)
            )
        if matches:
            selected = matches[0]
        else:
            fallback = Path("/data") / project / "PDBs" / protein_folder / current_ligand
            if not fallback.is_file():
                raise SystemExit(
                    f"Error: current BLOCK PDB {current_ligand!r} was not found "
                    f"in {input_root} or {fallback}"
                )
            selected = fallback

    return str(selected)


def main():
    global scriber_autop2_version, scriber_docker_version, scriber_ref, scriber_doi

    if len(sys.argv) < 4:
        sys.exit(
            "Usage: scriber.py <input_dir> <output_dir> <prefix>"
        )

    input_dir, output_dir, prefix = (
        sys.argv[1],
        sys.argv[2],
        sys.argv[3],
    )

    load_config()

    if os.environ.get("scriber_docker_c_version"):
        scriber_autop2_version = "?"
        scriber_docker_version = os.environ[
            "scriber_docker_c_version"
        ]
        scriber_ref = "?"
        scriber_doi = "?"

    scriber_chain = os.environ.get(
        "scriber_chain",
        "A"
    )

    host_dir = os.environ.get("dir", "")
    project = os.environ.get("project", "")

    input_path = f"/data/{input_dir}"
    output_path = f"/data/{output_dir}"
    intermediate_path = f"/data/{prefix}scriber"


    if not os.path.isdir(input_path):
        sys.exit(
            f"Error: input directory does not exist:\n"
            f"{input_path}"
        )

    os.makedirs(
        output_path,
        exist_ok=True
    )

    os.makedirs(
        intermediate_path,
        exist_ok=True
    )
    archive_root = os.path.join(intermediate_path, "scriber")
    os.makedirs(archive_root, exist_ok=True)


    summary_file = os.path.join(output_path, "scriber_summary.csv")

    pdb_files = [_select_current_protein_pdb(input_path, project)]

    if not pdb_files:
        sys.exit(
            f"Error: no .pdb files found in:\n"
            f"{input_path}"
        )

    for source_pdb in pdb_files:
        input_name = os.path.basename(
            source_pdb
        )[:-4]

        relative_dir = os.path.relpath(
            os.path.dirname(source_pdb),
            input_path
        )

        if relative_dir == ".":
            run_name = input_name
        else:
            clean_relative_dir = relative_dir.replace(
                "/",
                "__"
            )

            run_name = (
                f"{clean_relative_dir}__"
                f"{input_name}"
            )

        module_dir = os.path.join(
            intermediate_path,
            "scriber",
            run_name
        )

        work_input_dir = os.path.join(
            module_dir,
            "input"
        )

        work_output_dir = os.path.join(
            module_dir,
            "output"
        )

        consensus_output_dir = os.path.join(
            output_path,
            run_name
        )

        raw_output_dir = work_output_dir

        host_module_dir = (
            f"{host_dir}/{prefix}scriber/scriber/"
            f"{run_name}"
        )

        os.makedirs(
            work_input_dir,
            exist_ok=True
        )

        if os.path.isdir(work_output_dir):
            shutil.rmtree(work_output_dir)
        os.makedirs(
            work_output_dir,
            exist_ok=True
        )

        os.makedirs(
            consensus_output_dir,
            exist_ok=True
        )


        shutil.copy2(
            source_pdb,
            os.path.join(
                work_input_dir,
                f"{input_name}.pdb"
            )
        )

        prediction_csv = (
            f"/data/output/"
            f"{run_name}.scriber.csv"
        )

        result = subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "-v",
                f"{host_module_dir}:/data",
                f"pegi3s/scriber:{scriber_docker_version}",
                f"/data/input/{input_name}.pdb",
                scriber_chain,
                "--output",
                prediction_csv,
            ],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            for stream in (result.stdout, result.stderr):
                if stream.strip():
                    print(stream, file=sys.stderr)
            print(
                f"Warning: SCRIBER failed with exit code {result.returncode} "
                f"for {run_name}; continuing without SCRIBER predictions",
                flush=True,
            )
            continue

        if not os.listdir(work_output_dir):
            print(
                f"Warning: SCRIBER produced no output for {source_pdb}; "
                f"continuing without SCRIBER predictions",
                flush=True,
            )
            continue

        interface_csv = os.path.join(
            raw_output_dir,
            f"{run_name}.scriber."
            f"interface_residues.csv"
        )

        if not os.path.isfile(interface_csv):
            plain_interface_csv = os.path.join(
                raw_output_dir,
                "interface_residues.csv"
            )

            if os.path.isfile(
                plain_interface_csv
            ):
                shutil.copy2(
                    plain_interface_csv,
                    interface_csv
                )

            else:
                found = sorted(
                    glob.glob(
                        os.path.join(
                            raw_output_dir,
                            "*interface_residues*.csv"
                        )
                    )
                )

                if found:
                    shutil.copy2(
                        found[0],
                        interface_csv
                    )

                else:
                    print(
                        f"Warning: no interface residues CSV found for "
                        f"{run_name}; continuing without SCRIBER predictions",
                        flush=True,
                    )
                    continue

        consensus_file = os.path.join(
            consensus_output_dir,
            f"{run_name}.scriber.csv"
        )

        convert_interface_csv_to_consensus_format(
            interface_csv,
            consensus_file
        )

        if (
            not os.path.isfile(consensus_file)
            or os.path.getsize(consensus_file) == 0
        ):
            print(
                f"Warning: SCRIBER consensus file was not created or is "
                f"empty for {run_name}; continuing without SCRIBER predictions",
                flush=True,
            )
            continue

        shutil.copy2(consensus_file, os.path.join(module_dir, os.path.basename(consensus_file)))

        update_run_summary(
            summary_file,
            ["input_file", "run_name", "consensus_file", "raw_output_directory"],
            ["run_name"],
            {"input_file": os.path.basename(source_pdb),
             "run_name": run_name, "consensus_file": consensus_file,
             "raw_output_directory": raw_output_dir},
        )

    if os.path.isfile(summary_file):
        shutil.copy2(summary_file, os.path.join(archive_root, os.path.basename(summary_file)))

    record_version(
        f'scriber {scriber_autop2_version},'
        f'pegi3s/scriber:{scriber_docker_version},'
        f'SCRIBER {scriber_program_version},'
        f'"{scriber_ref}","{scriber_doi}"'
    )


if __name__ == "__main__":
    print(
        "Running: SCRIBER",
        flush=True
    )

    print(
        "You can only use this module if you have permissions "
        "to use the scriber server "
        "(https://biomine2.cs.vcu.edu/servers/SCRIBER/) "
        "Leaving the webpage open may be a good idea",
        flush=True,
    )

    main()
