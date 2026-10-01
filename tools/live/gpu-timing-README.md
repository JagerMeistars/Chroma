# GPU pass timing — isolated audit only

`gpu-chroma-pass-timing.jar` temporarily wraps Minecraft 26.3's `GpuDevice` and only the command encoders requested directly by `PostPass`, plus selected render passes. Presentation and every other caller receive the original concrete encoder; the existing final window surface is unchanged. It only accepts the existing **vanilla** `chroma-direct-audit-26.3/minecraft` directory and refuses Fabric. Do not attach it to the user's main instance: Sodium/Axiom have concrete-device assumptions.

Build and run CPU fakes (no game, attachment, context, or GPU work):

```powershell
python -B tools/live/build_gpu_timing.py
```

The tester can attach the resulting JAR with the existing `AttachChromaProbe` helper, passing a **new, separate control directory** as the agent argument. Attachment alone does not replace the device. Then:

```powershell
python tools/live/gpu-timing-request.py <control-directory> measure --name horse-near --warmup 2 --seconds 5 --wait
python tools/live/gpu-timing-request.py <control-directory> status
python tools/live/gpu-timing-request.py <control-directory> detach
```

`stop` restores the original device immediately and drains outstanding queries asynchronously. Duration expiry/error also restores it. `detach` requires the result to have saved. No game, pack, bob, native shadow, FPS, or camera settings are changed. Do not reload packs during a capture. Only Chroma post passes are measured; native OIT/presentation timing is unsupported.

The active end-of-frame JSON maps actual native labels (`Post pass minecraft:end_of_frame/N`) to Chroma fragment shaders. Two native timestamps surround pass creation/close, including attachment work. Results are polled without GPU waits or texture readback at subsequent Chroma chain starts and between frames. There are 1,024 reusable query pairs, at most 256 pairs read per poll, 100,000 samples, a maximum 30-second capture, and a 5-second drain timeout. In-flight pairs are never reused. Dropped/unresolved/error samples make the report unsuccessful. CSV retains individual durations and post-chain groups; JSON reports per-pass mean/median/p95/max milliseconds, settings, restoration, and query status.

This is an **instrumented GPU diagnostic**, not an FPS benchmark. Post-chain groups are inferred from the first selected pass and need not equal displayed frames. Both world filtering and screen entity contact shadows run inside `shade`; a separate mode comparison is needed to split them. GPU timestamps cannot isolate CPU submission, game simulation, or mod overhead. The proxy, queries, and polling add overhead; compare the same scene and use the existing uninstrumented benchmark for FPS.

A CPU test reproduces the real `FrontendGpuSurface` concrete-encoder rejection with fake backend objects, then verifies that the original encoder passes presentation unchanged. Additional CPU fakes verify native-call order/delegation, shader-label selection, timestamp conversion, asynchronous availability, capacity/timeout bounds, original-exception propagation, restoration callbacks, and warmup. The native interface/query implementations were inspected, but compilation and fake tests alone do **not** prove live timing correctness or overhead. No live attach was performed by the build script.

The first live diagnostic attempt crashed the owned vanilla client at `FrontendGpuSurface.blitFromTexture` because the former broad proxy escaped to presentation; it produced **no valid GPU timing result**. The narrowed version avoids that boundary and passes the CPU native-surface regression, but requires a one-second live smoke before longer captures. Primary/modded instances remain refused.
