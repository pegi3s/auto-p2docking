#!/usr/bin/env python3
import glob
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pymodule_common import convert_interface_csv_to_consensus_format, load_config, record_version, update_run_summary

ispred4_autop2_version = "2.0.0"
ispred4_docker_version = "4.0.0"
ispred4_program_version = "4.0.0"
ispred4_ref = ""
ispred4_doi = ""


def _copy_best_effort(src, dst_dir):
    if os.path.isfile(src):
        shutil.copy2(src, dst_dir)


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
    global ispred4_autop2_version, ispred4_docker_version, ispred4_ref, ispred4_doi

    if len(sys.argv) < 4:
        sys.exit("Usage: ispred4.py <input_dir> <out_dir> <prefix>")

    input_dir, output_dir, prefix = sys.argv[1], sys.argv[2], sys.argv[3]
    load_config()

    if os.environ.get("ispred4_docker_c_version"):
        ispred4_autop2_version = "?"
        ispred4_docker_version = os.environ["ispred4_docker_c_version"]
        ispred4_ref = "?"
        ispred4_doi = "?"

    chain = os.environ.get("ispred4_chain") or "A"
    host_dir = os.environ.get("dir", "")
    project = os.environ.get("project", "")

    input_path = f"/data/{input_dir}"
    output_path = f"/data/{output_dir}"
    intermediate_path = f"/data/{prefix}ispred4"
    work_dir = os.path.join(intermediate_path, "work")
    host_work_dir = f"{host_dir}/{prefix}ispred4/work"


    if not os.path.isdir(input_path):
        print("Error: input directory does not exist:")
        sys.exit(input_path)

    os.makedirs(output_path, exist_ok=True)
    os.makedirs(intermediate_path, exist_ok=True)
    archive_root = os.path.join(intermediate_path, "ispred4")
    os.makedirs(archive_root, exist_ok=True)
    if os.path.isdir(work_dir):
        shutil.rmtree(work_dir)
    os.makedirs(work_dir, exist_ok=True)

    pdb_files = [_select_current_protein_pdb(input_path, project)]

    if not pdb_files:
        print("Error: no .pdb files found in:")
        sys.exit(input_path)

    mapping_file = os.path.join(output_path, "ispred4_input_mapping.csv")

    for source_pdb in pdb_files:
        relative_path = os.path.relpath(source_pdb, input_path)
        clean_name = relative_path.replace("/", "__")

        if clean_name.endswith(".pdb"):
            clean_name = clean_name[:-len(".pdb")]

        clean_name = f"{clean_name}.pdb"
        run_name = clean_name[:-len(".pdb")]

        shutil.copy2(
            source_pdb,
            os.path.join(work_dir, clean_name)
        )

        update_run_summary(
            mapping_file, ["original_path", "copied_filename", "run_name"],
            ["run_name"],
            {"original_path": source_pdb, "copied_filename": clean_name,
             "run_name": run_name},
        )

    result = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{host_work_dir}:/data",
            f"pegi3s/ispred4:{ispred4_docker_version}",
            "--chain",
            chain,
            "--data-dir",
            "/data",
        ],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        if result.stdout.strip():
            print(result.stdout, file=sys.stderr)

        if result.stderr.strip():
            print(result.stderr, file=sys.stderr)

        sys.exit(
            f"Error: ISPRED4 failed with exit code {result.returncode}"
        )

    interface_files = sorted(
        glob.glob(
            os.path.join(
                work_dir,
                "*.ispred4.interface_residues.csv"
            )
        )
    )

    if not interface_files:
        print(
            "Error: ISPRED4 did not generate any "
            "interface residues CSV files."
        )
        print("Work directory:")
        print(work_dir)
        print("Files found:")

        for name in sorted(os.listdir(work_dir)):
            print(name)

        sys.exit(1)

    summary_file = os.path.join(output_path, "ispred4_runs.csv")

    suffix = ".ispred4.interface_residues.csv"

    for interface_csv in interface_files:
        file_name = os.path.basename(interface_csv)

        run_name = (
            file_name[:-len(suffix)]
            if file_name.endswith(suffix)
            else file_name
        )

        consensus_output_dir = os.path.join(
            output_path,
            run_name
        )


        module_dir = os.path.join(
            intermediate_path,
            "ispred4",
            run_name
        )

        module_input_dir = os.path.join(
            module_dir,
            "input"
        )

        module_output_dir = os.path.join(
            module_dir,
            "output"
        )
        raw_output_dir = module_output_dir

        os.makedirs(consensus_output_dir, exist_ok=True)
        os.makedirs(module_input_dir, exist_ok=True)
        if os.path.isdir(module_output_dir):
            shutil.rmtree(module_output_dir)
        os.makedirs(module_output_dir, exist_ok=True)

        _copy_best_effort(
            os.path.join(
                work_dir,
                f"{run_name}.pdb"
            ),
            module_input_dir
        )

        for path in glob.glob(
            os.path.join(
                work_dir,
                f"{run_name}.ispred4.*"
            )
        ):
            _copy_best_effort(
                path,
                module_output_dir
            )

        consensus_file = os.path.join(
            consensus_output_dir,
            f"{run_name}.ispred4.csv"
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
                "Error: consensus file was not created or is empty:"
            )
            sys.exit(consensus_file)

        shutil.copy2(consensus_file, os.path.join(module_dir, os.path.basename(consensus_file)))

        update_run_summary(
            summary_file,
            ["run_name", "consensus_file", "raw_output_directory",
             "intermediate_output_directory"],
            ["run_name"],
            {"run_name": run_name, "consensus_file": consensus_file,
             "raw_output_directory": raw_output_dir,
             "intermediate_output_directory": module_output_dir},
        )

    shutil.copy2(mapping_file, os.path.join(archive_root, os.path.basename(mapping_file)))
    shutil.copy2(summary_file, os.path.join(archive_root, os.path.basename(summary_file)))

    shutil.rmtree(
        work_dir,
        ignore_errors=True
    )

    record_version(
        f'ispred4 {ispred4_autop2_version},'
        f'pegi3s/ispred4:{ispred4_docker_version},'
        f'ISPRED4 {ispred4_program_version},'
        f'"{ispred4_ref}","{ispred4_doi}"'
    )


if __name__ == "__main__":
    print("Running: ISPRED4", flush=True)
    main()
