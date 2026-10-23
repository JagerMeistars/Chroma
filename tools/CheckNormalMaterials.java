import java.nio.*;
import java.nio.file.*;
import java.util.regex.*;
import org.lwjgl.BufferUtils;
import org.lwjgl.opengl.GL;
import static org.lwjgl.glfw.GLFW.*;
import static org.lwjgl.opengl.GL33C.*;

/** Render the real material decoder and normal transport in a hidden GL context. */
public class CheckNormalMaterials {
    static String include(Path root, String name) throws Exception {
        String source = Files.readString(root.resolve("assets/chroma/shaders/include/" + name));
        Matcher matcher = Pattern.compile("#include <chroma:([^>]+)>").matcher(source);
        StringBuffer out = new StringBuffer();
        while (matcher.find()) matcher.appendReplacement(out, Matcher.quoteReplacement(include(root, matcher.group(1))));
        matcher.appendTail(out);
        return out.toString();
    }
    static int shader(int type, String source) {
        int s = glCreateShader(type); glShaderSource(s, source); glCompileShader(s);
        if (glGetShaderi(s, GL_COMPILE_STATUS) == 0) throw new AssertionError(glGetShaderInfoLog(s));
        return s;
    }
    static byte[] texture(int code) {
        byte[] data = new byte[64];
        for (int p = 0; p < 16; p++) {
            data[p*4] = 24; data[p*4+1] = 112; data[p*4+2] = (byte)201; data[p*4+3] = (byte)255;
        }
        for (int q = 0; q < 4; q++) {
            int corner = (code >> (q*2)) & 3;
            int x = (q%2)*2 + corner%2, y = (q/2)*2 + corner/2;
            data[(y*4+x)*4+3] = 0;
        }
        return data;
    }
    static void upload(byte[] data) { upload(data, 4); }
    static void upload(byte[] data, int size) {
        ByteBuffer bytes = BufferUtils.createByteBuffer(data.length); bytes.put(data).flip();
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA8, size, size, 0, GL_RGBA, GL_UNSIGNED_BYTE, bytes);
    }
    static float[] draw(int program, int mode, int rotation) {
        glUniform1i(glGetUniformLocation(program,"mode"),mode);
        glUniform1i(glGetUniformLocation(program,"rotation"),rotation);
        glDrawArrays(GL_TRIANGLES,0,3);
        FloatBuffer read = BufferUtils.createFloatBuffer(16*16*4);
        glReadPixels(0,0,16,16,GL_RGBA,GL_FLOAT,read);
        float[] values = new float[read.capacity()]; read.get(values);
        if (glGetError()!=GL_NO_ERROR) throw new AssertionError("GL error");
        return values;
    }
    static void close(float a, float b, float tolerance, String context) {
        if (!Float.isFinite(a) || Math.abs(a-b)>tolerance) throw new AssertionError(context+": "+a+" != "+b);
    }
    public static void main(String[] args) throws Exception {
        boolean normalsEnabled=args.length<2 || args[1].equals("1");
        if (!glfwInit()) throw new IllegalStateException("GLFW init failed");
        glfwWindowHint(GLFW_VISIBLE,GLFW_FALSE); glfwWindowHint(GLFW_FOCUSED,GLFW_FALSE);
        glfwWindowHint(GLFW_CONTEXT_VERSION_MAJOR,3); glfwWindowHint(GLFW_CONTEXT_VERSION_MINOR,3);
        glfwWindowHint(GLFW_OPENGL_PROFILE,GLFW_OPENGL_CORE_PROFILE);
        long window=glfwCreateWindow(16,16,"Chroma material regression",0,0);
        glfwMakeContextCurrent(window); GL.createCapabilities();
        String vertex = "#version 330\nout vec2 uv; out vec3 eye; uniform int rotation; void main(){"
            + "vec2 p=vec2((gl_VertexID<<1)&2,gl_VertexID&2); gl_Position=vec4(p*2.0-1.0,0.0,1.0);"
            + "eye=vec3(p*2.0-1.0,-3.0); uv=vec2(p.x,1.0-p.y);"
            + "if(rotation==1)uv=vec2(1.0-uv.y,uv.x); if(rotation==2)uv.x=1.0-uv.x;}";
        String fragment = "#version 330\n"+include(Path.of(args[0]),"normal_material.glsl")
            + "\nin vec2 uv; in vec3 eye; uniform sampler2D atlas; uniform int mode; uniform ivec2 phase; uniform vec2 sampleScale; uniform vec2 sampleOffset; out vec4 color;"
            + "void main(){vec2 texUV=uv*sampleScale+sampleOffset; ChromaMaterial m=mode==3?chromaSampleTerrainMaterial(atlas,texUV,texture(atlas,texUV),phase,false):chromaSampleMaterial(atlas,texUV,texture(atlas,texUV),phase);"
            + "float a=chromaMaterialAlpha(m,eye,texUV,mat3(1.0));"
            + "if(mode==0||mode==3)color=m.color; else if(mode==1)color=vec4(chromaDecodeMaterialNormal(a,vec3(0,0,1)),1);"
            + "else color=vec4(m.mapped?1.0:0.0,m.tangentNormal.xy,m.color.a);}";
        int p=glCreateProgram(); glAttachShader(p,shader(GL_VERTEX_SHADER,vertex));
        glAttachShader(p,shader(GL_FRAGMENT_SHADER,fragment)); glLinkProgram(p);
        if(glGetProgrami(p,GL_LINK_STATUS)==0)throw new AssertionError(glGetProgramInfoLog(p));
        int target=glGenTextures(); glBindTexture(GL_TEXTURE_2D,target);
        glTexImage2D(GL_TEXTURE_2D,0,GL_RGBA32F,16,16,0,GL_RGBA,GL_FLOAT,(ByteBuffer)null);
        int fbo=glGenFramebuffers(); glBindFramebuffer(GL_FRAMEBUFFER,fbo);
        glFramebufferTexture2D(GL_FRAMEBUFFER,GL_COLOR_ATTACHMENT0,GL_TEXTURE_2D,target,0);
        if(glCheckFramebufferStatus(GL_FRAMEBUFFER)!=GL_FRAMEBUFFER_COMPLETE)throw new AssertionError("FBO");
        glBindVertexArray(glGenVertexArrays()); glUseProgram(p); glViewport(0,0,16,16);
        glUniform2f(glGetUniformLocation(p,"sampleScale"),1,1);
        int input=glGenTextures(); glBindTexture(GL_TEXTURE_2D,input);
        glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MIN_FILTER,GL_NEAREST);
        glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MAG_FILTER,GL_NEAREST);
        glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_S,GL_CLAMP_TO_EDGE);
        glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_T,GL_CLAMP_TO_EDGE);
        int checked=0;
        for(int code=0;code<225;code++) {
            upload(texture(code)); float[] color=draw(p,0,0);
            for(int i=0;i<color.length;i+=4) {
                close(color[i],24f/255,1e-5f,"red"); close(color[i+1],112f/255,1e-5f,"green");
                close(color[i+2],201f/255,1e-5f,"blue"); close(color[i+3],1,1e-5f,"coverage");
            }
            for(int rotation=0;rotation<3;rotation++) {
                float x=(code%15-7)/7f,y=(code/15-7)/7f;
                if(rotation==1){float old=x;x=-y;y=old;} else if(rotation==2)x=-x;
                if(!normalsEnabled){x=0;y=0;}
                float length=(float)Math.sqrt(x*x+y*y+1);
                float[] normal=draw(p,1,rotation);
                for(int i=0;i<normal.length;i+=4){
                    close(normal[i],x/length,1e-5f,"normal x code="+code+" rotation="+rotation);
                    close(normal[i+1],y/length,1e-5f,"normal y"); close(normal[i+2],1/length,1e-5f,"normal z");
                }
                checked++;
            }
        }
        byte[] nativeData=texture(112);
        for(int a:new int[]{0,64,128,191,255}) {
            for(int i=3;i<nativeData.length;i+=4)nativeData[i]=(byte)a;
            upload(nativeData); float[] color=draw(p,0,0), mapped=draw(p,2,0);
            for(int i=0;i<color.length;i+=4){close(color[i+3],a/255f,1e-5f,"native alpha");close(mapped[i],0,1e-5f,"native flag");}
        }
        for(float t:new float[]{0,.1f,.25f,.49f,.51f,.75f,.9f,1}) {
            byte[] a=texture(31),b=texture(194);
            for(int i=3;i<a.length;i+=4)a[i]=(byte)Math.round((a[i]&255)*(1-t)+(b[i]&255)*t);
            upload(a);float[] mapped=draw(p,2,0);
            for(int i=0;i<mapped.length;i+=4){close(mapped[i],1,1e-5f,"animated flag");close(mapped[i+3],1,1e-5f,"animated alpha");}
        }
        // Atlas sprites can start at any phase: mip-zero chest/shulker/item
        // atlases add one pixel of padding and alternate phase 1/3.
        int phaseCases=0;
        glUniform2f(glGetUniformLocation(p,"sampleScale"),.25f,.25f);
        for(int py=0;py<4;py++)for(int px=0;px<4;px++)for(int code=0;code<225;code++) {
            byte[] atlas=new byte[16*16*4], tile=texture(code);
            for(int y=0;y<4;y++)for(int x=0;x<4;x++)
                System.arraycopy(tile,(y*4+x)*4,atlas,((y+4+py)*16+x+4+px)*4,4);
            upload(atlas,16);
            glUniform2i(glGetUniformLocation(p,"phase"),px,py);
            glUniform2f(glGetUniformLocation(p,"sampleOffset"),(4+px)/16f,(4+py)/16f);
            float[] color=draw(p,0,0), normal=draw(p,1,0);
            float x=(code%15-7)/7f,y=(code/15-7)/7f;
            if(!normalsEnabled){x=0;y=0;}
            float length=(float)Math.sqrt(x*x+y*y+1);
            for(int i=0;i<color.length;i+=4) {
                close(color[i],24f/255,1e-5f,"offset red");close(color[i+1],112f/255,1e-5f,"offset green");
                close(color[i+2],201f/255,1e-5f,"offset blue");close(color[i+3],1,1e-5f,"offset coverage");
                close(normal[i],x/length,1e-5f,"offset normal x");close(normal[i+1],y/length,1e-5f,"offset normal y");
                close(normal[i+2],1/length,1e-5f,"offset normal z");
            }
            phaseCases++;
        }
        glUniform2i(glGetUniformLocation(p,"phase"),0,0);
        int coverageFallbacks=0;
        for(int py=0;py<4;py++)for(int px=0;px<4;px++) {
            if(px==0&&py==0)continue;
            for(int code:new int[]{0,31,112,194,224}) {
                byte[] atlas=new byte[16*16*4],tile=texture(code);
                for(int y=0;y<4;y++)for(int x=0;x<4;x++)
                    System.arraycopy(tile,(y*4+x)*4,atlas,((y+4+py)*16+x+4+px)*4,4);
                upload(atlas,16);
                glUniform2f(glGetUniformLocation(p,"sampleOffset"),(4+px)/16f,(4+py)/16f);
                float[] values=draw(p,2,0);
                for(int i=0;i<values.length;i+=4) {
                    close(values[i],0,1e-5f,"coverage fallback must not invent a normal");
                    close(values[i+3],1,1e-5f,"coverage fallback opacity");
                }
                coverageFallbacks++;
            }
        }
        glUniform2f(glGetUniformLocation(p,"sampleScale"),1,1);
        glUniform2f(glGetUniformLocation(p,"sampleOffset"),0,0);
        // Minecraft item draws clamp the sampler to level zero even on an
        // atlas with allocated mips. Terrain reads decoded coverage explicitly.
        upload(texture(112)); glGenerateMipmap(GL_TEXTURE_2D);
        glTexParameterf(GL_TEXTURE_2D,GL_TEXTURE_MAX_LOD,0);
        glViewport(0,0,2,2);
        for(int mode:new int[]{0,3}) {
            float[] values=draw(p,mode,0);
            for(int y=0;y<2;y++)for(int x=0;x<2;x++)
                close(values[(y*16+x)*4+3],1,1e-5f,"sampler-clamped minified coverage mode="+mode);
        }
        System.out.println("NORMAL_GPU_PASS enabled="+normalsEnabled+" cases="+checked+" atlas_phase_cases="+phaseCases+" coverage_fallback_cases="+coverageFallbacks+" all_pixels=16x16 RGB=exact coverage=exact UV=normal,rotated,mirrored animation=pass minified_sampler_clamp=pass GPU="+glGetString(GL_RENDERER)+" gameplay=false");
        glfwDestroyWindow(window);glfwTerminate();
    }
}
