# Experimental ImGui NVN shader adapter for Switch 2

This repository contains a source-only experiment that adapts a Switch 2 NVN UI2D shader variant to read the RGBA color attribute used by the existing ImGui vertex layout.

It is **not a complete ImGui backend or a drop-in Switch 2 port**. The Switch 2 renderer, input handling, frame lifecycle, and on-console rendering path are not implemented here. The earlier `imgui_backend_v2` scaffold remains unfinished. This repository publishes the shader transformation tool only.

## What the tool does

`build_imgui_shader.py` takes four variant 29 shader files supplied by the user, updates the vertex input mask, replaces four constant-color instructions with scalar loads from attribute 2, and emits an NVN shader bundle plus translator job descriptions.

The tool does not include Nintendo game files or shader dumps. The four input files must be extracted from the user's own game copy:

- `var29-vertex.code.bin`
- `var29-vertex.control.bin`
- `var29-fragment.code.bin`
- `var29-fragment.control.bin`

Run it with Python 3.10 or newer:

```sh
python3 build_imgui_shader.py \
  --input-dir /path/to/your/variant-29-files \
  --output-dir ./build
```

The generated `imgui-native.bin` is a derivative of the input shader. Keep generated files local; this repository intentionally excludes game-derived inputs and outputs.

## Status and limitations

- The transformation has been checked in the original workbench with shader translation and CPU-side native SDK acceptance emulation.
- Physical Switch 2 GPU execution and visible rendering have **not** been verified.
- The emitted translator jobs are metadata; a compatible external shader translator is needed to process them.
- The matching renderer must provide the documented constant buffers and preserve the ImDrawVert attribute layout.
- The original Switch NVN backend is maintained separately in [Martmists-GH/switch-mods](https://github.com/Martmists-GH/switch-mods); that project credits CraftyBoss for its NVN ImGui backend. This repository does not copy that backend.

## Provenance

The transformation was isolated from a private Switch 2 modding workbench. This repository does not contain game captures, executable files, ROMFS assets, keys, or generated shader binaries. Dear ImGui, the upstream NVN backend, Nintendo SDK material, and game-derived shader inputs retain their respective rights and licenses.

No standalone license is included yet.
