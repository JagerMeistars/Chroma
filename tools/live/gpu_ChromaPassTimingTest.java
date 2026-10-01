import com.mojang.renderpearl.api.commands.*;
import com.mojang.renderpearl.api.device.GpuDevice;
import com.mojang.renderpearl.api.device.GpuSurface;
import com.mojang.renderpearl.api.GpuFormat;
import com.mojang.renderpearl.api.textures.*;
import com.mojang.renderpearl.backend.api.*;
import com.mojang.renderpearl.frontend.FrontendCommandEncoder;
import com.mojang.renderpearl.frontend.FrontendGpuSurface;
import java.util.*;
import java.util.function.Supplier;

/** CPU-only fakes: does not initialize RenderSystem, create a context, attach, or call native GPU code. */
public final class gpu_ChromaPassTimingTest {
    static void check(boolean value, String message) { if (!value) throw new AssertionError(message); }
    static final String LABEL = "Post pass minecraft:end_of_frame/7";
    static final class Pool implements GpuQueryPool {
        final OptionalLong[] values; final List<String> events; boolean closed;
        Pool(int size, List<String> events) { values = new OptionalLong[size]; Arrays.fill(values, OptionalLong.empty()); this.events = events; }
        public int size() { return values.length; }
        public OptionalLong getValue(int i) { return values[i]; }
        public OptionalLong[] getValues(int first, int count) { return Arrays.copyOfRange(values, first, first + count); }
        public void close() { closed = true; events.add("pool-close"); }
    }
    static final class Fixture {
        final List<String> events = new ArrayList<>(); final long[] time = {0}; final Pool pool = new Pool(4, events);
        final RuntimeException nativeError = new IllegalStateException("native draw failed");
        boolean drawFailure, timestampFailure, isPostPass = true; int restores;
        final RenderPass nativePass = gpu_ChromaPassTiming.proxy(RenderPass.class, (p, method, args) -> {
            events.add(method.getName()); if (drawFailure && method.getName().equals("draw")) throw nativeError; return null;
        });
        final CommandEncoder nativeEncoder = gpu_ChromaPassTiming.proxy(CommandEncoder.class, (p, method, args) -> {
            if (method.getName().equals("createRenderPass")) { events.add("create"); return nativePass; }
            if (method.getName().equals("writeTimestamp")) {
                if (timestampFailure) throw new IllegalStateException("query unsupported");
                int i = (Integer) args[1]; events.add("timestamp-" + i); pool.values[i] = OptionalLong.empty();
            }
            if (method.getName().equals("submit")) events.add("submit"); return null;
        });
        final GpuDevice original = gpu_ChromaPassTiming.proxy(GpuDevice.class, (p, method, args) -> {
            if (method.getName().equals("createCommandEncoder")) return nativeEncoder; return null;
        });
        final gpu_ChromaPassTiming.Session session = new gpu_ChromaPassTiming.Session("cpu", original, pool,
                Map.of(LABEL, "chroma:post/voxel_update"), 2.0, 0, 10, () -> time[0]);
        Fixture() { session.restore = () -> { restores++; session.restored = true; }; session.callerAllowed = () -> isPostPass; }
        RenderPass pass(String label) { return session.device.createCommandEncoder().createRenderPass((Supplier<String>) () -> label, null, Optional.empty()); }
    }

    static void surfaceContract() throws Exception {
        List<String> events = new ArrayList<>();
        CommandEncoderBackend backend = gpu_ChromaPassTiming.proxy(CommandEncoderBackend.class, (p, m, a) -> null);
        FrontendCommandEncoder encoder = new FrontendCommandEncoder(null, null, backend);
        boolean[] allowed = {false};
        GpuDevice device = gpu_ChromaPassTiming.proxy(GpuDevice.class, (p, m, a) -> encoder);
        var session = new gpu_ChromaPassTiming.Session("surface", device, new Pool(4, events), Map.of(LABEL, "chroma:post/shade"), 1, 0, 10, () -> 0);
        session.callerAllowed = () -> allowed[0];
        check(session.device.createCommandEncoder() == encoder, "presentation receives original concrete encoder");
        allowed[0] = true;
        CommandEncoder timed = session.device.createCommandEncoder();
        check(timed != encoder, "PostPass receives timed encoder");
        check(!gpu_ChromaPassTiming.isPostPassCaller(), "ordinary test caller must not pass the native caller gate");
        GpuSurfaceBackend surfaceBackend = gpu_ChromaPassTiming.proxy(GpuSurfaceBackend.class, (p, m, a) -> {
            if (m.getName().equals("supportedPresentModes")) return List.of(GpuSurface.PresentMode.IMMEDIATE);
            if (m.getName().equals("blitFromTexture")) { check(a[0] == backend, "native surface gets original backend"); events.add("blit"); }
            return null;
        });
        FrontendGpuSurface surface = new FrontendGpuSurface(surfaceBackend);
        GpuTexture texture = gpu_ChromaPassTiming.proxy(GpuTexture.class, (p, m, a) -> switch (m.getName()) {
            case "getFormat" -> GpuFormat.RGBA8_UNORM; case "usage" -> 2; case "getDepthOrLayers" -> 1; default -> null;
        });
        GpuTextureView view = gpu_ChromaPassTiming.proxy(GpuTextureView.class, (p, m, a) -> texture);
        // Reproduce the actual native rejection without native GL/Vulkan code.
        try { surface.blitFromTexture(timed, view); throw new AssertionError("native surface should reject a proxy encoder"); }
        catch (IllegalArgumentException expected) { check(expected.getMessage().contains("FrontendCommandEncoder"), "actual concrete-class guard"); }
        surface.configure(new GpuSurface.Configuration(1, 1, GpuSurface.PresentMode.IMMEDIATE));
        surface.acquireNextTexture(); allowed[0] = false;
        surface.blitFromTexture(session.device.createCommandEncoder(), view);
        check(events.equals(List.of("blit")), "fixed presentation reaches native backend unchanged");
    }

    public static void main(String[] args) throws Exception {
        surfaceContract();
        Fixture f = new Fixture();
        check(f.session.device.createCommandEncoder() == f.session.device.createCommandEncoder(), "encoder proxy identity");
        check(f.pass("terrain") == f.nativePass && f.session.pending.isEmpty(), "unselected pass untouched"); f.events.clear();
        try (RenderPass pass = f.pass(LABEL)) { pass.draw(3, 1, 0, 0); }
        check(f.events.equals(List.of("timestamp-0", "create", "draw", "close", "timestamp-1")), "native call order " + f.events);
        f.session.poll(); check(f.session.samples.isEmpty() && f.session.pending.size() == 1, "unavailable result must not block or retire");
        f.pool.values[0] = OptionalLong.of(100); f.session.poll(); check(f.session.pending.size() == 1, "both results required");
        f.pool.values[1] = OptionalLong.of(130); f.session.poll(); check(f.session.samples.get(0).gpuNs == 60, "native timestamp period conversion");
        f.pass(LABEL).close(); f.pass(LABEL).close();
        int eventCount = f.events.size(); f.pass(LABEL).close();
        check(f.session.dropped == 1 && f.session.pending.size() == 2, "bounded query capacity");
        check(f.events.subList(eventCount, f.events.size()).equals(List.of("create", "close")), "exhaustion does not overwrite unresolved query");
        f.time[0] = 10_000_000_000L; f.session.maintain();
        check(f.restores == 1 && !f.session.accepting && !f.pool.closed, "duration restores before asynchronous drain");
        f.time[0] += 5_000_000_000L; f.session.maintain(); check(f.pool.closed && f.session.complete, "bounded drain timeout closes pool");

        Fixture g = new Fixture(); g.drawFailure = true;
        try (RenderPass pass = g.pass(LABEL)) { pass.draw(3, 1, 0, 0); throw new AssertionError("expected native failure"); }
        catch (RuntimeException error) { check(error == g.nativeError, "underlying exception identity preserved"); }
        check(g.restores == 1 && g.session.error != null && g.events.contains("close"), "native error restores and still closes pass");

        Fixture h = new Fixture(); h.timestampFailure = true;
        check(h.pass(LABEL) == h.nativePass, "instrumentation failure still delegates native create");
        check(h.restores == 1 && !h.session.accepting, "instrumentation failure restores device");
        Fixture i = new Fixture(); i.time[0] = -1; i.pass(LABEL).close();
        check(i.session.pending.isEmpty(), "warmup does not emit timestamps");
        i.session.stop("requested"); i.session.maintain();
        check(i.pool.closed && i.session.complete && i.restores == 1, "empty stop closes once");
        System.out.println("PASS CPU-only pass timing: real FrontendGpuSurface rejection/regression, caller gate, labels, delegation, order, period, nonblocking availability, bounded ring/drain, native failure, restoration, warmup");
    }
}
