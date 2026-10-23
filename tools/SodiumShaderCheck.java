import java.nio.file.*;
import java.util.*;
import java.util.zip.*;
import com.mojang.renderpearl.api.pipeline.*;
import com.mojang.renderpearl.backend.api.*;
import com.mojang.renderpearl.backend.opengl.GlPipelineRecompiler;
import net.minecraft.client.renderer.RenderPipelines;
import net.minecraft.resources.Identifier;
import com.mojang.renderpearl.frontend.shaders.SPIRVModule;
import static org.lwjgl.util.shaderc.Shaderc.*;
import static org.lwjgl.system.MemoryUtil.*;
import org.lwjgl.util.shaderc.*;
import static org.lwjgl.util.spvc.Spvc.*;
import org.lwjgl.system.MemoryStack;

/** Native MC 26.3 terrain variants with Sodium 0.9.3's defines and includes.
 * Uses GLSL -> SPIR-V -> OpenGL GLSL, without starting the game. */
public class SodiumShaderCheck extends ValidatePack {
 static ZipFile sodium;
 static String read(String path) throws Exception {
  if(pack.getEntry(path)!=null) return new String(pack.getInputStream(pack.getEntry(path)).readAllBytes(), java.nio.charset.StandardCharsets.UTF_8);
  if(sodium.getEntry(path)!=null) return new String(sodium.getInputStream(sodium.getEntry(path)).readAllBytes(), java.nio.charset.StandardCharsets.UTF_8);
  if(vanilla.getEntry(path)!=null) return new String(vanilla.getInputStream(vanilla.getEntry(path)).readAllBytes(), java.nio.charset.StandardCharsets.UTF_8);
  throw new IllegalArgumentException("Missing shader resource: "+path);
 }

 static void diagnose(SpvModule module,String name){
  try(var stack=MemoryStack.stackPush()){
   var ptr=stack.callocPointer(1);spvc_context_create(ptr);long ctx=ptr.get(0);
   try{
    var words=module.spv().asIntBuffer();spvc_context_parse_spirv(ctx,words,words.remaining(),ptr);
    long ir=ptr.get(0);spvc_context_create_compiler(ctx,SPVC_BACKEND_GLSL,ir,SPVC_CAPTURE_MODE_COPY,ptr);long cc=ptr.get(0);
    spvc_compiler_create_compiler_options(cc,ptr);long opts=ptr.get(0);
    spvc_compiler_options_set_uint(opts,SPVC_COMPILER_OPTION_GLSL_VERSION,330);
    spvc_compiler_options_set_bool(opts,SPVC_COMPILER_OPTION_GLSL_ES,false);
    spvc_compiler_install_compiler_options(cc,opts);
    int status=spvc_compiler_compile(cc,ptr);
    System.out.println("CROSS_DIAG "+name+" status="+status+" error="+spvc_context_get_last_error_string(ctx));
   }finally{spvc_context_destroy(ctx);}
  }
 }
 public static void main(String[] args) throws Exception {
  pack=new ZipFile(args[0]);vanilla=new ZipFile(args[1]);sodium=new ZipFile(args[3]);
  Path out=Path.of(args[2]);Files.createDirectories(out);
  ShaderSource source=new ShaderSource(){
   public String getShader(Identifier id,ShaderType type){
    try{return read(shaderPath(id.toString(),type==ShaderType.VERTEX?".vsh":".fsh"));}catch(Exception e){throw new RuntimeException(e);}
   }
   public CachedIncludeSource getInclude(Identifier id){
    return includes.computeIfAbsent(id.toString(),key->{try{return CachedIncludeSource.create(id,read("assets/"+id.getNamespace()+"/shaders/include/"+id.getPath()));}catch(Exception e){return CachedIncludeSource.createError(e.toString());}});
   }
   public void close(){includes.values().forEach(CachedIncludeSource::close);}
  };
  var method=GlPipelineRecompiler.class.getDeclaredMethod("decompileShader",BackendRenderPipeline.CreateInfo.Shader.class);
  method.setAccessible(true);
  var recompiler=new GlPipelineRecompiler(null,true);
  var pipelines=new ArrayList<RenderPipeline>();pipelines.addAll(RenderPipelines.requiredPipelines());pipelines.addAll(RenderPipelines.optionalPipelines());
  int count=0;
  long compiler=shaderc_compiler_initialize(),base=shaderc_compile_options_initialize();
  shaderc_compile_options_set_target_env(base,shaderc_target_env_vulkan,shaderc_env_version_vulkan_1_2);
  shaderc_compile_options_set_auto_bind_uniforms(base,true);
  shaderc_compile_options_set_preserve_bindings(base,false);
  shaderc_compile_options_set_generate_debug_info(base);
  shaderc_compile_options_set_optimization_level(base,shaderc_optimization_level_zero);
  shaderc_compile_options_add_macro_definition(base,"RENDERPEARL_DEPTH_IS_ZERO_TO_ONE","");
  shaderc_compile_options_add_macro_definition(base,"RENDERPEARL_INSTANCE_INDEX_INCLUDES_BASE_INSTANCE","");
  ShadercIncludeResolve resolver=ShadercIncludeResolve.create((u,n,t,s,d)->source.getInclude(Identifier.parse(memASCII(n))).includeResultPtr());
  ShadercIncludeResultRelease release=ShadercIncludeResultRelease.create((u,r)->{});
  shaderc_compile_options_set_include_callbacks(base,resolver,release,0);
  {
   for(var pipeline:pipelines){
    if(!pipeline.getLocation().toString().endsWith("_terrain")) continue;
    System.out.println("VARIANT " + pipeline.getLocation() + " " + pipeline.getShaderDefines() + " Sodium alpha cutout: translucent/OIT=0.01, cutout=0.5");
    for(var stage:pipeline.getShaders().entrySet()){
     String name=pipeline.getLocation().toString().replace(':','_').replace('/','_')+(stage.getKey()==ShaderType.VERTEX?".vsh":".fsh");
     long options=shaderc_compile_options_clone(base);
     pipeline.getShaderDefines().values().forEach((k,v)->shaderc_compile_options_add_macro_definition(options,k, k.equals("ALPHA_CUTOUT") && !pipeline.getLocation().toString().contains("cutout_terrain") ? "0.01" : v));
     pipeline.getShaderDefines().flags().forEach(k->shaderc_compile_options_add_macro_definition(options,k,""));
     shaderc_compile_options_add_macro_definition(options,"USE_VERTEX_COMPRESSION","");
     shaderc_compile_options_add_macro_definition(options,"USE_FOG","");
     long result=shaderc_compile_into_spv(compiler,read("assets/sodium/shaders/blocks/block_layer_opaque"+(stage.getKey()==ShaderType.VERTEX?".vsh":".fsh")),stage.getKey()==ShaderType.VERTEX?shaderc_vertex_shader:shaderc_fragment_shader,stage.getValue().toString(),"main",options);
     if(shaderc_result_get_compilation_status(result)!=shaderc_compilation_status_success)throw new RuntimeException(shaderc_result_get_error_message(result));
     var bytes=shaderc_result_get_bytes(result);var copy=memAlloc(bytes.remaining());copy.put(bytes).flip();
     try(var module=new SPIRVModule(copy,stage.getKey())){
      String glsl=(String)method.invoke(recompiler,new BackendRenderPipeline.CreateInfo.Shader(stage.getValue().toString(),"main",module));
      Files.writeString(out.resolve(name),glsl);
      if(!glsl.startsWith("#version")){diagnose(module,name);throw new IllegalStateException("Native OpenGL translation failed: "+name);}
      count++;
     }
     shaderc_result_release(result);shaderc_compile_options_release(options);
    }
   }
  }
  if(count!=12)throw new AssertionError("Expected 12 Sodium stages, got "+count);
  System.out.println("SODIUM_NATIVE_STAGES="+count+" client_gameplay=false");
  source.close(); resolver.close(); release.close();
  shaderc_compile_options_release(base); shaderc_compiler_release(compiler);
  pack.close(); vanilla.close(); sodium.close();
 }
}
