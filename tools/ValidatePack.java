import java.nio.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;
import java.util.zip.*;
import com.google.gson.*;
import com.mojang.serialization.JsonOps;
import com.mojang.renderpearl.api.pipeline.ShaderSource.CachedIncludeSource;
import com.mojang.renderpearl.api.pipeline.ShaderType;
import com.mojang.renderpearl.frontend.shaders.SPIRVModule;
import net.minecraft.resources.Identifier;
import net.minecraft.client.renderer.PostChainConfig;
import net.minecraft.client.renderer.RenderPipelines;
import net.minecraft.server.packs.metadata.pack.PackFormat;
import net.minecraft.server.packs.PackType;
import org.lwjgl.util.shaderc.*;
import static org.lwjgl.util.shaderc.Shaderc.*;
import static org.lwjgl.system.MemoryUtil.*;

public class ValidatePack {
    static ZipFile pack, vanilla;
    static Map<String, CachedIncludeSource> includes = new HashMap<>();
    static Map<String, Set<String>> samplers = new HashMap<>();
    static int failures = 0;
    static String read(String path) throws Exception {
        ZipFile z = pack.getEntry(path) != null ? pack : vanilla;
        var entry = z.getEntry(path);
        if (entry == null) throw new IllegalArgumentException("Missing resource: " + path);
        return new String(z.getInputStream(entry).readAllBytes(), StandardCharsets.UTF_8);
    }
    static String shaderPath(String id, String ext) {
        var i = Identifier.parse(id);
        return "assets/" + i.getNamespace() + "/shaders/" + i.getPath() + ext;
    }
    static void fail(String text) { failures++; System.out.println("FAIL " + text); }
    public static void main(String[] args) throws Exception {
        pack = new ZipFile(args[0]); vanilla = new ZipFile(args[1]);
        long compiler = shaderc_compiler_initialize();
        long options = shaderc_compile_options_initialize();
        // These settings match 26.3 GlslCompiler.createBaseShaderOptions().
        // Both Minecraft render backends compile GLSL to Vulkan 1.2 SPIR-V first.
        shaderc_compile_options_set_target_env(options, shaderc_target_env_vulkan, shaderc_env_version_vulkan_1_2);
        shaderc_compile_options_set_auto_bind_uniforms(options, true);
        shaderc_compile_options_set_preserve_bindings(options, false);
        shaderc_compile_options_set_generate_debug_info(options);
        shaderc_compile_options_set_optimization_level(options, shaderc_optimization_level_zero);
        ShadercIncludeResolve resolver = ShadercIncludeResolve.create((u, name, type, source, depth) -> {
            String id = memUTF8(name);
            return includes.computeIfAbsent(id, key -> {
                try {
                    Identifier i = Identifier.parse(key);
                    return CachedIncludeSource.create(i, read("assets/" + i.getNamespace() + "/shaders/include/" + i.getPath()));
                } catch (Exception e) { return CachedIncludeSource.createError(e.toString()); }
            }).includeResultPtr();
        });
        ShadercIncludeResultRelease release = ShadercIncludeResultRelease.create((u, result) -> {});
        shaderc_compile_options_set_include_callbacks(options, resolver, release, 0);
        Set<String> shaderPaths = new TreeSet<>();
        List<Map.Entry<String, JsonObject>> configs = new ArrayList<>();
        var entries = pack.entries();
        while (entries.hasMoreElements()) {
            String path = entries.nextElement().getName();
            if (path.endsWith(".fsh") || path.endsWith(".vsh")) shaderPaths.add(path);
            if (path.contains("/post_effect/") && path.endsWith(".json")) {
                JsonObject json = JsonParser.parseString(read(path)).getAsJsonObject();
                configs.add(Map.entry(path, json));
                var decoded = PostChainConfig.CODEC.parse(JsonOps.INSTANCE, json);
                if (decoded.error().isPresent()) fail(path + ": " + decoded.error().get());
                for (var elem : json.getAsJsonArray("passes")) {
                    var pass = elem.getAsJsonObject();
                    shaderPaths.add(shaderPath(pass.get("vertex_shader").getAsString(), ".vsh"));
                    shaderPaths.add(shaderPath(pass.get("fragment_shader").getAsString(), ".fsh"));
                }
            }
        }
        System.out.println("POST_CHAIN_JSONS " + configs.size());
        var metadata = PackFormat.packCodec(PackType.CLIENT_RESOURCES).codec().parse(JsonOps.INSTANCE, JsonParser.parseString(read("pack.mcmeta")).getAsJsonObject().get("pack"));
        if (metadata.error().isPresent()) fail("pack.mcmeta: " + metadata.error().get());
        else System.out.println("PACK_FORMAT " + metadata.result().get());
        int compiled = 0;
        for (String path : shaderPaths) {
            boolean vertex = path.endsWith(".vsh");
            long stageOptions = options;
            // This native shader exists only as an OIT pipeline. Its wavelet
            // declarations require the installed pipeline's actual defines.
            if (path.equals("assets/minecraft/shaders/core/oit_composite.fsh")) {
                stageOptions = shaderc_compile_options_clone(options);
                final long oitOptions = stageOptions;
                var defines = RenderPipelines.OIT_COMPOSITE.getShaderDefines();
                defines.values().forEach((k,v) -> shaderc_compile_options_add_macro_definition(oitOptions,k,v));
                defines.flags().forEach(k -> shaderc_compile_options_add_macro_definition(oitOptions,k,""));
            }
            long result = shaderc_compile_into_spv(compiler, read(path), vertex ? shaderc_vertex_shader : shaderc_fragment_shader, path, "main", stageOptions);
            if (shaderc_result_get_compilation_status(result) != shaderc_compilation_status_success) {
                fail(path + "\n" + shaderc_result_get_error_message(result));
            } else {
                compiled++;
                ByteBuffer bytes = shaderc_result_get_bytes(result);
                ByteBuffer copy = memAlloc(bytes.remaining()); copy.put(bytes).flip();
                try (SPIRVModule module = new SPIRVModule(copy, vertex ? ShaderType.VERTEX : ShaderType.FRAGMENT)) {
                    var reflect = module.reflect();
                    Set<String> required = new TreeSet<>();
                    for (var descriptor : reflect.descriptors())
                        if (descriptor.name().endsWith("Sampler")) required.add(descriptor.name());
                    samplers.put(path, required);
                    System.out.println("COMPILED " + path + " SAMPLERS " + required);
                }
            }
            shaderc_result_release(result);
            if (stageOptions != options) shaderc_compile_options_release(stageOptions);
        }
        int terrainVariants = 0;
        for (String[] defines : List.of(new String[]{"ALPHA_CUTOUT=0.5"}, new String[]{"ALPHA_CUTOUT=0.5", "MULTIDRAW_TERRAIN"}, new String[]{"ALPHA_CUTOUT=0.1"}, new String[]{"ALPHA_CUTOUT=0.1", "MULTIDRAW_TERRAIN"}, new String[]{"ALPHA_CUTOUT=0.1", "OIT_ALPHA_ONLY"}, new String[]{"ALPHA_CUTOUT=0.1", "OIT_ALPHA_ONLY", "MULTIDRAW_TERRAIN"})) {
            String path = "assets/minecraft/shaders/core/terrain.vsh";
            if (pack.getEntry(path) == null) continue;
            long variantOptions = shaderc_compile_options_clone(options);
            for (String define : defines) { String[] parts=define.split("="); shaderc_compile_options_add_macro_definition(variantOptions, parts[0], parts.length>1?parts[1]:"1"); }
            long result = shaderc_compile_into_spv(compiler, read(path), shaderc_vertex_shader, path, "main", variantOptions);
            if (shaderc_result_get_compilation_status(result) != shaderc_compilation_status_success) fail(path + Arrays.toString(defines) + "\n" + shaderc_result_get_error_message(result));
            else {terrainVariants++;System.out.println("TERRAIN_VARIANT " + Arrays.toString(defines) + " PASS");}
            shaderc_result_release(result);shaderc_compile_options_release(variantOptions);
        }
        for (var entry : configs) {
            Set<String> targets = new HashSet<>(entry.getValue().getAsJsonObject("targets").keySet());
            targets.add("minecraft:main");
            for (var elem : entry.getValue().getAsJsonArray("passes")) {
                var pass = elem.getAsJsonObject();
                String shader = shaderPath(pass.get("fragment_shader").getAsString(), ".fsh");
                String vertexShader = shaderPath(pass.get("vertex_shader").getAsString(), ".vsh");
                Set<String> bound = new TreeSet<>();
                for (var inp : pass.getAsJsonArray("inputs")) {
                    var input = inp.getAsJsonObject();
                    bound.add(input.get("sampler_name").getAsString() + "Sampler");
                    if (input.has("target") && !targets.contains(input.get("target").getAsString())) fail(entry.getKey() + " missing input target " + input.get("target"));
                }
                if (!targets.contains(pass.get("output").getAsString())) fail(entry.getKey() + " missing output target");
                Set<String> required = new TreeSet<>(samplers.getOrDefault(shader, Set.of()));
                required.addAll(samplers.getOrDefault(vertexShader, Set.of()));
                if (!bound.containsAll(required)) {
                    Set<String> missing = new TreeSet<>(required); missing.removeAll(bound);
                    fail(entry.getKey() + " unbound vertex/fragment samplers " + missing);
                }
            }
        }
        includes.values().forEach(CachedIncludeSource::close);
        resolver.close(); release.close();
        shaderc_compile_options_release(options); shaderc_compiler_release(compiler);
        pack.close(); vanilla.close();
        System.out.println("SUMMARY shaders=" + shaderPaths.size() + " compiled=" + compiled + " terrain_variants=" + terrainVariants + " effects=" + configs.size() + " failures=" + failures);
        System.exit(failures == 0 ? 0 : 1);
    }
}
