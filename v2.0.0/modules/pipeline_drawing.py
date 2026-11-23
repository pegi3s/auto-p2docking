#!/usr/bin/env python3
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pymodule_common import load_config

pipeline_drawing_autop2_version = "2.0.0"
pipeline_drawing_docker_version = "2.43.0"
pipeline_drawing_program_version = "2.43.0"


def _get_source_pdbs_modules(module_defs_path):
    """Equivalent of `main`'s/`pipeline_drawing`'s extract_module_section():
    returns the set of module names whose module_defs.conf section has
    source_PDBs=yes."""
    if not os.path.isfile(module_defs_path):
        return set()

    with open(module_defs_path) as f:
        content = f.read()

    pieces = re.split(r"(?m)^\[([^\[\]]+)\]$", content)
    modules = set()
    # pieces = [pre-text, name1, body1, name2, body2, ...]
    for i in range(1, len(pieces), 2):
        name = pieces[i]
        body = pieces[i + 1]
        value = "no"
        for line in body.splitlines():
            m = re.match(r"^\s*source_PDBs\s*=\s*(\S+)", line)
            if m:
                value = m.group(1)
        if value == "yes":
            modules.add(name)
    return modules


def _field(line, index):
    """Equivalent of `cut -fN -d' '` (1-based N == index + 1): splits on a
    literal single space (not whitespace runs), so repeated spaces produce
    empty fields, unlike awk/Python's default split()."""
    parts = line.split(" ")
    return parts[index] if len(parts) > index else ""


def main():
    global pipeline_drawing_autop_version, pipeline_drawing_docker_version
    global pipeline_drawing_program_version

    load_config()

    if os.environ.get("pipeline_drawing_docker_c_version"):
        pipeline_drawing_autop_version = "?"
        pipeline_drawing_docker_version = os.environ["pipeline_drawing_docker_c_version"]
        pipeline_drawing_program_version = "?"

    host_dir = os.environ.get("dir", "")

    # Modules marked source_PDBs=yes in module_defs.conf read PDB files
    # directly from PDBs/Ligands and PDBs/Receptor regardless of what their
    # "input" column in /data/pipeline declares. Since that dependency
    # never shows up as a column match, build the list of such modules
    # here so the links can be added to the graph explicitly further down.
    module_defs_path = os.environ.get("MODULE_DEFS_FILE", "/opt/module_defs.conf")
    source_pdbs_modules = _get_source_pdbs_modules(module_defs_path)

    print("Drawing pipeline")

    with open("/data/pipeline") as f:
        pipeline_lines = f.read().splitlines()

    stripped_lines = [re.sub(r"/(?!Ligands\b|Receptor\b)[^ ]*", "", line) for line in pipeline_lines]

    input_list = sorted(set(_field(line, 1) for line in pipeline_lines))
    output_list = sorted(set(_field(line, 2) for line in pipeline_lines))

    combined = input_list + output_list
    counts = {}
    for value in combined:
        counts[value] = counts.get(value, 0) + 1
    unique_list1 = sorted(v for v in set(combined) if counts[v] == 1)

    combined2 = input_list + unique_list1
    counts2 = {}
    for value in combined2:
        counts2[value] = counts2.get(value, 0) + 1
    unique_list2 = sorted(v for v in set(combined2) if counts2[v] > 1)

    unique_list_commands = []
    for unique_input in unique_list2:
        pattern = f" {unique_input} "
        for line in pipeline_lines:
            if pattern in line:
                unique_list_commands.append(line)

    synthetic_lines = []
    for line in unique_list_commands:
        third = _field(line, 1)
        synthetic_lines.append(f"data data {third}")

    pipeline_with_data = sorted(set(stripped_lines + synthetic_lines))

    seen_counts = {}
    pipeline_mod = []
    for line in pipeline_with_data:
        parts = line.split()
        if len(parts) < 3:
            continue
        first_word, second_word, third_word = parts[0], parts[1], parts[2]

        count = seen_counts.get(first_word, 0)
        if count > 0:
            modified_first_word = f"{first_word}\u00a7{count}"
            seen_counts[first_word] = count + 1
        else:
            modified_first_word = f"{first_word}\u00a70"
            seen_counts[first_word] = 1

        pipeline_mod.append((modified_first_word, second_word, third_word))

    edge_lines = set()
    for o_first, _o_second, o_third in pipeline_mod:
        for n_first, n_second, _n_third in pipeline_mod:
            n_first_base = n_first.split("\u00a7", 1)[0]
            if n_second == o_third:
                edge_lines.add(f"'{o_first}' '{n_first}'")
            elif o_third in ("PDBs/Ligands", "PDBs/Receptor", "PDBs") and n_first_base in source_pdbs_modules:
                edge_lines.add(f"'{o_first}' '{n_first}'")

    tmp1 = sorted(edge_lines)

    pipeline_py_lines = ["import graphviz", "dot = graphviz.Digraph('Pipeline')"]
    for node, _input, output in pipeline_mod:
        if node.startswith("copy§") and output in ("PDBs/Ligands", "PDBs/Receptor"):
            pipeline_py_lines.append(f"dot.node('{node}', 'copy ({output})')")
    for line in tmp1:
        value1, value2 = line.split(" ", 1)
        if value1 != value2:
            pipeline_py_lines.append(f"dot.edge({value1}, {value2})")
    pipeline_py_lines.append("dot.format = 'svg'")
    pipeline_py_lines.append("dot.render(directory='/data').replace('\\\\', '/')")

    with open("/data/pipeline.py", "w") as f:
        f.write("\n".join(pipeline_py_lines) + "\n")

    subprocess.run(
        [
            "docker", "run",
            "-v", f"{host_dir}:/data",
            f"pegi3s/graphviz:{pipeline_drawing_docker_version}",
            "bash", "-c", "cd /data && python3 pipeline.py",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    for path in ("/data/pipeline.py", "/data/Pipeline.gv"):
        if os.path.exists(path):
            os.remove(path)

    svg_path = "/data/Pipeline.gv.svg"
    if os.path.isfile(svg_path):
        with open(svg_path) as f:
            content = f.read()
        content = re.sub(r"\u00a7[0-9]*", "", content)
        with open(svg_path, "w") as f:
            f.write(content)


if __name__ == "__main__":
    main()
