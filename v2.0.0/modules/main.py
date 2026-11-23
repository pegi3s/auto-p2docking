#!/usr/bin/env python3
"""Python translation of the bash "main" dispatcher script.

Reads /data/config (via pymodule_common.load_config, equivalent to
". /data/config"), then walks /data/pipeline line by line, running each
declared module in turn (once, once per ligand, or as part of a "block"
sequence run in full for one ligand before moving on to the next), and
finally invokes pipeline_drawing.py.

Module "command" values (in /data/pipeline and in module_defs.conf's
section headers) may be given either with or without their ".py" suffix
(e.g. "highlight_regions" or "highlight_regions.py") -- see
pymodule_common.resolve_command_path().
"""
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pymodule_common import (
    is_user_protein_list,
    load_config,
    normalize_command_name,
    parse_module_defs,
    read_fields,
    resolve_command_path,
    run_keep_files,
    write_protein_list,
)

MODULE_DEFS_FILE = os.environ.get("MODULE_DEFS_FILE", "/opt/module_defs.conf")


def _resolve_input_arg(project, input_val):
    """If /data/$project/$input_val is an existing directory, it is a
    reference to a previous module's output and must be given as
    "$project/$input_val"; otherwise $input_val is external/raw data and
    is passed through unchanged."""
    if os.path.isdir(f"/data/{project}/{input_val}"):
        return f"{project}/{input_val}"
    return input_val


def _run_module(command, args, role=None):
    resolved = resolve_command_path(command)
    if resolved is None:
        print(f"bash: /opt/{command}: No such file or directory", file=sys.stderr)
        return
    env = os.environ.copy()
    if role is not None:
        env[_SELECTION_ROLE_ENV] = role
    else:
        env.pop(_SELECTION_ROLE_ENV, None)
    subprocess.run([resolved, *args], env=env)


# Role is inferred from the PDB source of each pipeline branch. The existing
# ligands_list.txt / input_ligand.txt contract remains unchanged.
_ROLE_CONFIG = {
    "ligand": ("Ligands", "ligands_list.txt", "input_ligand.txt"),
    "receptor": ("Receptor", "receptors_list.txt", "input_receptor.txt"),
}
_SELECTION_ROLE_ENV = "AUTO_P2DOCKING_PROTEIN_ROLE"


def _direct_role(path):
    # Exact directory names are significant: Receptor is singular.
    path = path.replace("\\", "/").strip("/")
    parts = path.split("/")
    for idx in range(len(parts) - 1):
        if parts[idx] == "PDBs":
            if parts[idx + 1] == "Ligands":
                return "ligand"
            if parts[idx + 1] == "Receptor":
                return "receptor"
    return None


def _build_output_roles(pipeline_lines):
    """Propagate source role to all downstream outputs (output1, output2...)."""
    roles = {}
    for line in pipeline_lines:
        command, source, output = read_fields(line, 3)
        role = _direct_role(source) or roles.get(source)
        output_role = _direct_role(output) or role
        if output and output_role is not None:
            old_role = roles.get(output)
            # copy may merge data from the other branch into an existing
            # output (e.g. receptor sites into the ligand docking input);
            # the destination keeps its branch.
            if normalize_command_name(command) == "copy" and old_role is not None:
                continue
            if old_role is not None and old_role != output_role:
                sys.exit(
                    f"[ERROR] Output {output!r} mixes ligand and receptor "
                    "branches. Use separate outputs for each branch."
                )
            roles[output] = output_role
    return roles


def _role_for_input(input_name, roles):
    # Legacy pipelines without a recognized PDB source keep ligand behavior.
    return _direct_role(input_name) or roles.get(input_name, "ligand")


def _selected_protein_names(project, role):
    folder, list_name, _ = _ROLE_CONFIG[role]
    base_dir = f"/data/{project}/PDBs"
    source_dir = os.path.join(base_dir, folder)
    list_path = os.path.join(base_dir, list_name)
    if not is_user_protein_list(list_path):
        if not os.path.isdir(source_dir):
            sys.exit(f"[ERROR] Missing PDB directory for {role}: {source_dir}")
        write_protein_list(list_path, source_dir)

    with open(list_path, encoding="utf-8") as handle:
        names = [name.strip() for name in handle if name.strip() and not name.lstrip().startswith("#")]
    if not names:
        sys.exit(f"[ERROR] No proteins were selected in {list_path}")
    if len(set(names)) != len(names):
        sys.exit(f"[ERROR] Duplicate PDB filenames in {list_path}")
    for name in names:
        if name != os.path.basename(name) or not name.lower().endswith(".pdb"):
            sys.exit(f"[ERROR] Invalid PDB filename in {list_path}: {name!r}")
        if not os.path.isfile(os.path.join(source_dir, name)):
            sys.exit(f"[ERROR] PDB selected in {list_path} does not exist: {name}")
    return names


def _write_selected_protein(project, name, role):
    _, _, selection_file = _ROLE_CONFIG[role]
    path = f"/data/{project}/PDBs/{selection_file}"
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(name + "\n")


def _validate_selection_role(command, role, modules):
    """Check that a per-protein module supports the selected branch.

    Legacy BLOCK=yes modules with no NEEDS_* flags remain ligand-only.
    Both NEEDS_* flags are capabilities, not two loops per invocation.
    """
    flags = modules.get(command, {})
    wants_ligands = flags.get("NEEDS_LIGANDS_LIST", False)
    wants_receptors = flags.get("NEEDS_RECEPTORS_LIST", False)
    if role == "receptor" and not wants_receptors:
        sys.exit(
            f"[ERROR] Module {command} does not declare "
            "NEEDS_RECEPTORS_LIST=yes for the receptor branch."
        )
    if role == "ligand" and wants_receptors and not wants_ligands:
        sys.exit(
            f"[ERROR] Module {command} does not declare "
            "NEEDS_LIGANDS_LIST=yes for the ligand branch."
        )


def _last_output_for_command(pipeline_lines, cmd):
    """Equivalent of:
    awk -v cmd="$new_cmd" '$1==cmd {value=$3} END {print value}' /data/pipeline
    i.e. the "output" field of the LAST line in the whole pipeline file
    whose command equals cmd."""
    value = ""
    for raw in pipeline_lines:
        parts = raw.split()
        if parts and normalize_command_name(parts[0]) == cmd:
            value = parts[2] if len(parts) > 2 else ""
    return value


def _append_line(path, text):
    with open(path, "a", encoding="utf-8", newline="\n") as f:
        f.write(text + "\n")


def main():
    load_config()
    project = os.environ.get("project", "")

    os.makedirs("/data/files_to_keep", exist_ok=True)
    os.makedirs(f"/data/{project}/intermediate_files/refs", exist_ok=True)

    with open("/data/files_to_keep/versions.csv", "w", encoding="utf-8", newline="\n") as f:
        f.write("Module,Docker image,Program,Reference,DOI\n")

    with open("/data/pipeline") as f:
        raw_pipeline_lines = f.read().splitlines()

    # Equivalent of the output_list.txt built (then later grep'd against and
    # removed) by the bash script: the non-blank "output" column values.
    output_list_lines = []
    for line in raw_pipeline_lines:
        parts = line.split()
        output1 = parts[2] if len(parts) > 2 else ""
        if output1.strip():
            output_list_lines.append(output1)

    output_roles = _build_output_roles(raw_pipeline_lines)
    modules = parse_module_defs(MODULE_DEFS_FILE)
    block_modules = {name for name, flags in modules.items() if flags["BLOCK"]}
    needs_ligands_list_modules = {
        name for name, flags in modules.items() if flags["NEEDS_LIGANDS_LIST"]
    }
    needs_receptors_list_modules = {
        name for name, flags in modules.items()
        if flags.get("NEEDS_RECEPTORS_LIST", False)
    }

    blocks_and_commands_path = f"/data/{project}/intermediate_files/blocks_and_commands"

    i = 0
    j = 1
    old_output = ""

    idx = 0
    n = len(raw_pipeline_lines)
    while idx < n:
        line = raw_pipeline_lines[idx]
        idx += 1

        command, input_, output, block, number = read_fields(line, 5)
        # module_defs.conf section headers are always bare; normalize so
        # BLOCK_MODULES/NEEDS_LIGANDS_LIST_MODULES/run_keep_files lookups
        # match regardless of whether /data/pipeline uses "hdock" or
        # "hdock.py".
        command = normalize_command_name(command)

        if old_output != input_:
            i += 1
            j = 1
        elif old_output == "":
            i = 1
            j = 1
        else:
            j += 1

        prefix = f"B{i}C{j}/B{i}C{j}-"
        input_arg = _resolve_input_arg(project, input_)
        line_actual = f"{command} {input_arg} {project}/{output}"

        is_true_block = command in block_modules and block == "block"

        if is_true_block:
            block_pipeline_entries = [
                (command, input_arg, f"{project}/{output}", f"{project}/intermediate_files/{prefix}")
            ]
            concat_command = line_actual

            try:
                number_int = int(number)
            except ValueError:
                number_int = 0

            k = 1
            while k < number_int:
                line3 = raw_pipeline_lines[idx]
                idx += 1
                command3, input3, output3 = read_fields(line3, 3)
                command3 = normalize_command_name(command3)

                if (
                    os.path.isdir(f"/data/{project}/{input3}")
                    or output == input3
                    or any(input3 in ol for ol in output_list_lines)
                ):
                    input3_arg = f"{project}/{input3}"
                else:
                    input3_arg = input3

                concat_command += f" && {command3} {input3_arg} {project}/{output3}"
                block_pipeline_entries.append(
                    (command3, input3_arg, f"{project}/{output3}", f"{project}/intermediate_files/{prefix}")
                )
                k += 1

            _append_line(blocks_and_commands_path, f"{concat_command} B{i}C{j}")

            prefix_mod = f"B{i}C{j}"
            role = _role_for_input(input_, output_roles)
            # A block must operate on the same source branch throughout.
            for _cmd, _in, _out, _pfx in block_pipeline_entries:
                # _in may be project-prefixed; the roles map uses raw output names.
                _normalized_in = _in.removeprefix(f"{project}/")
                if _role_for_input(_normalized_in, output_roles) != role:
                    sys.exit("[ERROR] A BLOCK cannot mix ligand and receptor branches")
            for cmd3, _, _, _ in block_pipeline_entries:
                _validate_selection_role(cmd3, role, modules)
            selected_names = _selected_protein_names(project, role)

            for pdb2 in selected_names:
                _write_selected_protein(project, pdb2, role)
                for cmd3, in3, out3, pfx3 in block_pipeline_entries:
                    _run_module(cmd3, [in3, out3, pfx3], role=role)
                    new_output = _last_output_for_command(raw_pipeline_lines, cmd3)
                    run_keep_files(cmd3, prefix_mod, new_output, project=project, module_defs_path=MODULE_DEFS_FILE)
                    old_output = output
        else:
            _append_line(blocks_and_commands_path, f"{command} {input_} {output} B{i}C{j}")

            if (
                command in block_modules
                or command in needs_ligands_list_modules
                or command in needs_receptors_list_modules
            ):
                role = _role_for_input(input_, output_roles)
                _validate_selection_role(command, role, modules)
                # Select only the protein list matching the pipeline branch.
                selected_names = _selected_protein_names(project, role)
                for pdb2 in selected_names:
                    _write_selected_protein(project, pdb2, role)
                    input_arg = _resolve_input_arg(project, input_)
                    _run_module(
                        command,
                        [input_arg, f"{project}/{output}", f"{project}/intermediate_files/{prefix}"],
                        role=role,
                    )
                    old_output = output
            else:
                input_arg = _resolve_input_arg(project, input_)
                _run_module(
                    command,
                    [input_arg, f"{project}/{output}", f"{project}/intermediate_files/{prefix}"],
                    role=_role_for_input(input_, output_roles),
                )
                old_output = output

        prefix_mod = f"B{i}C{j}"
        run_keep_files(command, prefix_mod, output, project=project, module_defs_path=MODULE_DEFS_FILE)

    shutil.copy2("/data/config", "/data/files_to_keep")
    shutil.copy2("/data/pipeline", "/data/files_to_keep")

    pdbs_dir = f"/data/{project}/PDBs"
    if os.path.isdir(pdbs_dir):
        shutil.copytree(pdbs_dir, "/data/files_to_keep/PDBs", dirs_exist_ok=True)

    # pipeline_drawing is a fixed dispatcher-invoked helper (not a
    # user-declared pipeline module), so it is called directly rather than
    # through resolve_command_path().
    subprocess.run(["/opt/pipeline_drawing.py"])
    if os.path.isfile("/data/Pipeline.gv.svg"):
        shutil.move("/data/Pipeline.gv.svg", "/data/files_to_keep/Pipeline.gv.svg")


if __name__ == "__main__":
    main()
