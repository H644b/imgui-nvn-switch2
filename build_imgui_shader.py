#!/usr/bin/env python3
"""Adapt a user-supplied Switch 2 NVN UI2D shader for ImDrawVert RGBA."""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def field(word: int, start: int, end: int, value: int) -> int:
    if not 0 <= value < 1 << (end - start):
        raise ValueError(f"value {value} does not fit bits [{start}, {end})")
    mask = ((1 << (end - start)) - 1) << start
    return (word & ~mask) | (value << start)


def read_input(source: Path, name: str) -> bytes:
    path = source / name
    try:
        return path.read_bytes()
    except OSError as exc:
        raise SystemExit(f"cannot read {path}: {exc}") from exc


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", required=True, type=Path,
                        help="directory containing the four user-extracted variant 29 shader files")
    parser.add_argument("--output-dir", required=True, type=Path,
                        help="directory for the adapted shader and translator job files")
    args = parser.parse_args()

    source = args.input_dir
    output = args.output_dir
    output.mkdir(parents=True, exist_ok=True)

    vertex = bytearray(read_input(source, "var29-vertex.code.bin"))
    vertex_control = bytearray(read_input(source, "var29-vertex.control.bin"))
    fragment = read_input(source, "var29-fragment.code.bin")
    fragment_control = read_input(source, "var29-fragment.control.bin")
    original_vertex = bytes(vertex)
    patches: list[dict[str, object]] = []

    if len(vertex) < 0x2A0:
        raise SystemExit("variant 29 vertex code is shorter than the expected patch region")
    if struct.unpack_from("<I", vertex, 0x18)[0] != 0x37:
        raise SystemExit("unexpected vertex input mask; refusing to patch this shader")
    if struct.unpack_from("<III", vertex_control) != (0x98761234, 201, 11):
        raise SystemExit("unexpected vertex control header")
    if struct.unpack_from("<III", fragment_control) != (0x98761234, 201, 11):
        raise SystemExit("unexpected fragment control header")

    struct.pack_into("<I", vertex, 0x18, 0xF37)
    patches.append({
        "offset": 0x18,
        "purpose": "Declare all four components of generic input attribute2, retaining position0/UV1.",
    })

    template = int.from_bytes(original_vertex[0x80:0x90], "little")
    if (template & 0xFFF) != 0x321 or ((template >> 24) & 0xFF) != 0xFF:
        raise SystemExit("unexpected vertex instruction template; refusing to patch this shader")

    # Replace the game's constant-color FMULs with scalar attribute loads. Keep
    # the existing output registers and serialize the loads on scoreboard 0.
    loads = (
        (0xB0, 9, 1),
        (0x260, 8, 0),
        (0x270, 10, 2),
        (0x280, 11, 3),
    )
    for offset, destination, component in loads:
        word = int.from_bytes(original_vertex[offset:offset + 16], "little")
        word = field(word, 16, 24, destination)
        word = field(word, 40, 50, 0xA0 + component * 4)
        word = field(word, 74, 76, 0)  # scalar ALD
        word = field(word, 105, 109, 15)
        word = field(word, 110, 113, 0)
        word = field(word, 113, 116, 7)
        word = field(word, 116, 122, 63)
        vertex[offset:offset + 16] = word.to_bytes(16, "little")
        patches.append({
            "offset": offset,
            "purpose": f"Load attribute2 component{component} into existing output register R{destination}; publish scoreboard0.",
        })

    # Wait for the last attribute load before later code consumes its value.
    offset = 0x290
    word = int.from_bytes(original_vertex[offset:offset + 16], "little")
    word = field(word, 116, 122, 63)
    vertex[offset:offset + 16] = word.to_bytes(16, "little")
    patches.append({
        "offset": offset,
        "purpose": "Wait for the final attribute load; preserve the following instruction operands.",
    })

    vertex_guid = hashlib.md5(vertex).digest()
    vertex_control[0x20:0x30] = vertex_guid
    for control, code in ((vertex_control, vertex), (fragment_control, fragment)):
        if struct.unpack_from("<I", control, 0x30)[0] != len(control):
            raise SystemExit("shader control length field is inconsistent")
        if struct.unpack_from("<I", control, 0x44)[0] != len(code):
            raise SystemExit("shader code length does not match its control metadata")

    files = {
        "fragment.control.bin": fragment_control,
        "vertex.control.bin": vertex_control,
        "fragment.code.bin": fragment,
        "vertex.code.bin": vertex,
    }
    for filename, data in files.items():
        (output / filename).write_bytes(data)

    # This layout matches the existing consumer: control data remains CPU
    # resident, while shader code sections begin on 0x800-byte boundaries.
    offsets = (0x10, 0x100, 0x800, 0x1800)
    packed = bytearray(0x3000)
    struct.pack_into("<4I", packed, 0, *offsets)
    for offset, data in zip(offsets, files.values()):
        packed[offset:offset + len(data)] = data
    (output / "imgui-native.bin").write_bytes(packed)

    jobs = [
        {
            "key": "native-imgui-vertex", "stage": "vs", "arch": "sm86",
            "code": "vertex.code.bin", "c1": "", "tex": {"0": "2d"},
            "attr": {"0": "float", "1": "float", "2": "float"}, "debug": False,
        },
        {
            "key": "native-imgui-fragment", "stage": "ps", "arch": "sm86",
            "code": "fragment.code.bin", "c1": "", "tex": {"0": "2d"},
            "fout": {"0": "float"}, "debug": False,
        },
    ]
    (output / "translate-jobs.json").write_text(json.dumps(jobs, indent=2) + "\n")

    manifest = {
        "source": "user-supplied variant 29 UI2D shader files",
        "source_vertex_sha256": sha256(original_vertex),
        "source_fragment_sha256": sha256(fragment),
        "output_sha256": sha256(packed),
        "output_size": len(packed),
        "offsets": dict(zip(("fragment_control", "vertex_control", "fragment_code", "vertex_code"), offsets)),
        "patches": patches,
        "required_renderer_adaptation": [
            "Supply vertex cbuf0 with the native UI2D matrices and UV flags.",
            "Supply fragment cbuf0 with the RGBA multiplier and additive values.",
            "Keep the 20-byte ImDrawVert layout: position0, UV1, and RGBA-UNORM8 attribute2.",
        ],
        "translation_verified": False,
        "native_sdk_acceptance_verified": False,
        "hardware_validated": False,
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Wrote adapted shader to {output}")


if __name__ == "__main__":
    main()
