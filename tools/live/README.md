# Direct vanilla client audit helper

This is an optional local test helper, excluded from the resource pack. It attaches through the standard Java diagnostic API, invokes vanilla client and integrated-server methods, and reads existing GPU targets. It does not patch classes, shaders, or rendering behavior. Only `PrismLauncher/instances/chroma-direct-audit-26.3/minecraft` is accepted; every request checks that directory.

Build with `build.ps1`, then attach `chroma-live-probe.jar` using `AttachChromaProbe NEW_PID ABSOLUTE_JAR_PATH ABSOLUTE_CONTROL_DIRECTORY`. The control directory receives `ready.json` with the confirmed PID and game directory. Check both before issuing commands.

Use `request.py CONTROL_DIRECTORY OPERATION [--argument TEXT | --file FILE]`. Supported operations:

- `open --argument Chroma-Audit`: open the isolated saved world.
- `status`: actual player position, loaded level, FPS, selected resource packs, applied post effects, and reload state.
- `commands --file commands.txt`: run newline-separated vanilla commands on the integrated server. Each result includes parsed errors, feedback, and engine callbacks. Inspect these rather than relying only on the outer `ok` flag.
- `configure`: hide HUD, stop tutorial, disable camera bob, entity shadows, VSync and pause on lost focus, and cap rendering at 120 FPS.
- `capture`: invoke Minecraft's own screenshot API; output appears in the isolated instance's screenshots folder.
- `dump --argument LABEL`: read actual OpenGL main color/depth and persistent end-of-frame targets. Raw buffers, color PNGs and `manifest.json` are saved under `CONTROL_DIRECTORY/captures/LABEL`. Buffers use bottom-up OpenGL orientation; PNGs are flipped for display. Depth is little-endian float32; color is RGBA8. Existing GL state is restored after reading.
- `reload` and `reload-status`: asynchronously reload resource packs and inspect completion.
- `close-screen`, `detach`, and `exit`: close the current screen, stop only the API worker, or ask this isolated client to shut down.

`dispatcher` is a low-level diagnostic operation. Use `commands` for normal command execution because Minecraft 26.3 uses its execution context for commands such as `execute`.
