# Development checks

These tools are excluded from the resource-pack ZIP. The pack itself requires no
Java agent, mod, script or datapack.

1. `python tools/check_assets.py --source PATH_TO_RPDREVO` validates resources,
   marker encoding, the automatic post chain and the saved source hash manifest.
2. `python tools/check_native.py` compiles with the installed Minecraft 26.3
   shaderc/SPIR-V pipeline, translates the actual core/post variants, links them
   on a hidden local OpenGL context, and parses the documented commands with
   Minecraft's command/NBT codecs. It does not launch the game or measure FPS.
3. `python tools/build.py` writes the Auto ZIP on `main`; on the shadow branch it
   dispatches to `build_shadows.py` and preserves the Auto release.
4. `python tools/check_shadow_math.py`, `python tools/check_voxel_space.py` and
   `python tools/check_voxel_geometry.py` check the CPU geometry references,
   world-anchored pixel sampling and packed storage. They do not execute GLSL.

`generate_pack.py` regenerates only the five primary marker models, their legacy
aliases, ten marker textures, atlas, transport helpers and native core hooks from
the installed client JAR, including terrain's camera-header guard. It preserves
the lighting shaders and post chain.
Use `--output PATH` to compare regenerated files before replacing them.

The real-client functional audit is a historical 32-source helper at `live/verify_slotless.py --run`; it does not test the current 128-source build. It needs the
prepared isolated Chroma instance and explicitly attached test bridges described
in [live/README.md](live/README.md) and [live/bench-README.md](live/bench-README.md).
It refuses an active benchmark and restores its scene after checking all 32
individual contributions, five shapes, coincident lights and camera/address
changes. Do not run it against a user's normal world.

Final live reports are in `audit/slotless/functional-verification.json`,
`audit/slotless/edge-verification.json` and `audit/slotless/benchmark/results`.
The previous slotted renderer's synthetic tests are preserved with its backup
under `audit/slotless/previous-root/tools`; they do not test this transport ABI.
