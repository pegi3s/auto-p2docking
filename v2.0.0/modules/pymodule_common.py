#!/usr/bin/env python3
"""Shared helpers for Python translations of the bash auto-p2docking modules.

Every bash module follows the same convention:

    . /data/config
    input_dir=$1
    out_dir=$2
    prefix=$3
    if [ "$<module>_docker_c_version" != "" ]; then
        ...override autop2_version/docker_version/ref/doi with "?"...
    fi
    ...
    echo "<module> $version,..." >> /data/files_to_keep/versions.csv
    echo -e "..._ref=\"...\"\n..._doi=\"...\"" >> /data/$project/intermediate_files/refs/tmp_references

This module provides the Python equivalents of the parts of that
convention that are not module-specific, so a Python module can keep the
exact same "shape" as its bash counterpart:

  - load_config(): equivalent of ". /data/config"
  - record_version(): equivalent of the versions.csv "echo ... >>" line
  - record_refs(): equivalent of the tmp_references "echo -e ... >>" line
"""
import fnmatch
import os
import re
import shutil
import subprocess
import sys


def load_config(config_path="/data/config"):
    """Populate os.environ with the variables defined in a bash-style config
    file, exactly like ". /data/config" does for the bash modules.

    The config file provided by the user is a real (if simple) bash script,
    so instead of re-implementing a bash parser, we let bash source it and
    adopt whatever environment variables it produced. This keeps behavior
    identical to the bash modules regardless of quoting/expansions used in
    the config file.

    Returns the dict of variables that were (re)defined by this file, for
    convenience, but the values are also applied directly to os.environ.
    """
    if not os.path.isfile(config_path):
        return {}

    script = f'set -a; . "{config_path}"; env -0'
    result = subprocess.run(
        ["bash", "-c", script],
        capture_output=True,
        check=True,
    )

    updated = {}
    for entry in result.stdout.split(b"\0"):
        if not entry:
            continue
        key, _, value = entry.decode(errors="surrogateescape").partition("=")
        if os.environ.get(key) != value:
            updated[key] = value
        os.environ[key] = value
    return updated


def record_version(line, versions_path="/data/files_to_keep/versions.csv"):
    """Append one line to files_to_keep/versions.csv (matches every
    module's trailing `echo "..." >> /data/files_to_keep/versions.csv`)."""
    os.makedirs(os.path.dirname(versions_path), exist_ok=True)
    with open(versions_path, "a") as f:
        f.write(line + "\n")


def record_refs(text, project=None):
    """Append text to <project>/intermediate_files/refs/tmp_references
    (matches modules' trailing `echo -e "..." >> .../tmp_references`).
    `text` should already include any needed "\\n" between entries."""
    project = project if project is not None else os.environ.get("project", "")
    refs_path = f"/data/{project}/intermediate_files/refs/tmp_references"
    os.makedirs(os.path.dirname(refs_path), exist_ok=True)
    with open(refs_path, "a") as f:
        f.write(text)


AUTO_LIST_HEADER = (
    "# Generated automatically from the .pdb files in {folder}. "
    "Remove this line to keep your own selection."
)


def is_user_protein_list(list_path):
    """True when list_path is a selection written by the investigator: it
    exists, has at least one entry, and does not start with the
    AUTO_LIST_HEADER line. Generated or empty lists are rebuilt."""
    if not os.path.isfile(list_path):
        return False
    with open(list_path, encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]
    if lines and lines[0].startswith("# Generated automatically"):
        return False
    return any(not line.startswith("#") for line in lines)


def write_protein_list(list_path, source_dir):
    """Writes the .pdb files of source_dir, sorted, to list_path under the
    AUTO_LIST_HEADER line."""
    os.makedirs(os.path.dirname(list_path), exist_ok=True)
    folder = os.path.relpath(source_dir, os.path.dirname(os.path.dirname(list_path)))
    with open(list_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(AUTO_LIST_HEADER.format(folder=folder) + "\n")
        for name in sorted(os.listdir(source_dir)):
            if name.lower().endswith(".pdb") and os.path.isfile(os.path.join(source_dir, name)):
                f.write(name + "\n")


def check_sites_files(input_dir, *pdb_names):
    """Exit with an error unless /data/<input_dir>/<name>/<name>_active.sites
    and <name>_passive.sites exist for every name (shared by the docking
    modules that use active/passive sites)."""
    missing = [
        f"/data/{input_dir}/{name}/{name}_{kind}.sites"
        for name in pdb_names
        for kind in ("active", "passive")
        if not os.path.isfile(f"/data/{input_dir}/{name}/{name}_{kind}.sites")
    ]
    if missing:
        sys.exit(
            "[ERROR] Missing active/passive sites file(s) in the module input "
            f"folder: {', '.join(missing)}"
        )


_TM_SCORE_RE = re.compile(r"TM-score \(chain[12]\):\s*([0-9.]+)")


def parse_max_tm_score(path):
    """Return the highest TM-score found in a tmtools plain-text result
    file (lines like "TM-score (chain1): 0.1234"), or None if the file is
    missing or contains no parseable score (equivalent of the bash
    `grep -E 'TM-score \\(chain[12]\\):' | sed -E 's/.*: //' | sort -g | tail -1`
    pipeline, but without the "-gt on an empty/non-numeric string" bug
    class that pipeline is prone to)."""
    if not os.path.isfile(path):
        return None
    best = None
    with open(path) as f:
        for line in f:
            m = _TM_SCORE_RE.search(line)
            if not m:
                continue
            try:
                value = float(m.group(1))
            except ValueError:
                continue
            if best is None or value > best:
                best = value
    return best


def remove_empty_files(directory):
    """Recursively delete every zero-byte file under `directory`, matching
    the bash modules' `find . -type f -empty -print -delete` cleanup step
    (used after a docker run that may have left partial/failed downloads
    behind as empty files)."""
    for root, _dirs, files in os.walk(directory):
        for name in files:
            path = os.path.join(root, name)
            if os.path.getsize(path) == 0:
                os.remove(path)


def _clean_header(value):
    return value.strip().lower().replace(" ", "").replace("-", "_")


def convert_interface_csv_to_consensus_format(input_csv, output_file):
    """Convert an ISPRED4/PeSTo-style "interface residues" CSV (delimited
    by ";" or ",", with a residue-number column and a "code" column) into
    the plain-text consensus format "residue_number code" (one per line,
    sorted by residue number). Equivalent of the identical Python heredoc
    embedded in both the bash `ispred4` and `pesto` modules."""
    import csv

    with open(input_csv, "r", encoding="utf-8-sig", errors="replace", newline="") as handle:
        sample = handle.read(4096)
        handle.seek(0)

        delimiter = ";" if sample.count(";") >= sample.count(",") else ","
        reader = csv.DictReader(handle, delimiter=delimiter)

        if not reader.fieldnames:
            raise SystemExit(f"Empty or invalid CSV: {input_csv}")

        cleaned = {_clean_header(field): field for field in reader.fieldnames}

        res_col = None
        for candidate in ["res_num", "residue", "residue_number", "position", "pos", "seq_pos"]:
            if candidate in cleaned:
                res_col = cleaned[candidate]
                break

        code_col = cleaned.get("code")

        if res_col is None or code_col is None:
            raise SystemExit(
                f"Missing residue/code columns in {input_csv}. "
                f"Headers: {reader.fieldnames}"
            )

        rows = []

        for row in reader:
            raw_residue = str(row.get(res_col, "")).strip()
            raw_code = str(row.get(code_col, "")).strip()

            if raw_residue == "" or raw_code == "":
                continue

            try:
                residue_number = int(float(raw_residue))
                code = int(float(raw_code))
            except ValueError:
                continue

            if code not in {0, 1, 2}:
                code = 0

            rows.append((residue_number, code))

    with open(output_file, "w", encoding="utf-8", newline="\n") as out:
        for residue_number, code in sorted(rows):
            out.write(f"{residue_number} {code}\n")


def read_fields(line, n):
    """Equivalent of bash's "read f1 f2 ... fN" for a fixed number of
    whitespace-separated fields: missing trailing fields become "", and if
    the line has more than n fields the last one keeps the remainder of
    the line."""
    parts = line.split(None, n - 1)
    while len(parts) < n:
        parts.append("")
    return parts


def normalize_command_name(command):
    """Strips a trailing ".py" (if present) from a module "command" name.

    module_defs.conf section headers are always bare (e.g. "[hdock]"), but
    /data/pipeline's command column may still use either form ("hdock" or
    "hdock.py"). Every lookup keyed by module_defs.conf's section name
    (BLOCK_MODULES/NEEDS_LIGANDS_LIST_MODULES membership, keep_files
    section extraction, the literal hdock/haddock/pydock_ftdock docker
    image checks, ...) must normalize the pipeline's command through this
    first, or it silently fails to match whenever ".py" is used -- unlike
    resolve_command_path(), which already tries both forms when resolving
    the file to execute.
    """
    if command.endswith(".py"):
        return command[:-3]
    return command


def resolve_command_path(command, opt_dir="/opt"):
    """Resolves a module "command" name (as declared in /data/pipeline or a
    module_defs.conf section header, e.g. "highlight_regions") to the
    actual executable file under opt_dir. Tries the exact name first (a
    still-bash module, or a name that already includes ".py"), then falls
    back to "<command>.py" so pipeline/module_defs.conf entries can drop
    the ".py" suffix. Returns None if neither exists."""
    exact = os.path.join(opt_dir, command)
    if os.path.isfile(exact):
        return exact
    with_py = os.path.join(opt_dir, f"{command}.py")
    if os.path.isfile(with_py):
        return with_py
    return None


def _iter_module_def_sections(module_defs_path):
    """Yields (module_name, section_body) tuples for every "[name]" section
    in a module_defs.conf-style file, in file order."""
    if not os.path.isfile(module_defs_path):
        return
    with open(module_defs_path) as f:
        content = f.read()
    pieces = re.split(r"(?m)^\[([^\[\]]+)\]$", content)
    for i in range(1, len(pieces), 2):
        yield pieces[i], pieces[i + 1]


def extract_module_section(module_defs_path, module_name):
    """Equivalent of `main`/`pre_main`'s extract_module_section(): returns
    the body text of the "[module_name]" section, or None if there is no
    such section."""
    for name, body in _iter_module_def_sections(module_defs_path):
        if name == module_name:
            return body
    return None


def parse_module_defs(module_defs_path):
    """Parse module flags; absent flags default to False.

    NEEDS_LIGANDS_LIST and NEEDS_RECEPTORS_LIST declare supported roles;
    the pipeline dispatcher chooses the relevant list for each branch.
    """
    modules = {}
    for name, body in _iter_module_def_sections(module_defs_path):
        flags = {
            "BLOCK": False,
            "NEEDS_LIGANDS_LIST": False,
            "NEEDS_RECEPTORS_LIST": False,
            "source_PDBs": False,
        }
        for line in body.splitlines():
            m = re.match(
                r"^\s*(BLOCK|NEEDS_LIGANDS_LIST|NEEDS_RECEPTORS_LIST|source_PDBs)\s*=\s*(\S+)",
                line,
            )
            if m:
                flags[m.group(1)] = m.group(2) == "yes"
        modules[name] = flags
    return modules


_KEEP_FILES_RE = re.compile(r'^\s*keep_files\s+"([^"]*)"\s+"([^"]*)"')


def _expand_keep_files_vars(text, variables):
    """Equivalent of bash's double-quote variable expansion for the
    keep_files "name_or_glob_pattern" "dest_name" arguments (e.g.
    "exclude_list-$prefix_mod.*"): substitutes "$name"/"${name}" with the
    matching entry in `variables`, leaving anything else untouched."""
    def repl(m):
        name = m.group(1) or m.group(2)
        return variables.get(name, m.group(0))

    return re.sub(r"\$\{(\w+)\}|\$(\w+)", repl, text)


def _keep_files_matches(base_dir, pattern):
    """Return all matches, preserving structure relative to the searched root.

    A bare '*' denotes the entire output directory (the original convention).
    Otherwise, match a basename or a relative path if the pattern contains '/'.
    """
    if not base_dir or not os.path.isdir(base_dir):
        return []
    if pattern == "*":
        return [base_dir]
    found = []
    for root, dirs, files in os.walk(base_dir):
        dirs.sort()
        for name in sorted(dirs) + sorted(files):
            path = os.path.join(root, name)
            relative = os.path.relpath(path, base_dir).replace(os.sep, "/")
            comparable = relative if "/" in pattern else name
            if fnmatch.fnmatchcase(comparable, pattern):
                found.append(path)
    # Matching a directory makes nested matches redundant.
    selected = []
    for path in sorted(found, key=lambda p: (p.count(os.sep), p)):
        if not any(os.path.commonpath([path, parent]) == parent for parent in selected):
            selected.append(path)
    return selected


def _keep_files_copy(name_pattern, dest_name, project, prefix_mod, module_cmd, module_output):
    """Copy all requested output(s) to stable destinations using existing syntax.

    Repeated calls for a block merge directory trees instead of producing .1/.2.
    File-to-file destinations still work for legacy `keep_files "x" "y"` rules.
    """
    variables = {
        "project": project, "prefix_mod": prefix_mod,
        "module_cmd": module_cmd, "module_output": module_output,
    }
    pattern = _expand_keep_files_vars(name_pattern, variables)
    dest = _expand_keep_files_vars(dest_name, variables)
    output_root = os.path.abspath(f"/data/{project}/{module_output}")
    matches = _keep_files_matches(output_root, pattern)
    source_root = output_root
    if not matches:
        source_root = os.path.abspath(
            f"/data/{project}/intermediate_files/{prefix_mod}/{prefix_mod}-{module_cmd}"
        )
        matches = _keep_files_matches(source_root, pattern)
    if not matches:
        return

    base_keep = os.path.abspath('/data/files_to_keep')
    dest_path = os.path.abspath(os.path.join(base_keep, dest))
    if os.path.commonpath([base_keep, dest_path]) != base_keep or dest_path == base_keep:
        raise ValueError(f"Invalid keep_files destination: {dest}")

    for match in matches:
        is_dir = os.path.isdir(match)
        actual_dest = dest_path
        if '*' in pattern and '*' in dest:
            name = os.path.basename(match)
            before, _, after = pattern.partition('*')
            wild = name
            if wild.startswith(before):
                wild = wild[len(before):]
            if after and wild.endswith(after):
                wild = wild[:-len(after)]
            expanded_dest = dest.replace('*', wild, 1)
            actual_dest = os.path.abspath(os.path.join(base_keep, expanded_dest))
            if os.path.commonpath([base_keep, actual_dest]) != base_keep:
                raise ValueError(f"Invalid keep_files destination: {expanded_dest}")

        if not is_dir and (len(matches) > 1 or os.path.isdir(actual_dest)):
            relative = os.path.relpath(match, source_root)
            actual_dest = os.path.join(actual_dest, relative)
        if is_dir:
            # Bare '*' copies folder contents; other folder patterns copy the
            # matched folder as the destination, retaining its own hierarchy.
            if os.path.isfile(actual_dest):
                raise ValueError(f"Cannot merge directory into file: {actual_dest}")
            os.makedirs(actual_dest, exist_ok=True)
            shutil.copytree(match, actual_dest, dirs_exist_ok=True)
        else:
            os.makedirs(os.path.dirname(actual_dest), exist_ok=True)
            shutil.copy2(match, actual_dest)


def run_keep_files(command, prefix_mod, output, project=None, module_defs_path=None):
    """Apply plain `keep_files "name_or_pattern" "destination"` rules."""
    project = project if project is not None else os.environ.get('project', '')
    module_defs_path = module_defs_path or os.environ.get('MODULE_DEFS_FILE', '/opt/module_defs.conf')
    body = extract_module_section(module_defs_path, command)
    if body is None:
        return
    for line in body.splitlines():
        m = _KEEP_FILES_RE.match(line)
        if m:
            _keep_files_copy(m.group(1), m.group(2), project, prefix_mod, command, output)

def update_run_summary(path, fieldnames, key_columns, row):
    """Upsert an output CSV record; preserves earlier BLOCK runs and avoids duplicates.

    Only used by modules explicitly importing this helper.
    """
    import csv
    path = os.fspath(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    records = []
    if os.path.isfile(path):
        with open(path, newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle, delimiter=";")
            if reader.fieldnames != list(fieldnames):
                raise ValueError(
                    f"Incompatible existing summary {path}: {reader.fieldnames}. "
                    "Use a clean output directory or migrate this CSV."
                )
            records = list(reader)

    key = tuple(row[column] for column in key_columns)
    records = [
        existing for existing in records
        if tuple(existing[column] for column in key_columns) != key
    ]
    records.append(row)

    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter=";", lineterminator="\n")
        writer.writeheader()
        writer.writerows(records)

