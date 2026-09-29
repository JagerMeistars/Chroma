import java.nio.file.*;
import java.util.*;
import java.util.zip.*;
import com.google.gson.*;
import com.mojang.renderpearl.api.pipeline.*;
import com.mojang.renderpearl.backend.api.*;
import com.mojang.renderpearl.backend.opengl.GlPipelineRecompiler;
import com.mojang.renderpearl.frontend.shaders.GlslCompiler;
import net.minecraft.client.renderer.RenderPipelines;
import net.minecraft.resources.Identifier;
import com.mojang.renderpearl.frontend.shaders.SPIRVModule;
import static org.lwjgl.util.shaderc.Shaderc.*;
import static org.lwjgl.system.MemoryUtil.*;
import org.lwjgl.util.shaderc.*;
import static org.lwjgl.util.spvc.Spvc.*;
import org.lwjgl.system.MemoryStack;

/** Uses the exact native GLSL -> SPIR-V -> OpenGL GLSL path, without starting the game. */
public class ReproduceClientShaders extends ValidatePack {
 static int constantBroadcasts(SpvModule module){
  var words=module.spv().asIntBuffer();var constants=new HashSet<Integer>();var indices=new ArrayList<Integer>();
  for(int i=5;i<words.limit();){int instruction=words.get(i),count=instruction>>>16,op=instruction&65535;
   if(count==0)throw new AssertionError("Invalid SPIR-V instruction");
   if(op==43||op==46)constants.add(words.get(i+2));
   if(op==337)indices.add(words.get(i+5));
   i+=count;
  }
  for(int index:indices)if(!constants.contains(index))throw new AssertionError("Non-constant broadcast lane: "+index);
  return indices.size();
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
  pack=new ZipFile(args[0]);vanilla=new ZipFile(args[1]);
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
  int count=0,broadcasts=0;
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
    if(pipeline.getShaders().entrySet().stream().noneMatch(e->pack.getEntry(shaderPath(e.getValue().toString(),e.getKey()==ShaderType.VERTEX?".vsh":".fsh"))!=null))continue;
    for(var stage:pipeline.getShaders().entrySet()){
     String name=pipeline.getLocation().toString().replace(':','_').replace('/','_')+(stage.getKey()==ShaderType.VERTEX?".vsh":".fsh");
     long options=shaderc_compile_options_clone(base);
     pipeline.getShaderDefines().values().forEach((k,v)->shaderc_compile_options_add_macro_definition(options,k,v));
     pipeline.getShaderDefines().flags().forEach(k->shaderc_compile_options_add_macro_definition(options,k,""));
     long result=shaderc_compile_into_spv(compiler,source.getShader(stage.getValue(),stage.getKey()),stage.getKey()==ShaderType.VERTEX?shaderc_vertex_shader:shaderc_fragment_shader,stage.getValue().toString(),"main",options);
     if(shaderc_result_get_compilation_status(result)!=shaderc_compilation_status_success)throw new RuntimeException(shaderc_result_get_error_message(result));
     var bytes=shaderc_result_get_bytes(result);var copy=memAlloc(bytes.remaining());copy.put(bytes).flip();
     try(var module=new SPIRVModule(copy,stage.getKey())){
      if(args[2].contains("final"))broadcasts+=constantBroadcasts(module);
      String glsl=(String)method.invoke(recompiler,new BackendRenderPipeline.CreateInfo.Shader(stage.getValue().toString(),"main",module));
      Files.writeString(out.resolve(name),glsl);
      if(!glsl.startsWith("#version")){diagnose(module,name);fail("Native OpenGL translation failed: "+name);}
      count++;
     }
     shaderc_result_release(result);shaderc_compile_options_release(options);
    }
   }
  }
  // Post shaders must pass the actual OpenGL GLSL330 translator and driver,
  // not only Shaderc. Some SPIR-V operations (e.g. bitCount) are valid input
  // but are not exposed by the generated GLSL330 extension set.
  int postPairs=0;
  var postEntries=pack.entries();
  while(postEntries.hasMoreElements()){
   String path=postEntries.nextElement().getName();
   if(!path.contains("/post_effect/")||!path.endsWith(".json"))continue;
   JsonObject config=JsonParser.parseString(read(path)).getAsJsonObject();
   for(var element:config.getAsJsonArray("passes")){
    var pass=element.getAsJsonObject();
    for(var type:List.of(ShaderType.VERTEX,ShaderType.FRAGMENT)){
     boolean vertex=type==ShaderType.VERTEX;
     Identifier id=Identifier.parse(pass.get(vertex?"vertex_shader":"fragment_shader").getAsString());
     String name=String.format("post_pass_%03d",postPairs)+(vertex?".vsh":".fsh");
     long result=shaderc_compile_into_spv(compiler,source.getShader(id,type),vertex?shaderc_vertex_shader:shaderc_fragment_shader,id.toString(),"main",base);
     if(shaderc_result_get_compilation_status(result)!=shaderc_compilation_status_success)throw new RuntimeException(shaderc_result_get_error_message(result));
     var bytes=shaderc_result_get_bytes(result);var copy=memAlloc(bytes.remaining());copy.put(bytes).flip();
     try(var module=new SPIRVModule(copy,type)){
      String glsl=(String)method.invoke(recompiler,new BackendRenderPipeline.CreateInfo.Shader(id.toString(),"main",module));
      Files.writeString(out.resolve(name),glsl);
      if(!glsl.startsWith("#version")){diagnose(module,name);fail("Native OpenGL post translation failed: "+name);}
      count++;
     }
     shaderc_result_release(result);
    }
    postPairs++;
   }
  }
  System.out.println("NATIVE_POST_PAIRS "+postPairs);
  resolver.close();release.close();shaderc_compile_options_release(base);shaderc_compiler_release(compiler);
  source.close();pack.close();vanilla.close();
  System.out.println("NATIVE_ROUNDTRIP stages="+count+" failures="+failures+" constant_broadcasts="+broadcasts+" output="+out);
  System.exit(failures==0?0:1);
 }
}
