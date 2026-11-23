#!/usr/bin/env python3
import glob
import hashlib
import os
import random
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pymodule_common import load_config, parse_module_defs, record_version

consensus_autop2_version = "2.0.0"


def _read_lines(path):
    with open(path) as f:
        return f.read().splitlines()


def _split_pairs(lines):
    pairs = []
    for line in lines:
        parts = line.split()
        if len(parts) >= 2:
            pairs.append((parts[0], parts[1]))
    return pairs


def count_active_sites(lines_or_path):
    lines = _read_lines(lines_or_path) if isinstance(lines_or_path, str) else lines_or_path
    return sum(1 for parts in (l.split() for l in lines) if len(parts) >= 2 and parts[1] == "1")


def is_valid_result(num, min_number, max_number):
    return min_number <= num <= max_number


def calculate_majority_consensus(files):
    files_residues = []
    all_residues = set()

    for file in files:
        pairs = _split_pairs(_read_lines(file))
        residue_values = {}

        for residue, value in pairs:
            residue = int(float(residue))

            if value not in {"0", "1", "2"}:
                raise ValueError(
                    f"Invalid consensus value '{value}' for residue {residue} in {file}"
                )

            if residue in residue_values:
                raise ValueError(
                    f"Duplicate residue {residue} found in {file}"
                )

            residue_values[residue] = value
            all_residues.add(residue)

        files_residues.append(residue_values)

    result = []

    for residue in sorted(all_residues):
        count0 = count1 = count2 = 0

        for residue_values in files_residues:
            value = residue_values.get(residue, "0")

            if value == "0":
                count0 += 1
            elif value == "1":
                count1 += 1
            elif value == "2":
                count2 += 1

        if count0 > count1 and count0 > count2:
            consensus = "0"
        elif count1 >= count0 and count1 > count2:
            consensus = "1"
        elif count2 >= count0 and count2 > count1:
            consensus = "2"
        else:
            consensus = "0"

        result.append(f"{residue} {consensus}")

    return result


def mark_do_not_run(protein, project):
    warning_path = f"/data/{project}/intermediate_files/warning_files/do_not_run.{protein}"
    with open(warning_path, "w") as f:
        f.write("Do not run\n")


def write_final_output(chosen_path, protein, protein_output_dir, out_dir, project):
    os.makedirs(protein_output_dir, exist_ok=True)
    shutil.copy2(chosen_path, protein_output_dir)

    pairs = _split_pairs(_read_lines(chosen_path))
    active = [residue for residue, value in pairs if value == "1"]
    passive = [residue for residue, value in pairs if value == "2"]

    with open(os.path.join(protein_output_dir, f"{protein}_active.sites"), "w") as f:
        if active:
            f.write(",".join(active) + "\n")

    with open(os.path.join(protein_output_dir, f"{protein}_passive.sites"), "w") as f:
        if passive:
            f.write(",".join(passive) + "\n")

    done_dir = f"/data/{project}/intermediate_files/done_files"
    os.makedirs(done_dir, exist_ok=True)
    with open(os.path.join(done_dir, f"done.{protein}"), "w") as f:
        f.write(f"{out_dir}/{protein}\n")

    warning_path = f"/data/{project}/intermediate_files/warning_files/do_not_run.{protein}"
    if os.path.isfile(warning_path):
        os.remove(warning_path)
    print(f"Consensus completed for {protein}", flush=True)


def choose_method_with_most_active_sites(files):
    best_file = None
    best_count = -1

    for f in files:
        count = count_active_sites(f)
        if count > best_count:
            best_count = count
            best_file = f

    return best_file


def remove_consecutive_active_sites(input_path, output_path):
    previous_kept_active = False

    with open(output_path, "w") as out:
        for residue, value in _split_pairs(_read_lines(input_path)):
            if value == "1" and previous_kept_active:
                out.write(f"{residue} 0\n")
                previous_kept_active = False
            else:
                out.write(f"{residue} {value}\n")
                previous_kept_active = value == "1"


def create_safe_option(input_path, output_path, max_number):
    pairs = _split_pairs(_read_lines(input_path))
    actives = [residue for residue, value in pairs if value == "1"]
    random.shuffle(actives)
    selected = set(actives[:max_number])

    with open(output_path, "w") as out:
        for residue, value in pairs:
            if value == "1":
                out.write(f"{residue} {'1' if residue in selected else '0'}\n")
            elif value == "2":
                out.write(f"{residue} 2\n")
            else:
                out.write(f"{residue} 0\n")


def handle_too_many_active_sites(
    protein, protein_work_dir, protein_output_dir, out_dir, project,
    preferred_1, preferred_2, min_number, max_number, critical_number,
):
    method1_matches = sorted(glob.glob(os.path.join(protein_work_dir, f"{protein}.{preferred_1}")))
    method2_matches = sorted(glob.glob(os.path.join(protein_work_dir, f"{protein}.{preferred_2}")))
    method1 = method1_matches[0] if method1_matches else None
    method2 = method2_matches[0] if method2_matches else None

    # Fall back to the methods that are actually available (e.g. when one
    # predictor failed) instead of discarding the protein.
    if not method1 or not method2:
        available = sorted(glob.glob(os.path.join(protein_work_dir, f"{protein}.*.csv")))
        chosen = [m for m in (method1, method2) if m]
        chosen += [f for f in available if f not in chosen]
        method1 = chosen[0] if chosen else None
        method2 = chosen[1] if len(chosen) > 1 else method1

    if not method1 or not method2:
        print(f"Preferred methods not found for {protein}")
        mark_do_not_run(protein, project)
        return

    two_methods_only = os.path.join(protein_work_dir, "two_methods_only")
    with open(two_methods_only, "w") as f:
        for line in calculate_majority_consensus([method1, method2]):
            f.write(line + "\n")
    num_two = count_active_sites(two_methods_only)

    if is_valid_result(num_two, min_number, max_number):
        write_final_output(two_methods_only, protein, protein_output_dir, out_dir, project)
        return

    if num_two < critical_number:
        mark_do_not_run(protein, project)
        return

    if num_two > max_number:

        middle_number_removed = os.path.join(protein_work_dir, "middle_number_removed")
        remove_consecutive_active_sites(two_methods_only, middle_number_removed)
        num_middle = count_active_sites(middle_number_removed)

        if is_valid_result(num_middle, min_number, max_number):
            write_final_output(middle_number_removed, protein, protein_output_dir, out_dir, project)
            return

        if num_middle < critical_number:
            mark_do_not_run(protein, project)
            return

        if num_middle > max_number:

            safe_option = os.path.join(protein_work_dir, "safe_option")
            create_safe_option(middle_number_removed, safe_option, max_number)
            num_safe = count_active_sites(safe_option)

            if is_valid_result(num_safe, min_number, max_number):
                write_final_output(safe_option, protein, protein_output_dir, out_dir, project)
                return

            mark_do_not_run(protein, project)
            return

    print(f"Too-many-active-sites routine failed for {protein}")
    mark_do_not_run(protein, project)


def run_consensus_for_protein(
    protein, source_dir, work_base, output_path, out_dir, project,
    preferred_1, preferred_2, min_number, max_number, critical_number,
):
    protein_work_dir = os.path.join(work_base, protein)
    protein_output_dir = os.path.join(output_path, protein)

    done_marker = f"/data/{project}/intermediate_files/done_files/done.{protein}"
    if os.path.isfile(done_marker):
        with open(done_marker) as f:
            prev_output_dir = f.readline().strip()

        if (
            prev_output_dir
            and os.path.isdir(f"/data/{prev_output_dir}")
            and f"/data/{prev_output_dir}" != protein_output_dir
        ):
            print(f"{protein} already marked as done; copying previously computed results from {prev_output_dir}")
            os.makedirs(protein_output_dir, exist_ok=True)
            shutil.copytree(f"/data/{prev_output_dir}", protein_output_dir, dirs_exist_ok=True)

        print(f"Consensus previously marked done for {protein}", flush=True)
        return

    shutil.rmtree(protein_work_dir, ignore_errors=True)
    os.makedirs(protein_work_dir, exist_ok=True)
    os.makedirs(protein_output_dir, exist_ok=True)

    source_files = sorted(glob.glob(os.path.join(source_dir, f"{protein}.*.csv")))
    if not source_files:
        print(f"No CSV files matching {protein}.*.csv in {source_dir}")
        mark_do_not_run(protein, project)
        return

    for src in source_files:
        shutil.copy2(src, protein_work_dir)

    input_files = sorted(glob.glob(os.path.join(protein_work_dir, f"{protein}.*.csv")))
    if not input_files:
        print(f"No input CSV files found for {protein} after copy")
        mark_do_not_run(protein, project)
        return

    consensus_results = os.path.join(protein_work_dir, "consensus_results")
    with open(consensus_results, "w") as f:
        for line in calculate_majority_consensus(input_files):
            f.write(line + "\n")
    num_consensus = count_active_sites(consensus_results)

    if is_valid_result(num_consensus, min_number, max_number):
        write_final_output(consensus_results, protein, protein_output_dir, out_dir, project)
        return

    if num_consensus < min_number:

        best_method = choose_method_with_most_active_sites(input_files)

        if not best_method or not os.path.isfile(best_method):
            print(f"No valid method found for {protein}")
            mark_do_not_run(protein, project)
            return

        single_method = os.path.join(protein_work_dir, "single_method")
        shutil.copy2(best_method, single_method)
        num_single = count_active_sites(single_method)

        if is_valid_result(num_single, min_number, max_number):
            write_final_output(single_method, protein, protein_output_dir, out_dir, project)
            return

        if num_single < critical_number:
            mark_do_not_run(protein, project)
            return

        if num_single > max_number:
            handle_too_many_active_sites(
                protein, protein_work_dir, protein_output_dir, out_dir, project,
                preferred_1, preferred_2, min_number, max_number, critical_number,
            )
            return

        mark_do_not_run(protein, project)
        return

    if num_consensus > max_number:
        handle_too_many_active_sites(
            protein, protein_work_dir, protein_output_dir, out_dir, project,
            preferred_1, preferred_2, min_number, max_number, critical_number,
        )
        return

    print(f"No valid consensus result found for {protein}")
    mark_do_not_run(protein, project)


def _selected_protein_for_block(project):
    """Protein corresponding to the PDB selected by main.py for this iteration."""
    role = os.environ.get('AUTO_P2DOCKING_PROTEIN_ROLE', 'ligand')
    if role not in ('ligand', 'receptor'):
        sys.exit(f'[ERROR] Invalid protein selection role: {role!r}')
    selection_file = 'input_receptor.txt' if role == 'receptor' else 'input_ligand.txt'
    ligand_file = os.path.join('/data', project, 'PDBs', selection_file)
    if not os.path.isfile(ligand_file):
        sys.exit(f'[ERROR] Missing BLOCK ligand selection file: {ligand_file}')

    with open(ligand_file, encoding='utf-8') as f:
        ligand = os.path.basename(f.readline().strip())

    if not ligand or not ligand.lower().endswith('.pdb'):
        sys.exit(f'[ERROR] Invalid BLOCK ligand in {ligand_file}: {ligand!r}')

    return ligand[:-4]



def _announce_consensus_once_per_pipeline(project, prefix):
    """Print one consensus header per main.py invocation, even for BLOCK runs.

    main.py launches this module as a separate subprocess for every ligand.
    Its parent PID and Linux process start time identify that one invocation
    without relying on the ordering/content of ligands_list.txt.
    """
    parent_pid = os.getppid()
    try:
        with open(f"/proc/{parent_pid}/stat", encoding="utf-8") as f:
            # Field 22 is starttime. Split after the command name because it
            # can contain spaces and parentheses.
            parent_starttime = f.read().rsplit(") ", 1)[1].split()[19]
    except (OSError, IndexError, ValueError):
        parent_starttime = "unknown"

    run_key = f"{project}|{prefix}|{parent_pid}|{parent_starttime}"
    run_id = hashlib.sha256(run_key.encode("utf-8")).hexdigest()[:24]
    marker = os.path.join(tempfile.gettempdir(),
                          f"auto_p2docking_consensus_header_{run_id}")
    try:
        with open(marker, "x", encoding="utf-8"):
            pass
    except FileExistsError:
        return

    print("Running: consensus", flush=True)


def main():
    global consensus_autop2_version

    if len(sys.argv) < 4:
        sys.exit("Usage: consensus.py <input_dir> <out_dir> <prefix>")

    input_dir, out_dir, prefix = sys.argv[1], sys.argv[2], sys.argv[3]
    load_config()

    project = os.environ.get("project", "")
    input_path = f"/data/{input_dir}"
    output_path = f"/data/{out_dir}"
    work_base = f"/data/{prefix}consensus"

    os.makedirs(output_path, exist_ok=True)
    os.makedirs(work_base, exist_ok=True)
    os.makedirs(f"/data/{project}/intermediate_files/done_files", exist_ok=True)
    os.makedirs(f"/data/{project}/intermediate_files/warning_files", exist_ok=True)
    os.makedirs("/data/files_to_keep", exist_ok=True)

    max_number = os.environ.get("consensus_active_max_number", "")
    min_number = os.environ.get("consensus_active_min_number", "")
    critical_number = os.environ.get("consensus_critical_active_number", "")
    preferred_1 = os.environ.get("consensus_preferred_1", "")
    preferred_2 = os.environ.get("consensus_preferred_2", "")

    if not min_number or not max_number or not critical_number:
        sys.exit("[ERROR] Missing consensus thresholds in /data/config")

    if not preferred_1 or not preferred_2:
        sys.exit("[ERROR] Missing consensus preferred methods in /data/config")

    min_number = int(min_number)
    max_number = int(max_number)
    critical_number = int(critical_number)


    if not os.path.isdir(input_path):
        sys.exit(f"[ERROR] Input path does not exist: {input_path}")

    # BLOCK=yes: main.py invokes this module once per ligand.  Avoid
    # reprocessing every protein directory on every invocation.
    module_defs_path = os.environ.get("MODULE_DEFS_FILE", "/opt/module_defs.conf")
    module_flags = parse_module_defs(module_defs_path).get("consensus")
    if module_flags is None:
        sys.exit(f"[ERROR] Missing [consensus] section in {module_defs_path}")

    if module_flags["BLOCK"]:
        protein = _selected_protein_for_block(project)
        _announce_consensus_once_per_pipeline(project, prefix)
        protein_dir = os.path.join(input_path, protein)
        if not os.path.isdir(protein_dir):
            print(f"[WARNING] No consensus input folder for {protein}: {protein_dir}")
            mark_do_not_run(protein, project)
        else:
            run_consensus_for_protein(
                protein, protein_dir, work_base, output_path, out_dir, project,
                preferred_1, preferred_2, min_number, max_number, critical_number,
            )
    else:
        print("Running: consensus", flush=True)
        # BLOCK=no: process all protein folders, regardless of whether an
        # input_ligand.txt from a previous run happens to exist.
        protein_dirs = [
            path for path in sorted(glob.glob(os.path.join(input_path, "*")))
            if os.path.isdir(path)
        ]
        if not protein_dirs:
            sys.exit(f"[ERROR] No protein folders found inside {input_path}")

        for protein_dir in protein_dirs:
            protein = os.path.basename(protein_dir)
            run_consensus_for_protein(
                protein, protein_dir, work_base, output_path, out_dir, project,
                preferred_1, preferred_2, min_number, max_number, critical_number,
            )

    record_version(f"consensus {consensus_autop2_version}")


if __name__ == "__main__":
    main()

