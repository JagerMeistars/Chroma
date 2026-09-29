import java.lang.instrument.Instrumentation;
import java.lang.reflect.*;
import java.nio.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;
import java.util.concurrent.*;
import java.util.function.Consumer;

/** Request-file API audit agent. Refuses every game directory except the isolated Chroma audit instance. */
public class ChromaLiveProbe {
  static Object mc;static Class<?> mcType;static ClassLoader loader;static Path directory,gameDirectory;
  static volatile boolean running=true;
  static volatile String reloadState="not_requested";
  static Object field(Object target,String name)throws Exception{for(Class<?> c=target.getClass();c!=null;c=c.getSuperclass())try{Field f=c.getDeclaredField(name);f.setAccessible(true);return f.get(target);}catch(NoSuchFieldException e){}throw new NoSuchFieldException(name);}
  static void option(Object options,String name,Object value)throws Exception{Object o=call(options,name);o.getClass().getMethod("set",Object.class).invoke(o,value);}
  static Object call(Object target,String name)throws Exception{return target.getClass().getMethod(name).invoke(target);}
  static Method method(Class<?> type,String name,int count){return Arrays.stream(type.getMethods()).filter(m->m.getName().equals(name)&&m.getParameterCount()==count).findFirst().orElseThrow();}
  static Class<?> type(String name)throws Exception{return Class.forName(name,true,loader);}
  static void schedule(Object target,Runnable action)throws Exception{target.getClass().getMethod("execute",Runnable.class).invoke(target,action);}
  static Throwable cause(Throwable t){while(t instanceof InvocationTargetException&&t.getCause()!=null)t=t.getCause();return t;}
  static String quote(String text){var b=new StringBuilder("\"");for(char c:text.toCharArray())switch(c){case'"'->b.append("\\\"");case'\\'->b.append("\\\\");case'\n'->b.append("\\n");case'\r'->b.append("\\r");case'\t'->b.append("\\t");default->{if(c<32)b.append(String.format("\\u%04x",(int)c));else b.append(c);}}return b.append('"').toString();}
  static String json(Object value){
    if(value==null)return"null";if(value instanceof String s)return quote(s);if(value instanceof Number||value instanceof Boolean)return value.toString();
    if(value instanceof Map<?,?> map){var a=new ArrayList<String>();map.forEach((k,v)->a.add(quote(String.valueOf(k))+":"+json(v)));return"{"+String.join(",",a)+"}";}
    if(value instanceof Iterable<?> list){var a=new ArrayList<String>();list.forEach(v->a.add(json(v)));return"["+String.join(",",a)+"]";}return quote(value.toString());
  }
  static void write(Path path,Object value)throws Exception{Files.writeString(path,json(value)+"\n",StandardCharsets.UTF_8);}
  static Object onThread(Object target,Callable<Object> action)throws Exception{
    var future=new CompletableFuture<Object>();schedule(target,()->{try{future.complete(action.call());}catch(Throwable t){future.completeExceptionally(cause(t));}});
    return future.get(30,TimeUnit.SECONDS);
  }
  static void verifyGameDirectory()throws Exception{
    gameDirectory=((java.io.File)mcType.getField("gameDirectory").get(mc)).getCanonicalFile().toPath();
    Path instances=Path.of(System.getProperty("user.home"),"AppData","Roaming","PrismLauncher","instances");
    boolean allowed=false;
    for(String name:List.of("chroma-direct-audit-26.3"))
      if(gameDirectory.equals(instances.resolve(name).resolve("minecraft").toFile().getCanonicalFile().toPath()))allowed=true;
    if(!allowed)throw new SecurityException("Refusing non-isolated gameDirectory: "+gameDirectory);
  }
  public static void agentmain(String argument,Instrumentation instrumentation)throws Exception{
    mcType=Arrays.stream(instrumentation.getAllLoadedClasses()).filter(c->c.getName().equals("net.minecraft.client.Minecraft")).findFirst().orElseThrow();
    loader=mcType.getClassLoader();mc=mcType.getMethod("getInstance").invoke(null);verifyGameDirectory();
    directory=Path.of(argument).toAbsolutePath().normalize();Files.createDirectories(directory);
    if(System.getProperties().putIfAbsent("chroma.live.agent",directory.toString())!=null)throw new IllegalStateException("ChromaLiveProbe already attached");
    write(directory.resolve("ready.json"),Map.of("pid",ProcessHandle.current().pid(),"gameDirectory",gameDirectory.toString(),"mode","API requests; no world opened yet by this agent"));
    var worker=new Thread(()->{while(running){try{
      try(var stream=Files.list(directory)){for(Path request:stream.filter(p->p.getFileName().toString().endsWith(".req")).sorted().toList()){
        String content=Files.readString(request,StandardCharsets.UTF_8);Path work=Path.of(request+".running"),done=Path.of(request+".done");Files.move(request,work);
        try{write(done,run(content));}catch(Throwable t){var e=cause(t);write(done,Map.of("ok",false,"exception",e.getClass().getName(),"error",String.valueOf(e.getMessage())));}
      }}Thread.sleep(100);
    }catch(Throwable t){try{write(directory.resolve("worker-error.json"),Map.of("error",cause(t).toString()));}catch(Exception ignored){}}}
      System.getProperties().remove("chroma.live.agent");
    },"Chroma direct functional audit");worker.setDaemon(true);worker.start();
  }
  static Object run(String request)throws Exception{
    String[] lines=request.split("\\R");String operation=lines[0];verifyGameDirectory();
    if(operation.equals("commands")||operation.equals("dispatcher")){
      Object server=call(mc,"getSingleplayerServer");if(server==null)throw new IllegalStateException("No integrated server; open the isolated audit world first");
      return onThread(server,()->{
        var records=new ArrayList<Object>();for(int i=1;i<lines.length;i++)if(!lines[i].isBlank())records.add(command(server,lines[i],operation.equals("dispatcher")));
        return Map.of("ok",records.stream().noneMatch(v->((Map<?,?>)v).containsKey("exception")),"commands",records);
      });
    }
    if(operation.equals("detach")){running=false;return Map.of("ok",true,"detached",true);}
    return onThread(mc,()->{
      if(operation.equals("status")){
        var result=new LinkedHashMap<String,Object>();result.put("ok",true);result.put("pid",ProcessHandle.current().pid());result.put("gameDirectory",gameDirectory.toString());
        result.put("paused",call(mc,"isPaused"));result.put("fps",call(mc,"getFps"));result.put("frameTimeNs",call(mc,"getFrameTimeNs"));
        result.put("integratedServer",call(mc,"getSingleplayerServer")!=null);result.put("levelLoaded",mcType.getField("level").get(mc)!=null);
        result.put("reload",reloadState);result.put("resourcePacks",field(field(mc,"options"),"resourcePacks"));
        result.put("appliedPostEffects",((List<?>)call(field(mc,"gameRenderer"),"getAppliedPostEffects")).stream().map(chain->{try{return String.valueOf(call(chain,"id"));}catch(Exception e){return e.toString();}}).toList());
        Object player=field(mc,"player");
        if(player!=null)result.put("player",Map.of("x",call(player,"getX"),"y",call(player,"getY"),"z",call(player,"getZ"),"yaw",call(player,"getYRot"),"pitch",call(player,"getXRot")));
        return result;
      }
      if(operation.equals("open")){Object flows=call(mc,"createWorldOpenFlows");flows.getClass().getMethod("openWorld",String.class,Runnable.class).invoke(flows,lines[1],(Runnable)()->{});}
      else if(operation.equals("configure")){
        Object options=field(mc,"options");options.getClass().getField("pauseOnLostFocus").setBoolean(options,false);
        option(options,"bobView",false);option(options,"entityShadows",false);option(options,"enableVsync",false);
        option(options,"inactivityFpsLimit",type("net.minecraft.client.InactivityFpsLimit").getField("MINIMIZED").get(null));
        option(options,"framerateLimit",120);
        call(mc,"getFramerateLimitTracker").getClass().getMethod("setFramerateLimit",int.class).invoke(call(mc,"getFramerateLimitTracker"),120);
        Object hud=field(field(mc,"gui"),"hud");Field hidden=hud.getClass().getDeclaredField("isHidden");hidden.setAccessible(true);hidden.setBoolean(hud,true);
        call(call(mc,"getTutorial"),"stop");method(mcType,"setScreenAndShow",1).invoke(mc,new Object[]{null});
        return Map.of("ok",true,"hudHidden",true,"pauseOnLostFocus",false,"bobView",false,"fpsLimit",120);
      }
      else if(operation.equals("reload")){
        if(reloadState.equals("running"))throw new IllegalStateException("Resource reload already running");
        reloadState="running";
        ((CompletableFuture<?>)call(mc,"reloadResourcePacks")).whenComplete((value,error)->reloadState=error==null?"complete":"error: "+cause(error));
        return Map.of("ok",true,"reload",reloadState);
      }
      else if(operation.equals("reload-status"))return Map.of("ok",true,"reload",reloadState);
      else if(operation.equals("dump")){
        String name=lines.length>1?lines[1]:"capture";
        if(!name.matches("[a-zA-Z0-9_-]+"))throw new IllegalArgumentException("dump name must be a simple filename");
        return dump(directory.resolve("captures").resolve(name));
      }
      else if(operation.equals("capture"))type("net.minecraft.client.Screenshot").getMethod("grab",mcType,boolean.class).invoke(null,mc,false);
      else if(operation.equals("close-screen"))method(mcType,"setScreenAndShow",1).invoke(mc,new Object[]{null});
      else if(operation.equals("exit")){running=false;call(mc,"stop");}
      else throw new IllegalArgumentException("Unknown operation: "+operation);
      return Map.of("ok",true,"operation",operation);
    });
  }
  /** Read back the actual vanilla OpenGL main image and persistent post targets, preserving GL state. */
  static Object dump(Path out)throws Exception{
    Files.createDirectories(out);
    Object renderer=field(mc,"gameRenderer");var targets=new LinkedHashMap<String,Object>();
    targets.put("main",call(renderer,"mainRenderTarget"));
    Map<?,?> chains=(Map<?,?>)field(field(call(mc,"getShaderManager"),"postChains"),"postChains");
    for(var entry:chains.entrySet())if(entry.getKey().toString().contains("end_of_frame")){
      Optional<?> chain=(Optional<?>)entry.getValue();
      if(chain.isPresent())for(var target:((Map<?,?>)field(chain.get(),"persistentTargets")).entrySet())targets.put(target.getKey().toString(),target.getValue());
    }
    Class<?> gl=type("org.lwjgl.opengl.GL11"),gl15=type("org.lwjgl.opengl.GL15");
    Method geti=gl.getMethod("glGetInteger",int.class),bind=gl.getMethod("glBindTexture",int.class,int.class),pixel=gl.getMethod("glPixelStorei",int.class,int.class),bindBuffer=gl15.getMethod("glBindBuffer",int.class,int.class);
    int oldBinding=(int)geti.invoke(null,32873),oldPbo=(int)geti.invoke(null,35053);
    int[] settings={3333,3330,3331,3332,3328,3329,32875,32876};int[] values=new int[settings.length];for(int i=0;i<settings.length;i++)values[i]=(int)geti.invoke(null,settings[i]);
    var records=new ArrayList<Object>();Set<Integer> seen=new HashSet<>();
    try{
      bindBuffer.invoke(null,35051,0);for(int s:settings)pixel.invoke(null,s,s==3333?1:0);
      for(var entry:targets.entrySet())for(String kind:List.of("color","depth")){
        Object tex=call(entry.getValue(),kind.equals("color")?"getColorTexture":"getDepthTexture");if(tex==null)continue;
        int id=(int)call(tex,"glId");if(!seen.add(id))continue;
        int w=(int)tex.getClass().getMethod("getWidth",int.class).invoke(tex,0),h=(int)tex.getClass().getMethod("getHeight",int.class).invoke(tex,0);
        if(w<=0||h<=0||w*(long)h>16000000)throw new IllegalStateException("Unexpected texture size");
        ByteBuffer buffer=ByteBuffer.allocateDirect(w*h*4).order(ByteOrder.LITTLE_ENDIAN);bind.invoke(null,3553,id);
        gl.getMethod("glGetTexImage",int.class,int.class,int.class,int.class,ByteBuffer.class).invoke(null,3553,0,kind.equals("depth")?6402:6408,kind.equals("depth")?5126:5121,buffer);
        byte[] bytes=new byte[buffer.capacity()];buffer.get(bytes);
        String file=entry.getKey().replaceAll("[^a-zA-Z0-9_-]","_")+"-"+kind+".bin";Files.write(out.resolve(file),bytes);
        if(kind.equals("color")){
          var image=new java.awt.image.BufferedImage(w,h,java.awt.image.BufferedImage.TYPE_INT_ARGB);
          for(int y=0;y<h;y++)for(int x=0;x<w;x++){int p=(y*w+x)*4;image.setRGB(x,h-y-1,((bytes[p+3]&255)<<24)|((bytes[p]&255)<<16)|((bytes[p+1]&255)<<8)|(bytes[p+2]&255));}
          javax.imageio.ImageIO.write(image,"png",out.resolve(file.replace(".bin",".png")).toFile());
        }
        records.add(Map.of("file",file,"width",w,"height",h,"kind",kind,"label",String.valueOf(call(tex,"getLabel")),"textureId",id,"format",String.valueOf(call(tex,"getFormat"))));
      }
    }finally{bind.invoke(null,3553,oldBinding);bindBuffer.invoke(null,35051,oldPbo);for(int i=0;i<settings.length;i++)pixel.invoke(null,settings[i],values[i]);}
    write(out.resolve("manifest.json"),Map.of("pid",ProcessHandle.current().pid(),"gameDirectory",gameDirectory.toString(),"targets",records));
    return Map.of("ok",true,"directory",out.toString(),"targets",records);
  }
  static Map<String,Object> command(Object server,String command,boolean direct)throws Exception{
    var record=new LinkedHashMap<String,Object>();record.put("command",command);
    var messages=new ArrayList<String>();var sourceResults=new ArrayList<Object>();var completion=new ArrayList<Object>();
    record.put("messages",messages);record.put("results",sourceResults);record.put("completion",completion);
    try{
      Object commands=call(server,"getCommands"),source=call(server,"createCommandSourceStack");
      Class<?> sourceInterface=type("net.minecraft.commands.CommandSource"),callbackInterface=type("net.minecraft.commands.CommandResultCallback");
      Object sink=Proxy.newProxyInstance(loader,new Class<?>[]{sourceInterface},(proxy,m,args)->{
        return switch(m.getName()){
          case"sendSystemMessage"->{messages.add(String.valueOf(call(args[0],"getString")));yield null;}
          case"acceptsSuccess","acceptsFailure","alwaysAccepts"->true;
          case"shouldInformAdmins"->false;
          case"toString"->"ChromaLiveProbe output";case"hashCode"->System.identityHashCode(proxy);case"equals"->proxy==args[0];
          default->null;
        };
      });
      Object callback=Proxy.newProxyInstance(loader,new Class<?>[]{callbackInterface},(proxy,m,args)->{
        if(m.getName().equals("onResult")){sourceResults.add(Map.of("success",args[0],"result",args[1]));return null;}
        if(m.getName().equals("equals"))return proxy==args[0];
        if(m.getName().equals("hashCode"))return System.identityHashCode(proxy);
        if(m.getName().equals("toString"))return "ChromaLiveProbe source callback";
        if(m.isDefault())return InvocationHandler.invokeDefault(proxy,m,args);
        return null;
      });
      Object done=Proxy.newProxyInstance(loader,new Class<?>[]{callbackInterface},(proxy,m,args)->{
        if(m.getName().equals("onResult")){completion.add(Map.of("success",args[0],"result",args[1]));return null;}
        if(m.getName().equals("equals"))return proxy==args[0];
        if(m.getName().equals("hashCode"))return System.identityHashCode(proxy);
        if(m.getName().equals("toString"))return "ChromaLiveProbe completion callback";
        if(m.isDefault())return InvocationHandler.invokeDefault(proxy,m,args);return null;
      });
      source=source.getClass().getMethod("withSource",sourceInterface).invoke(source,sink);
      source=source.getClass().getMethod("withCallback",callbackInterface).invoke(source,callback);
      Object dispatcher=call(commands,"getDispatcher");
      if(direct){
        Method execute=Arrays.stream(dispatcher.getClass().getMethods()).filter(m->m.getName().equals("execute")&&m.getParameterCount()==2&&m.getParameterTypes()[0]==String.class).findFirst().orElseThrow();
        record.put("dispatcherResult",execute.invoke(dispatcher,command,source));
      }else{
        Method parse=Arrays.stream(dispatcher.getClass().getMethods()).filter(m->m.getName().equals("parse")&&m.getParameterCount()==2&&m.getParameterTypes()[0]==String.class).findFirst().orElseThrow();
        Object parsed=parse.invoke(dispatcher,command,source);
        method(commands.getClass(),"validateParseResults",1).invoke(null,parsed);
        Object context=call(parsed,"getContext");Object built=context.getClass().getMethod("build",String.class).invoke(context,command);
        Object chain=((Optional<?>)method(type("com.mojang.brigadier.context.ContextChain"),"tryFlatten",1).invoke(null,built)).orElseThrow();
        Object executionSource=source;
        Consumer<Object> queue=execution->{try{method(type("net.minecraft.commands.execution.ExecutionContext"),"queueInitialCommandExecution",5).invoke(null,execution,command,chain,executionSource,done);}catch(Exception e){throw new RuntimeException(e);}};
        method(commands.getClass(),"executeCommandInContext",2).invoke(null,source,queue);
      }
      record.put("engine",direct?"brigadier.dispatcher.execute":"Minecraft26.3 execution context");
    }catch(Throwable t){var e=cause(t);record.put("exception",e.getClass().getName());record.put("error",String.valueOf(e.getMessage()));}
    return record;
  }
}

