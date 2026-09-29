# Chroma live benchmark instrumentation (Minecraft 26.3)

This test-only attach agent refuses every instance except `chroma-direct-audit-26.3`.
It is not part of the resource pack. It adds no lighting, render passes, entity data,
shaders or mod dependency. The test supervisor launches and attaches explicitly.

Build `bench-build.ps1`, then attach `bench-chroma.jar` using the existing
`AttachChromaProbe` launcher, passing a **separate** control directory. The existing
world/command bridge and this benchmark agent can coexist.

```powershell
python tools/live/bench-request.py audit/slotless/benchmark configure
python tools/live/bench-request.py audit/slotless/benchmark status
python tools/live/bench-request.py audit/slotless/benchmark select-packs --pack vanilla --pack file/Chroma
python tools/live/bench-request.py audit/slotless/benchmark measure --name baseline-32 --warmup 10 --seconds 20 --wait
```

`configure` requests a 1920 x 1080 native framebuffer, turns Vsync off, sets the
vanilla 260 FPS option (unlimited in this exact client), sets FOV 70 and render/simulation
distances 8/5, hides the HUD, and installs an invisible non-pausing input lock.
Read `status` after resize events: the actual main target must be 1920 x 1080.
Measurements refuse another resolution, a paused/absent world, a throttled window,
Vsync, a frame cap, or a missing input lock. Never minimize the test window.
The lock captures game input only; no keyboard/mouse events are synthesized.

Measurements wrap the existing `LocalSampleLogger` used by
`DebugScreenOverlay.logFrameDuration`. Exact client bytecode confirms that
`Minecraft.renderFrame` supplies the interval between consecutive completed frames,
after command submission, presentation and frame limiting. This includes whole-frame
stalls. All frame samples are retained, rather than polling the integer FPS counter.
The original logger still receives every sample. There is no synchronous GPU readback
or screenshot during timed windows. `detach` restores the original logger.

The supplementary `getFrameTimeNs` column is only the update/extract/render/blit CPU
segment before submission and presentation; it is not used to calculate FPS.
GPU timing queries are not enabled by this agent. Frame averages and percentiles
come from the completed-frame wall intervals. The 1% low metric is the reciprocal
of the average of the slowest 1% frame durations.

For comparisons use the same world, entities, camera, resolution, graphics settings,
input lock and background workload. Change only the selected pack, reload, verify
the scene outside the timed window, then allow ten seconds of warmup. Prefer paired
20-second baseline/prototype runs and repeat if a large outlier or scene change occurs.
The JSON contains initial/final camera/settings and links the raw CSV. Check these
states and invalid-frame count before interpreting a result. GPU/render load from
other active applications remains a limit of a desktop measurement; this instrument
does not control or terminate other processes.

`select-packs` uses the live repository and `reloadResourcePacks()` asynchronously;
wait for `status.reload` to become `complete` and verify the selected pack before
configuring the input lock and measuring. Every measurement name must be unique.
