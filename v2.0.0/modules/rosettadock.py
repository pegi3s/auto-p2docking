#!/usr/bin/env python3
import configparser
import glob
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pymodule_common import load_config, record_refs, record_version


rosettadock_autop2_version = "2.0.0"
rosettadock_screening_docker_version = "1.0.0"
rosettadock_ref = ""
rosettadock_doi = ""


def _get_required_parameter(name, default):
    value = os.environ.get(name, "")
    if value == "":
        return default
    return value


def _build_screening_config(
    source_config,
    destination_config,
    receptor_name,
):
    """
    Build the config file expected by pegi3s/rosettadock-screening.

    The user-supplied rosettadock_config contains the experiment-specific
    [Regions] and [Variables_TF] sections.

    General execution parameters are obtained from the auto-p2docking
    /data/config.
    """

    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str

    files_read = parser.read(source_config)

    if not files_read:
        sys.exit(
            f"Error: could not read RosettaDock configuration file:\n"
            f"{source_config}"
        )

    if "Regions" not in parser:
        sys.exit(
            "Error: rosettadock_config must contain a [Regions] section"
        )

    if "Variables_TF" not in parser:
        sys.exit(
            "Error: rosettadock_config must contain a [Variables_TF] section"
        )

    if "Input_Files" not in parser:
        parser["Input_Files"] = {}

    parser["Input_Files"]["pdb_receptor"] = receptor_name

    if "General_Constants" not in parser:
        parser["General_Constants"] = {}

    parser["General_Constants"]["i_global_max"] = (
        _get_required_parameter(
            "rosettadock_i_global_max",
            "100",
        )
    )

    parser["General_Constants"]["i_local_max"] = (
        _get_required_parameter(
            "rosettadock_i_local_max",
            "20",
        )
    )

    parser["General_Constants"]["success_cycles"] = (
        _get_required_parameter(
            "rosettadock_success_cycles",
            "10",
        )
    )

    if "Reward" not in parser:
        parser["Reward"] = {}

    parser["Reward"]["ratio"] = (
        _get_required_parameter(
            "rosettadock_ratio",
            "1",
        )
    )

    parser["Reward"]["ratio_increment"] = (
        _get_required_parameter(
            "rosettadock_ratio_increment",
            "0.1",
        )
    )

    if "CST_Weight" not in parser:
        parser["CST_Weight"] = {}

    parser["CST_Weight"]["cst_weight"] = (
        _get_required_parameter(
            "rosettadock_cst_weight",
            "0.05",
        )
    )

    with open(
        destination_config,
        "w",
        encoding="utf-8",
        newline="\n",
    ) as f:
        parser.write(f)


def _copy_optional_control_files(input_path, run_dir):
    """
    rosettadock-screening optionally accepts control_results.xlsx.
    Its current implementation also supports control_results.csv.
    """

    for name in (
        "control_results.xlsx",
        "control_results.csv",
    ):
        source = os.path.join(input_path, name)

        if os.path.isfile(source):
            shutil.copy2(
                source,
                os.path.join(run_dir, name),
            )


def _copy_results(run_dir, output_dir):
    """
    Preserve the output structure produced by rosettadock-screening,
    without copying the temporary receptor/ligand/config inputs.
    """

    final_results = os.path.join(
        run_dir,
        "final_results",
    )

    results_csv = os.path.join(
        run_dir,
        "results.csv",
    )

    if not os.path.isfile(results_csv):
        sys.exit(
            "Error: RosettaDock screening did not create results.csv"
        )

    os.makedirs(
        output_dir,
        exist_ok=True,
    )

    if os.path.isdir(final_results):
        shutil.copytree(
            final_results,
            os.path.join(
                output_dir,
                "final_results",
            ),
            dirs_exist_ok=True,
        )

    shutil.copy2(
        results_csv,
        os.path.join(
            output_dir,
            "results.csv",
        ),
    )

    # The screening pipeline can generate this file when a control
    # dataset is supplied.
    control_csv = os.path.join(
        run_dir,
        "control_results.csv",
    )

    if os.path.isfile(control_csv):
        shutil.copy2(
            control_csv,
            os.path.join(
                output_dir,
                "control_results.csv",
            ),
        )


def main():
    global rosettadock_autop2_version
    global rosettadock_screening_docker_version
    global rosettadock_ref
    global rosettadock_doi

    if len(sys.argv) < 4:
        sys.exit(
            "Usage: rosettadock.py "
            "<input_dir> <out_dir> <prefix>"
        )

    input_dir, out_dir, prefix = (
        sys.argv[1],
        sys.argv[2],
        sys.argv[3],
    )

    load_config()

    if os.environ.get(
        "rosettadock_screening_docker_c_version"
    ):
        rosettadock_autop2_version = "?"
        rosettadock_screening_docker_version = (
            os.environ[
                "rosettadock_screening_docker_c_version"
            ]
        )
        rosettadock_ref = "?"
        rosettadock_doi = "?"

    project = os.environ.get("project", "")
    host_dir = os.environ.get("dir", "")

    input_path = f"/data/{input_dir}"

    if not os.path.isdir(input_path):
        sys.exit(
            f"Error: input directory not found:\n"
            f"{input_path}"
        )

    rosettadock_config = os.path.join(
        input_path,
        "rosettadock_config",
    )

    constraints_file = os.path.join(
        input_path,
        "constraints.cst",
    )

    if not os.path.isfile(rosettadock_config):
        sys.exit(
            "Error: rosettadock_config was not found in "
            f"{input_path}"
        )

    if not os.path.isfile(constraints_file):
        sys.exit(
            "Error: constraints.cst was not found in "
            f"{input_path}"
        )

    # --------------------------------------------------------
    # Receptor
    # --------------------------------------------------------

    receptor_files = sorted(
        path
        for path in glob.glob(
            f"/data/{project}/PDBs/Receptor/*"
        )
        if (
            os.path.isfile(path)
            and path.lower().endswith(".pdb")
        )
    )

    if not receptor_files:
        sys.exit(
            "Error: no receptor PDB file found in "
            f"/data/{project}/PDBs/Receptor"
        )

    receptor_path = receptor_files[0]
    receptor_name = os.path.basename(receptor_path)

    if len(receptor_files) > 1:
        print(
            "Warning: more than one receptor PDB was found. "
            f"Using {receptor_name}",
            flush=True,
        )

    receptor_stem = os.path.splitext(
        receptor_name
    )[0]

    # --------------------------------------------------------
    # Current ligand
    # --------------------------------------------------------

    input_ligand_path = (
        f"/data/{project}/PDBs/input_ligand.txt"
    )

    if not os.path.isfile(input_ligand_path):
        sys.exit(
            "Error: PDBs/input_ligand.txt was not found"
        )

    with open(
        input_ligand_path,
        encoding="utf-8",
    ) as f:
        ligand_name = f.readline().strip()

    if not ligand_name:
        sys.exit(
            "Error: input_ligand.txt is empty"
        )

    ligand_name = os.path.basename(
        ligand_name
    )

    ligand_path = (
        f"/data/{project}/PDBs/Ligands/"
        f"{ligand_name}"
    )

    if not os.path.isfile(ligand_path):
        sys.exit(
            f"Error: ligand PDB not found:\n"
            f"{ligand_path}"
        )

    ligand_stem = os.path.splitext(
        ligand_name
    )[0]

    # Same protection used by other docking/surface modules.
    warning_path = (
        f"/data/{project}/intermediate_files/"
        f"warning_files/do_not_run.{ligand_stem}"
    )

    if (
        receptor_stem == ligand_stem
        or os.path.isfile(warning_path)
    ):
        return

    # --------------------------------------------------------
    # Temporary RosettaDock-screening working directory
    # --------------------------------------------------------

    run_base = (
        f"/data/{prefix}rosettadock"
    )

    run_dir = os.path.join(
        run_base,
        ligand_stem,
    )

    ligand_run_dir = os.path.join(
        run_dir,
        "ligands",
    )

    output_group_dir = (
        f"/data/{out_dir}/{ligand_stem}"
    )

    mounted_run_dir = (
        f"{host_dir}/{prefix}"
        f"rosettadock/{ligand_stem}"
    )

    os.makedirs(
        ligand_run_dir,
        exist_ok=True,
    )

    os.makedirs(
        output_group_dir,
        exist_ok=True,
    )

    try:
        # ----------------------------------------------------
        # Stage files expected by rosettadock-screening
        # ----------------------------------------------------

        shutil.copy2(
            receptor_path,
            os.path.join(
                run_dir,
                receptor_name,
            ),
        )

        shutil.copy2(
            ligand_path,
            os.path.join(
                ligand_run_dir,
                ligand_name,
            ),
        )

        shutil.copy2(
            constraints_file,
            os.path.join(
                run_dir,
                "constraints.cst",
            ),
        )

        _copy_optional_control_files(
            input_path,
            run_dir,
        )

        _build_screening_config(
            source_config=rosettadock_config,
            destination_config=os.path.join(
                run_dir,
                "config",
            ),
            receptor_name=receptor_name,
        )

        # ----------------------------------------------------
        # Run PEgi3S RosettaDock-screening
        # ----------------------------------------------------

        print(
            f"Running RosettaDock screening for "
            f"{ligand_name}",
            flush=True,
        )

        subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "-v",
                (
                    f"{mounted_run_dir}:"
                    f"/data"
                ),
                "-v",
                (
                    "/var/run/docker.sock:"
                    "/var/run/docker.sock"
                ),
                "-e",
                (
                    "HOST_DATA_DIR="
                    f"{mounted_run_dir}"
                ),
                (
                    "pegi3s/"
                    "rosettadock-screening:"
                    f"{rosettadock_screening_docker_version}"
                ),
            ],
            check=True,
        )

        # ----------------------------------------------------
        # Copy useful output back to auto-p2docking
        # ----------------------------------------------------

        _copy_results(
            run_dir,
            output_group_dir,
        )

    finally:
        # The PDBs/config/constraints copied above only exist to
        # satisfy the directory layout expected by the screening
        # image. They must not remain as persistent intermediate
        # copies after this module finishes.
        if os.path.isdir(run_dir):
            shutil.rmtree(
                run_dir,
                ignore_errors=True,
            )

        # Remove the parent if this was its last ligand.
        try:
            os.rmdir(run_base)
        except OSError:
            pass

    record_version(
        f"rosettadock {rosettadock_autop2_version},"
        f"pegi3s/rosettadock-screening:"
        f"{rosettadock_screening_docker_version},"
        f'RosettaDock screening,"{rosettadock_ref}",'
        f'"{rosettadock_doi}"'
    )

    record_refs(
        f'rosettadock_ref="{rosettadock_ref}"\n'
        f'rosettadock_doi="{rosettadock_doi}"\n'
    )


if __name__ == "__main__":
    print(
        "Running RosettaDock screening",
        flush=True,
    )
    main()
