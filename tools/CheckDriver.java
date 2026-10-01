import java.nio.file.*;
import java.util.*;
import java.util.regex.*;
import org.lwjgl.opengl.GL;
import static org.lwjgl.glfw.GLFW.*;
import static org.lwjgl.opengl.GL33C.*;

/** Compile and link the native client's translated shader variants on the GPU. */
public class CheckDriver {
    static String normalizeBlockNames(String source) {
        // This harness translates stages independently, before Minecraft remaps
        // descriptor bindings for an entire pipeline. Auto-numbered block names
        // therefore alias unrelated blocks across stages. Match blocks by their
        // complete member declaration so linking tests the actual shader interface.
        Matcher m = Pattern.compile("(layout\\(std140\\) uniform )\\w+(\\s*\\{([^}]+)\\})").matcher(source);
        StringBuffer out = new StringBuffer();
        while (m.find()) {
            String signature = m.group(3).replaceAll("\\s+", "");
            String name = "ChromaBlock_" + Integer.toUnsignedString(signature.hashCode(), 16);
            m.appendReplacement(out, Matcher.quoteReplacement(m.group(1) + name + m.group(2)));
        }
        m.appendTail(out);
        return out.toString();
    }
    static int compile(int type, String text) {
        int shader = glCreateShader(type);
        glShaderSource(shader, normalizeBlockNames(text));
        glCompileShader(shader);
        if (glGetShaderi(shader, GL_COMPILE_STATUS) == 0)
            throw new IllegalStateException(glGetShaderInfoLog(shader));
        return shader;
    }
    static void checkRaster(int vertex, int expected, String name) {
        int fragment = compile(GL_FRAGMENT_SHADER,
            "#version 330 core\nlayout(location=0) out vec4 color; void main(){color=vec4(1.0);}");
        int program = glCreateProgram();
        glAttachShader(program, vertex); glAttachShader(program, fragment); glLinkProgram(program);
        if (glGetProgrami(program, GL_LINK_STATUS) == 0)
            throw new IllegalStateException(glGetProgramInfoLog(program));
        int vao = glGenVertexArrays(), query = glGenQueries();
        glBindVertexArray(vao); glUseProgram(program); glViewport(0, 0, 32, 32);
        glBeginQuery(GL_SAMPLES_PASSED, query);
        glDrawArrays(GL_TRIANGLES, 0, 3);
        glEndQuery(GL_SAMPLES_PASSED);
        int samples = glGetQueryObjecti(query, GL_QUERY_RESULT);
        int error = glGetError();
        if (error != GL_NO_ERROR || samples != expected)
            throw new AssertionError(name + " raster samples=" + samples + " expected=" + expected + " GL error=" + error);
        glUseProgram(0); glDeleteQueries(query); glDeleteVertexArrays(vao);
        glDeleteProgram(program); glDeleteShader(fragment);
    }
    public static void main(String[] args) throws Exception {
        if (!glfwInit()) throw new IllegalStateException("GLFW init failed");
        glfwWindowHint(GLFW_VISIBLE, GLFW_FALSE);
        glfwWindowHint(GLFW_FOCUSED, GLFW_FALSE);
        glfwWindowHint(GLFW_CONTEXT_VERSION_MAJOR, 3);
        glfwWindowHint(GLFW_CONTEXT_VERSION_MINOR, 3);
        glfwWindowHint(GLFW_OPENGL_PROFILE, GLFW_OPENGL_CORE_PROFILE);
        long window = glfwCreateWindow(32, 32, "Chroma offline shader check", 0, 0);
        if (window == 0) throw new IllegalStateException("Hidden GL context failed");
        glfwMakeContextCurrent(window);
        GL.createCapabilities();
        int count = 0;
        int rasterChecks = 0;
        Set<String> shadowPasses = args.length > 1
            ? new HashSet<>(Arrays.asList(args[2].split(","))) : Set.of();
        boolean shadowsEnabled = args.length > 1 && args[1].equals("1");
        System.out.println("GPU " + glGetString(GL_RENDERER) + " " + glGetString(GL_VERSION));
        try (var paths = Files.list(Path.of(args[0]))) {
            for (Path vertex : paths.sorted().toList()) {
                if (!vertex.toString().endsWith(".vsh")) continue;
                Path fragment = Path.of(vertex.toString().replaceFirst("\\.vsh$", ".fsh"));
                int v = compile(GL_VERTEX_SHADER, Files.readString(vertex));
                int f = compile(GL_FRAGMENT_SHADER, Files.readString(fragment));
                int p = glCreateProgram();
                glAttachShader(p, v); glAttachShader(p, f); glLinkProgram(p);
                if (glGetProgrami(p, GL_LINK_STATUS) == 0)
                    throw new IllegalStateException(vertex + ": " + glGetProgramInfoLog(p));
                String name = vertex.getFileName().toString();
                if (shadowPasses.contains(name)) {
                    checkRaster(v, shadowsEnabled ? 1024 : 0, name);
                    rasterChecks++;
                }
                if (args.length > 1 && name.equals(args[3])) {
                    // Lighting must still rasterize; disabled shadows must not
                    // retain any active shadow/cache texture reads in its program.
                    checkRaster(v, 1024, name);
                    rasterChecks++;
                    if (!shadowsEnabled) {
                        for (int i = 0; i < glGetProgrami(p, GL_ACTIVE_UNIFORMS); ++i) {
                            String uniform = glGetActiveUniformName(p, i, 512);
                            if (uniform.contains("ShadowSampler") || uniform.contains("SurfaceSampler")
                                    || uniform.contains("VoxelSampler") || uniform.contains("VoxelLod1Sampler"))
                                throw new AssertionError("Disabled shade still uses " + uniform);
                        }
                    }
                }
                glDeleteProgram(p); glDeleteShader(v); glDeleteShader(f);
                count++;
            }
        }
        glfwDestroyWindow(window); glfwTerminate();
        if (count == 0) throw new IllegalStateException("No programs checked");
        System.out.println("DRIVER_LINK programs=" + count + " failures=0 client_gameplay=false");
        if (args.length > 1) {
            if (rasterChecks != shadowPasses.size() + 1)
                throw new AssertionError("Missing shadow raster checks");
            System.out.println("SHADOW_RASTER enabled=" + shadowsEnabled + " passes=" + shadowPasses.size()
                + " shadow_samples=" + (shadowsEnabled ? 1024 : 0) + " lighting_samples=1024 failures=0");
        }
    }
}
