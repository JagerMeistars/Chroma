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
                glDeleteProgram(p); glDeleteShader(v); glDeleteShader(f);
                count++;
            }
        }
        glfwDestroyWindow(window); glfwTerminate();
        if (count == 0) throw new IllegalStateException("No programs checked");
        System.out.println("DRIVER_LINK programs=" + count + " failures=0 client_gameplay=false");
    }
}
