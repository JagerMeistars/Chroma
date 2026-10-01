import com.google.gson.JsonParser;
import com.mojang.blaze3d.systems.RenderSystem;
import com.mojang.renderpearl.api.commands.CommandEncoder;
import com.mojang.renderpearl.api.commands.GpuQueryPool;
import com.mojang.renderpearl.api.commands.RenderPass;
import com.mojang.renderpearl.api.commands.RenderPassDescriptor;
import com.mojang.renderpearl.api.device.GpuDevice;
import java.lang.instrument.Instrumentation;
import java.lang.reflect.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.time.Instant;
import java.util.*;
import java.util.concurrent.*;
import java.util.function.*;
import net.minecraft.client.Minecraft;
import net.minecraft.resources.Identifier;

/** Temporary vanilla-audit instrumentation. Never use with Sodium/Axiom or the user's main instance. */
public final class gpu_ChromaPassTiming {
    static final String PROPERTY = "chroma.gpu.pass.timing.agent";
    static final int PAIRS = 1024, MAX_SAMPLES = 100000, MAX_POLLS = 256;
    static final StackWalker CALLER = StackWalker.getInstance(StackWalker.Option.RETAIN_CLASS_REFERENCE);
    static Minecraft mc;
    static Path directory;
    static Field deviceField;
    static volatile boolean running;
    static Session session;

    static void verify() throws Exception {
        Path actual = mc.gameDirectory.getCanonicalFile().toPath();
        Path expected = Path.of(System.getProperty("user.home"), "AppData", "Roaming", "PrismLauncher",
                "instances", "chroma-direct-audit-26.3", "minecraft").toFile().getCanonicalFile().toPath();
        if (!actual.equals(expected)) throw new SecurityException("Refusing non-isolated game directory: " + actual);
        try {
            Class.forName("net.fabricmc.loader.api.FabricLoader", false, mc.getClass().getClassLoader());
            throw new SecurityException("Interface proxy is deliberately unsupported under Fabric/modded Minecraft");
        } catch (ClassNotFoundException expectedVanilla) { }
    }

    static Object onThread(Callable<Object> action) throws Exception {
        CompletableFuture<Object> result = new CompletableFuture<>();
        mc.execute(() -> { try { result.complete(action.call()); } catch (Throwable e) { result.completeExceptionally(e); } });
        return result.get(30, TimeUnit.SECONDS);
    }

    static Object invoke(Object target, Method method, Object[] args) throws Throwable {
        try { return method.invoke(target, args); }
        catch (InvocationTargetException error) { throw error.getCause(); }
    }

    @SuppressWarnings("unchecked")
    static <T> T proxy(Class<T> type, InvocationHandler handler) {
        return (T) Proxy.newProxyInstance(type.getClassLoader(), new Class<?>[]{type}, handler);
    }

    static String label(Object[] args) {
        Object first = args[0];
        Supplier<?> supplier = first instanceof RenderPassDescriptor d ? d.label() : (Supplier<?>) first;
        return supplier == null ? "" : String.valueOf(supplier.get());
    }

    static boolean isPostPassCaller() {
        // Only PostPass keeps this encoder local and uses it solely to create its
        // render pass. Minecraft presentation requires the ORIGINAL concrete
        // FrontendCommandEncoder, so it must never see our interface proxy.
        return CALLER.walk(frames -> frames.dropWhile(frame -> {
            Class<?> type = frame.getDeclaringClass();
            return type == gpu_ChromaPassTiming.class || type == Session.class || Proxy.isProxyClass(type);
        }).findFirst().map(frame -> frame.getClassName().equals("net.minecraft.client.renderer.PostPass")).orElse(false));
    }

    static Map<String, String> activeLabels() throws Exception {
        var resource = mc.getResourceManager().getResource(Identifier.fromNamespaceAndPath("minecraft", "post_effect/end_of_frame.json")).orElseThrow();
        Map<String, String> labels = new LinkedHashMap<>();
        try (var reader = resource.openAsReader()) {
            var passes = JsonParser.parseReader(reader).getAsJsonObject().getAsJsonArray("passes");
            for (int i = 0; i < passes.size(); i++) {
                String shader = passes.get(i).getAsJsonObject().get("fragment_shader").getAsString();
                if (shader.startsWith("chroma:")) labels.put("Post pass minecraft:end_of_frame/" + i, shader);
            }
        }
        if (labels.isEmpty()) throw new IllegalStateException("Active end_of_frame has no Chroma fragment shaders");
        return labels;
    }

    public static void agentmain(String argument, Instrumentation ignored) throws Exception {
        mc = Minecraft.getInstance(); verify();
        directory = Path.of(argument).toAbsolutePath().normalize(); Files.createDirectories(directory);
        if (System.getProperties().putIfAbsent(PROPERTY, directory.toString()) != null)
            throw new IllegalStateException("GPU pass timing agent already attached");
        try {
            deviceField = RenderSystem.class.getDeclaredField("DEVICE"); deviceField.setAccessible(true);
            if (deviceField.getType() != GpuDevice.class || Modifier.isFinal(deviceField.getModifiers()))
                throw new IllegalStateException("Unexpected RenderSystem.DEVICE contract");
            running = true;
            write(directory.resolve("ready.json"), Map.of("ok", true, "pid", ProcessHandle.current().pid(),
                    "gameDirectory", mc.gameDirectory.getCanonicalPath(), "deviceModified", false,
                    "method", "Native GPU timestamp pairs around selected render passes; no GPU wait, frame setting changes, or resource-pack changes"));
            Thread worker = new Thread(gpu_ChromaPassTiming::work, "Chroma isolated GPU pass timing");
            worker.setDaemon(true); worker.start();
        } catch (Throwable error) { System.getProperties().remove(PROPERTY); throw error; }
    }

    static void work() {
        try {
            while (running) {
                onThread(() -> { if (session != null) session.maintain(); return null; });
                if (session != null && session.complete && !session.saved) { save(session); session.saved = true; }
                try (var stream = Files.list(directory)) {
                    for (Path path : stream.filter(p -> p.getFileName().toString().endsWith(".req")).sorted().toList()) {
                        String contents = Files.readString(path, StandardCharsets.UTF_8);
                        Files.move(path, Path.of(path + ".running"));
                        try { write(Path.of(path + ".done"), onThread(() -> request(contents))); }
                        catch (Throwable error) { write(Path.of(path + ".done"), Map.of("ok", false, "error", error.toString())); }
                    }
                }
                Thread.sleep(100);
            }
        } catch (Throwable error) {
            try { onThread(() -> { if (session != null) { session.fail(error); session.finish(); } return null; }); }
            catch (Throwable restoreError) { error.addSuppressed(restoreError); }
            try { write(directory.resolve("worker-error.json"), Map.of("ok", false, "error", error.toString())); }
            catch (Exception ignored) { }
        } finally { System.getProperties().remove(PROPERTY); }
    }

    static Object request(String text) throws Exception {
        verify(); String[] args = text.split("\\R");
        if (args[0].equals("status")) return session == null ? Map.of("ok", true, "state", "idle") : session.status();
        if (args[0].equals("stop")) {
            if (session != null) session.stop("requested");
            return Map.of("ok", true, "state", "draining", "deviceRestored", session == null || session.restored);
        }
        if (args[0].equals("detach")) {
            if (session != null && !session.saved) throw new IllegalStateException("Stop and wait for saved result before detach");
            running = false; return Map.of("ok", true, "deviceRestored", session == null || session.restored);
        }
        if (!args[0].equals("measure")) throw new IllegalArgumentException("Expected status, measure, stop, or detach");
        if (session != null && !session.saved) throw new IllegalStateException("Previous capture is still recording/draining/saving");
        String name = args[1]; double warmup = Double.parseDouble(args[2]), seconds = Double.parseDouble(args[3]);
        if (args.length > 4) throw new IllegalArgumentException("Only Chroma PostPass timing is supported; native OIT/presentation timing is not intercepted");
        if (!name.matches("[a-zA-Z0-9_-]+") || !Double.isFinite(warmup) || !Double.isFinite(seconds)
                || warmup < 0 || warmup > 30 || seconds < 1 || seconds > 30) throw new IllegalArgumentException("Unique safe name, warmup 0-30, duration 1-30 seconds required");
        if (Files.exists(directory.resolve(name + ".json"))) throw new IllegalArgumentException("Result already exists");
        if (mc.level == null || mc.isPaused()) throw new IllegalStateException("Unpaused loaded audit world required");
        GpuDevice original = RenderSystem.getDevice();
        if (!original.getClass().getName().equals("com.mojang.renderpearl.frontend.FrontendGpuDevice"))
            throw new IllegalStateException("Unexpected or already-wrapped device: " + original.getClass().getName());
        Map<String, String> labels = activeLabels();
        double period = original.getDeviceInfo().timestampPeriod();
        if (!Double.isFinite(period) || period <= 0) throw new IllegalStateException("No positive timestamp period");
        Session next = new Session(name, original, original.createTimestampQueryPool(PAIRS * 2), labels,
                period, warmup, seconds, System::nanoTime);
        next.restore = () -> {
            try {
                Object current = deviceField.get(null);
                if (current == next.device) deviceField.set(null, original);
                else if (current != original) throw new IllegalStateException("Device replaced by another actor; refusing to overwrite");
                next.restored = true;
            } catch (ReflectiveOperationException error) { throw new IllegalStateException(error); }
        };
        try {
            next.initial = Map.of("resourcePacks", List.copyOf(mc.options.resourcePacks),
                    "deviceInfo", original.getDeviceInfo().toString(), "width", mc.gameRenderer.mainRenderTarget().width,
                    "height", mc.gameRenderer.mainRenderTarget().height, "bobView", mc.options.bobView().get(),
                    "nativeEntityShadows", mc.options.entityShadows().get());
            deviceField.set(null, next.device); session = next;
        }
        catch (Throwable error) { next.pool.close(); throw error; }
        return Map.of("ok", true, "output", directory.resolve(name + ".json").toString(), "labels", labels,
                "warmupSeconds", warmup, "sampleSeconds", seconds, "scope", "Chroma PostPass only");
    }

    static final class Sample {
        final int pair; final long submit, cpuNs; final String label, stage; boolean ended;
        double gpuNs;
        Sample(int pair, long submit, long cpuNs, String label, String stage) {
            this.pair = pair; this.submit = submit; this.cpuNs = cpuNs; this.label = label; this.stage = stage;
        }
    }

    static final class Session {
        final String name, startedUtc = Instant.now().toString();
        final GpuDevice original, device; final GpuQueryPool pool; final double period, warmup, seconds;
        final Map<String, String> labels; final String firstLabel; final LongSupplier clock;
        BooleanSupplier callerAllowed = gpu_ChromaPassTiming::isPostPassCaller;
        final ArrayDeque<Integer> free = new ArrayDeque<>(); final ArrayDeque<Sample> pending = new ArrayDeque<>();
        final ArrayList<Sample> samples = new ArrayList<>(); final IdentityHashMap<CommandEncoder, CommandEncoder> encoders = new IdentityHashMap<>();
        final long start, end; long submit, dropped, stopTime; String reason = "", error;
        boolean accepting = true, restored, poolClosed; volatile boolean complete, saved;
        Map<String, Object> initial = Map.of(); Runnable restore = () -> { };

        Session(String name, GpuDevice original, GpuQueryPool pool, Map<String, String> labels,
                double period, double warmup, double seconds, LongSupplier clock) {
            this.name = name; this.original = original; this.pool = pool; this.labels = Map.copyOf(labels);
            firstLabel = labels.keySet().iterator().next();
            this.period = period; this.warmup = warmup; this.seconds = seconds; this.clock = clock;
            start = clock.getAsLong() + (long) (warmup * 1e9); end = start + (long) (seconds * 1e9);
            for (int i = 0; i < pool.size() / 2; i++) free.add(i);
            device = proxy(GpuDevice.class, (p, method, args) -> {
                if (method.getName().equals("close")) { stop("native-device-close"); finish(); }
                Object result;
                try { result = invoke(original, method, args); }
                catch (Throwable error) { fail(error); throw error; }
                if (method.getName().equals("createCommandEncoder") && accepting && callerAllowed.getAsBoolean())
                    return encoders.computeIfAbsent((CommandEncoder) result, this::wrapEncoder);
                return result;
            });
        }

        CommandEncoder wrapEncoder(CommandEncoder originalEncoder) {
            return proxy(CommandEncoder.class, (p, method, args) -> {
                if (method.getName().equals("createRenderPass") && accepting) {
                    Sample sample = null;
                    try { sample = begin(originalEncoder, label(args)); } catch (Throwable error) { fail(error); }
                    Object pass;
                    try { pass = invoke(originalEncoder, method, args); }
                    catch (Throwable error) { fail(error); throw error; }
                    if (sample == null) return pass;
                    Sample ticket = sample;
                    return proxy(RenderPass.class, (rp, passMethod, passArgs) -> {
                        Object result;
                        try { result = invoke(pass, passMethod, passArgs); }
                        catch (Throwable error) { fail(error); throw error; }
                        if (passMethod.getName().equals("close") && !ticket.ended && !poolClosed) {
                            try { originalEncoder.writeTimestamp(pool, ticket.pair * 2 + 1); ticket.ended = true; }
                            catch (Throwable error) { fail(error); }
                        }
                        return result;
                    });
                }
                Object result;
                try { result = invoke(originalEncoder, method, args); }
                catch (Throwable error) { fail(error); throw error; }
                return result;
            });
        }

        Sample begin(CommandEncoder encoder, String label) {
            // The native frame-submit caller receives the unwrapped encoder.
            // Poll older results at the next chain start, never by intercepting
            // presentation. Group IDs denote chain starts, not native submits.
            if (label.equals(firstLabel)) { submit++; maintain(); }
            long now = clock.getAsLong();
            if (!accepting || now < start) return null;
            if (now >= end) { stop("duration"); return null; }
            String stage = labels.get(label);
            if (stage == null) return null;
            if (samples.size() + pending.size() >= MAX_SAMPLES) { stop("sample-capacity"); return null; }
            if (free.isEmpty()) { dropped++; return null; }
            int pair = free.remove(); Sample sample = new Sample(pair, submit, now - start, label, stage);
            pending.add(sample); encoder.writeTimestamp(pool, pair * 2); return sample;
        }

        void poll() {
            for (int i = 0; i < MAX_POLLS && !pending.isEmpty(); i++) {
                Sample sample = pending.peek(); if (!sample.ended) return;
                // Native GL checks QUERY_RESULT_AVAILABLE; Vulkan uses availability, without WAIT.
                // Retire a pair only after BOTH results are present; never reset an in-flight slot.
                OptionalLong[] values = pool.getValues(sample.pair * 2, 2);
                if (values[0].isEmpty() || values[1].isEmpty()) return;
                long ticks = values[1].getAsLong() - values[0].getAsLong();
                if (ticks < 0) { fail(new IllegalStateException("Non-monotonic GPU timestamp")); return; }
                sample.gpuNs = ticks * period; pending.remove(); free.add(sample.pair); samples.add(sample);
            }
        }

        void maintain() {
            if (complete) return;
            if (accepting && clock.getAsLong() >= end) stop("duration");
            poll();
            if (!accepting && (pending.isEmpty() || clock.getAsLong() - stopTime >= 5_000_000_000L)) finish();
        }
        void stop(String why) {
            if (!accepting) return;
            accepting = false; reason = why; stopTime = clock.getAsLong(); restore.run();
        }
        void fail(Throwable failure) {
            if (error == null) error = failure.toString();
            try { stop("error"); } catch (Throwable restoreError) { error += "; restore: " + restoreError; }
        }
        void finish() {
            if (complete) return;
            if (accepting) stop("finished");
            // Native GL deletes query names; Vulkan queues destruction behind submitted work. No wait.
            if (!poolClosed) { pool.close(); poolClosed = true; }
            complete = true;
        }
        Map<String, Object> status() {
            var out = new LinkedHashMap<String, Object>(); out.put("ok", error == null); out.put("name", name);
            out.put("state", complete ? (saved ? "saved" : "saving") : accepting ? "recording" : "draining");
            out.put("samples", samples.size()); out.put("pending", pending.size()); out.put("dropped", dropped);
            out.put("deviceRestored", restored); out.put("poolClosed", poolClosed); out.put("reason", reason);
            if (error != null) out.put("error", error); return out;
        }
    }

    static void save(Session s) throws Exception {
        Map<String, ArrayList<Double>> byPass = new TreeMap<>();
        try (var csv = Files.newBufferedWriter(directory.resolve(s.name + ".csv"), StandardCharsets.UTF_8)) {
            csv.write("post_chain_group,cpu_start_ns,gpu_ns,stage,label\n");
            for (Sample sample : s.samples) {
                csv.write(sample.submit + "," + sample.cpuNs + "," + sample.gpuNs + "," + csv(sample.stage) + "," + csv(sample.label) + "\n");
                byPass.computeIfAbsent(sample.label, k -> new ArrayList<>()).add(sample.gpuNs / 1e6);
            }
        }
        var summaries = new LinkedHashMap<String, Object>();
        for (var entry : byPass.entrySet()) {
            var v = entry.getValue(); v.sort(Double::compare);
            summaries.put(entry.getKey(), Map.of("stage", s.labels.getOrDefault(entry.getKey(), "native:" + entry.getKey()),
                    "count", v.size(), "meanMs", v.stream().mapToDouble(Double::doubleValue).average().orElse(0),
                    "medianMs", v.get((v.size() - 1) / 2), "p95Ms", v.get((int) Math.ceil((v.size() - 1) * .95)), "maxMs", v.get(v.size() - 1)));
        }
        var out = new LinkedHashMap<String, Object>(s.status());
        out.put("state", "saved");
        out.put("ok", s.error == null && s.restored && s.pending.isEmpty() && s.dropped == 0 && !s.samples.isEmpty());
        out.put("startedUtc", s.startedUtc); out.put("warmupSeconds", s.warmup); out.put("sampleSeconds", s.seconds);
        out.put("timestampPeriodNs", s.period); out.put("initialState", s.initial); out.put("passes", summaries);
        out.put("method", "GPU timestamp pairs immediately before createRenderPass and after close, resolved asynchronously at subsequent Chroma chain starts and between frames. Only the direct native PostPass caller receives a timed encoder; native presentation receives its original concrete encoder. Includes pass attachment work. No GPU completion wait or pixel readback.");
        out.put("limits", "Instrumented diagnostic, not uninstrumented FPS. Post-chain groups need not equal displayed frames. Only Chroma PostPass is intercepted; native OIT/presentation is not measured. Passes are selected from active end_of_frame at start: do not reload packs mid-capture. World-filter and entity-screen work share the shade pass and require separate controls to distinguish them.");
        out.put("csv", directory.resolve(s.name + ".csv").toString()); write(directory.resolve(s.name + ".json"), out);
    }

    static String csv(String s) { return "\"" + s.replace("\"", "\"\"") + "\""; }
    static String json(Object value) {
        if (value == null) return "null";
        if (value instanceof Number || value instanceof Boolean) return value.toString();
        if (value instanceof Map<?, ?> m) { var a = new ArrayList<String>(); m.forEach((k, v) -> a.add(json(k.toString()) + ":" + json(v))); return "{" + String.join(",", a) + "}"; }
        if (value instanceof Iterable<?> list) { var a = new ArrayList<String>(); list.forEach(v -> a.add(json(v))); return "[" + String.join(",", a) + "]"; }
        StringBuilder s = new StringBuilder("\"");
        for (char c : value.toString().toCharArray()) switch (c) {
            case '\\' -> s.append("\\\\"); case '"' -> s.append("\\\""); case '\n' -> s.append("\\n"); case '\r' -> s.append("\\r"); case '\t' -> s.append("\\t");
            default -> { if (c < 32) s.append(String.format("\\u%04x", (int) c)); else s.append(c); }
        }
        return s.append('"').toString();
    }
    static void write(Path path, Object value) throws Exception { Files.writeString(path, json(value) + "\n", StandardCharsets.UTF_8); }
}
