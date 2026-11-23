#!/usr/bin/env python3
"""Python translation of the bash "pre_main" entrypoint script.

Normalizes /data/pipeline and /data/config (stripping any stray "\\r"
characters, and empty lines from the pipeline), handles the special
pipeline-drawing/protocol-download "pipeline" modes, otherwise validates
/data/pipeline (every command must resolve to an actual module, every
module used inside a "block" sequence must be BLOCK-compatible per
module_defs.conf, and connected modules must have compatible
INPUT_TYPES/OUTPUT_TYPES) and that the docker images required by
hdock/haddock/pydock_ftdock are present, then runs main.py.

Every failure exits with status 1, and main.py's exit status is passed
on, so a script running the image can detect failed runs.

Module "command" values (in /data/pipeline) may be given either with or
without their ".py" suffix (e.g. "highlight_regions" or
"highlight_regions.py") -- see pymodule_common.resolve_command_path().
"""
import os
import re
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pymodule_common import normalize_command_name, parse_module_defs, read_fields, resolve_command_path

MODULE_DEFS_FILE = os.environ.get("MODULE_DEFS_FILE", "/opt/module_defs.conf")

PROTOCOLS_URL = (
    "http://evolution6.i3s.up.pt/static/"
    "auto-p2docking/v2/Protocols"
)

REQUIRED_DOCKER_IMAGES = {
    "hdock": "pegi3s/hdock",
    "haddock": "pegi3s/haddock24",
    "pydock_ftdock": "pegi3s/pydock3",
    "rosettadock": "pegi3s/rosettadock-screening",
}


def _strip_cr(path):
    with open(path, "rb") as f:
        content = f.read()
    content = content.replace(b"\r", b"")
    with open(path, "wb") as f:
        f.write(content)


def _remove_empty_lines(path):
    with open(path, encoding="utf-8") as f:
        lines = [line.rstrip() for line in f.read().splitlines()]
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for line in lines:
            if line:
                f.write(line + "\n")


def _parse_module_types(path):
    """Returns {module: (input_types, output_types)} from the INPUT_TYPES=
    and OUTPUT_TYPES= lines (space-separated) of module_defs.conf."""
    types = {}
    current_module = None

    with open(path, encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()

            if not line or line.startswith("#"):
                continue

            if line.startswith("[") and line.endswith("]"):
                current_module = normalize_command_name(line[1:-1].strip())
                types[current_module] = (set(), set())
                continue

            if current_module:
                for index, key in enumerate(("INPUT_TYPES=", "OUTPUT_TYPES=")):
                    if line.startswith(key):
                        types[current_module][index].update(line[len(key):].split())

    return types


def _validate_connections(pipeline_lines, module_types):
    """Every module that reads the output of earlier modules must accept at
    least one of the types each of them produces. Modules without
    INPUT_TYPES/OUTPUT_TYPES (e.g. copy) are not checked."""
    output_producers = {}

    for line_number, line in enumerate(pipeline_lines, start=1):
        command, input_, output, block, number = read_fields(line, 5)
        command = normalize_command_name(command)
        accepted = module_types.get(command, (set(), set()))[0]

        for producer in output_producers.get(input_, []):
            produced = module_types.get(producer, (set(), set()))[1]
            if accepted and produced and not accepted & produced:
                print(
                    f"Invalid pipeline connection (line {line_number}): "
                    f"{producer} -> {command}"
                )
                print(
                    f"{producer} produces {' '.join(sorted(produced))}, but "
                    f"{command} accepts {' '.join(sorted(accepted))}"
                )
                sys.exit(1)

        if output:
            producers = output_producers.setdefault(output, [])
            if command not in producers:
                producers.append(command)


def main():
    _strip_cr("/data/pipeline")
    _strip_cr("/data/config")
    _remove_empty_lines("/data/pipeline")

    with open("/data/pipeline") as f:
        pipeline_lines = f.read().splitlines()

    check_pipeline = pipeline_lines[0] if pipeline_lines else ""

    if check_pipeline == "pipeline_drawing":
        os.makedirs("/data/files_to_keep", exist_ok=True)
        with open("/data/pipeline", "w", encoding="utf-8", newline="\n") as f:
            for line in pipeline_lines[1:]:
                f.write(line + "\n")
        # pipeline_drawing is a fixed dispatcher-invoked helper (not a
        # user-declared pipeline module), so it is called directly rather
        # than through resolve_command_path().
        returncode = subprocess.run(["/opt/pipeline_drawing.py"]).returncode
        with open("/data/pipeline") as f:
            rest = f.read()
        with open("/data/pipeline", "w", encoding="utf-8", newline="\n") as f:
            f.write("pipeline_drawing\n" + rest)
        shutil.rmtree("/data/files_to_keep")
        sys.exit(returncode)

    elif check_pipeline == "protocol_description":
        print("Please see the generated protocol description file")
        result = subprocess.run(
            ["wget", f"{PROTOCOLS_URL}/protocol_description", "-P", "/data"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if result.returncode != 0:
            print("Could not download the protocol description file")
            sys.exit(1)

    elif check_pipeline.startswith("protocol_"):
        failed = []
        for line in pipeline_lines:
            result = subprocess.run(
                ["wget", f"{PROTOCOLS_URL}/{line}.zip", "-P", "/data"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            if result.returncode != 0:
                failed.append(line)
        if failed:
            print(f"Could not download: {', '.join(failed)}")
            sys.exit(1)

    else:
        for line in pipeline_lines:
            a = line.split()[0] if line.split() else ""
            if resolve_command_path(a) is None:
                print(f"This is an invalid command: {a}")
                sys.exit(1)

        # check that every module used inside a "block" is BLOCK-compatible
        modules = parse_module_defs(MODULE_DEFS_FILE)

        _validate_connections(pipeline_lines, _parse_module_types(MODULE_DEFS_FILE))

        block_modules = {name for name, flags in modules.items() if flags["BLOCK"]}

        idx = 0
        n = len(pipeline_lines)
        while idx < n:
            line = pipeline_lines[idx]
            idx += 1

            command, input_, output, block, number = read_fields(line, 5)
            # module_defs.conf section headers are always bare; normalize
            # so the BLOCK_MODULES lookup matches regardless of whether
            # /data/pipeline uses "hdock" or "hdock.py".
            command = normalize_command_name(command)

            if block == "block":
                if command not in block_modules:
                    print(
                        "Please revise your pipeline file. The block command "
                        "includes modules that are not compatible with the "
                        "block command"
                    )
                    sys.exit(1)

                try:
                    number_int = int(number)
                except ValueError:
                    number_int = 0

                k = 1
                while k < number_int:
                    line3 = pipeline_lines[idx]
                    idx += 1
                    command3 = read_fields(line3, 3)[0]
                    command3 = normalize_command_name(command3)
                    if command3 not in block_modules:
                        print(
                            "Please revise your pipeline file. The block "
                            "command includes modules that are not "
                            "compatible with the block command"
                        )
                        sys.exit(1)
                    k += 1

        # check docker images
        result = subprocess.run(
            ["docker", "image", "list"], capture_output=True, text=True
        )
        image_lines = result.stdout.splitlines()

        command_list = []
        for line in pipeline_lines:
            command_list.append(normalize_command_name(read_fields(line, 5)[0]))

        for command1 in command_list:
            image_name = REQUIRED_DOCKER_IMAGES.get(command1)
            if image_name is None:
                continue
            pattern = re.compile(r"^" + re.escape(image_name) + r"\b")
            if not any(pattern.match(img_line) for img_line in image_lines):
                print(
                    f"Please build the local {image_name} image in order to "
                    "be able to use the pipeline. The instructions are in a "
                    "file named instructions_docker_images"
                )
                shutil.copy2("/opt/instructions_docker_images", "/data")
                sys.exit(1)

        # main.py is a fixed dispatcher-invoked helper (not a user-declared
        # pipeline module), so it is called directly rather than through
        # resolve_command_path().
        sys.exit(subprocess.run(["/opt/main.py"]).returncode)


if __name__ == "__main__":
    main()
