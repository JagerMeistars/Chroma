import java.lang.instrument.Instrumentation;
import java.lang.reflect.Field;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.time.Instant;
import java.util.*;
import java.util.concurrent.*;
import net.minecraft.client.Minecraft;
import net.minecraft.client.KeyMapping;
import net.minecraft.client.InactivityFpsLimit;
import net.minecraft.client.gui.GuiGraphicsExtractor;
import net.minecraft.client.gui.screens.Screen;
import net.minecraft.network.chat.Component;
import net.minecraft.util.debugchart.LocalSampleLogger;
import net.minecraft.world.phys.Vec3;
import com.mojang.blaze3d.systems.RenderSystem;

/** Isolated test instrumentation. Measures vanilla's completed-frame wall intervals, never changes world rendering. */
public final class bench_ChromaBenchmark {
  static Minecraft mc;
  static Path directory;
  static volatile boolean running=true;
  static volatile Measurement measurement;
  static volatile String reloadState="not_requested";
  static Field loggerField;
  static LocalSampleLogger originalLogger;
  static final int MAX_SAMPLES=500000;

  static void verify() throws Exception {
    Path actual=mc.gameDirectory.getCanonicalFile().toPath();
    Path expected=Path.of(System.getProperty("user.home"),"AppData","Roaming","PrismLauncher","instances","chroma-direct-audit-26.3","minecraft").toFile().getCanonicalFile().toPath();
    if(!actual.equals(expected))throw new SecurityException("Refusing non-isolated Chroma game directory: "+actual);
  }
  static Field field(Class<?> cls,String name)throws Exception {
    for(Class<?> c=cls;c!=null;c=c.getSuperclass())try{Field f=c.getDeclaredField(name);f.setAccessible(true);return f;}catch(NoSuchFieldException ignored){}
    throw new NoSuchFieldException(name);
  }
  static Object onThread(Callable<Object> task)throws Exception {
    CompletableFuture<Object> result=new CompletableFuture<>();
    mc.execute(()->{try{result.complete(task.call());}catch(Throwable error){result.completeExceptionally(error);}});
    return result.get(30,TimeUnit.SECONDS);
  }
  static String json(Object value) {
    if(value==null)return "null";
    if(value instanceof Number||value instanceof Boolean)return value.toString();
    if(value instanceof Map<?,?> m){List<String> out=new ArrayList<>();m.forEach((k,v)->out.add(json(k.toString())+":"+json(v)));return "{"+String.join(",",out)+"}";}
    if(value instanceof Iterable<?> a){List<String> out=new ArrayList<>();a.forEach(v->out.add(json(v)));return "["+String.join(",",out)+"]";}
    StringBuilder s=new StringBuilder("\"");
    for(char c:value.toString().toCharArray())switch(c){case '\\'->s.append("\\\\");case '"'->s.append("\\\"");case '\n'->s.append("\\n");case '\r'->s.append("\\r");case '\t'->s.append("\\t");default->{if(c<32)s.append(String.format("\\u%04x",(int)c));else s.append(c);}}
    return s.append('"').toString();
  }
  static void write(Path path,Object value)throws Exception{Files.writeString(path,json(value)+"\n",StandardCharsets.UTF_8);}
  public static void agentmain(String argument,Instrumentation instrumentation)throws Exception {
    mc=Minecraft.getInstance();verify();directory=Path.of(argument).toAbsolutePath().normalize();Files.createDirectories(directory);
    if(System.getProperties().putIfAbsent("chroma.benchmark.agent",directory.toString())!=null)throw new IllegalStateException("Chroma benchmark already attached");
    onThread(()->{Object overlay=mc.getDebugOverlay();loggerField=field(overlay.getClass(),"frameTimeLogger");originalLogger=(LocalSampleLogger)loggerField.get(overlay);loggerField.set(overlay,new FrameLogger());return true;});
    write(directory.resolve("ready.json"),Map.of("ok",true,"pid",ProcessHandle.current().pid(),"gameDirectory",mc.gameDirectory.getCanonicalPath(),"method","Vanilla DebugScreenOverlay.logFrameDuration: completed-frame wall intervals after submit, present and frame limiter"));
    Thread worker=new Thread(()->{
      while(running)try{
        Measurement m=measurement;
        if(m!=null&&m.complete&&!m.saved){saveMeasurement(m);m.saved=true;}
        try(var stream=Files.list(directory)){
          for(Path request:stream.filter(p->p.getFileName().toString().endsWith(".req")).sorted().toList()){
            String contents=Files.readString(request,StandardCharsets.UTF_8);Files.move(request,Path.of(request+".running"));
            try{write(Path.of(request+".done"),run(contents));}catch(Throwable error){while(error instanceof ExecutionException&&error.getCause()!=null)error=error.getCause();write(Path.of(request+".done"),Map.of("ok",false,"error",error.toString()));}
          }
        }
        Thread.sleep(100);
      }catch(Throwable error){try{write(directory.resolve("worker-error.json"),Map.of("ok",false,"error",error.toString()));}catch(Exception ignored){}}
      System.getProperties().remove("chroma.benchmark.agent");
    },"Chroma isolated benchmark requests");worker.setDaemon(true);worker.start();
  }
  static Map<String,Object> status()throws Exception {
    var out=new LinkedHashMap<String,Object>();var window=mc.getWindow();var target=mc.gameRenderer.mainRenderTarget();
    out.put("ok",true);out.put("pid",ProcessHandle.current().pid());out.put("gameDirectory",mc.gameDirectory.getCanonicalPath());
    out.put("framebufferWidth",target.width);out.put("framebufferHeight",target.height);
    out.put("windowFramebufferWidth",window.getWidth());out.put("windowFramebufferHeight",window.getHeight());
    out.put("screenWidth",window.getScreenWidth());out.put("screenHeight",window.getScreenHeight());out.put("pixelDensity",window.getPixelDensity());
    out.put("iconified",window.isIconified());out.put("focused",window.isFocused());out.put("paused",mc.isPaused());out.put("levelLoaded",mc.level!=null);
    out.put("vanillaFpsCounter",mc.getFps());out.put("effectiveFrameLimit",mc.getFramerateLimitTracker().getFramerateLimit());out.put("throttleReason",mc.getFramerateLimitTracker().getThrottleReason().toString());
    out.put("vsync",mc.options.enableVsync().get());out.put("fov",mc.options.fov().get());out.put("renderDistance",mc.options.renderDistance().get());out.put("simulationDistance",mc.options.simulationDistance().get());
    out.put("resourcePacks",List.copyOf(mc.options.resourcePacks));out.put("repositorySelectedPacks",List.copyOf(mc.getResourcePackRepository().getSelectedIds()));out.put("reload",reloadState);out.put("screen",mc.gui.screen()==null?"none":mc.gui.screen().getClass().getName());
    out.put("hudHidden",field(mc.gui.hud.getClass(),"isHidden").getBoolean(mc.gui.hud));
    out.put("deviceInfo",RenderSystem.getDevice().getDeviceInfo().toString());
    out.put("surfaceConfiguration",mc.windowSurface().currentConfiguration().toString());
    if(mc.player!=null)out.put("camera",Map.of("x",mc.player.getX(),"y",mc.player.getY(),"z",mc.player.getZ(),"yaw",mc.player.getYRot(),"pitch",mc.player.getXRot()));
    return out;
  }
  static Object run(String request)throws Exception {
    verify();String[] a=request.split("\\R");String op=a[0];
    return onThread(()->{
      if(op.equals("status")){var out=status();Measurement m=measurement;if(m!=null)out.put("measurement",Map.of("name",m.name,"frames",m.count,"complete",m.complete,"saved",m.saved,"output",directory.resolve("results").resolve(m.name+".json").toString()));return out;}
      if(op.equals("select-packs")){
        if(measurement!=null&&!measurement.complete)throw new IllegalStateException("Measurement in progress");
        if(reloadState.equals("running"))throw new IllegalStateException("Resource reload already in progress");
        var selected=new ArrayList<String>();for(int i=1;i<a.length;i++)if(!a[i].isBlank())selected.add(a[i]);
        if(selected.isEmpty())selected.add("vanilla");
        var repository=mc.getResourcePackRepository();repository.reload();
        for(String id:selected)if(!repository.isAvailable(id))throw new IllegalArgumentException("Unknown resource pack "+id+"; available="+repository.getAvailableIds());
        repository.setSelected(selected);mc.options.resourcePacks=new ArrayList<>(selected);mc.options.incompatibleResourcePacks.clear();reloadState="running";
        mc.reloadResourcePacks().whenComplete((value,error)->reloadState=error==null?"complete":"error: "+error);
        return Map.of("ok",true,"selected",selected,"reload",reloadState);
      }
      if(op.equals("configure")){
        if(measurement!=null&&!measurement.complete)throw new IllegalStateException("Measurement in progress");
        int width=a.length>1?Integer.parseInt(a[1]):1920,height=a.length>2?Integer.parseInt(a[2]):1080;
        if(width<320||height<240||width>7680||height>4320)throw new IllegalArgumentException("Invalid framebuffer size");
        mc.options.pauseOnLostFocus=false;mc.options.enableVsync().set(false);mc.options.framerateLimit().set(260);mc.getFramerateLimitTracker().setFramerateLimit(260);
        mc.options.inactivityFpsLimit().set(InactivityFpsLimit.MINIMIZED);mc.options.bobView().set(false);mc.options.entityShadows().set(false);mc.options.fov().set(70);
        mc.options.renderDistance().set(8);mc.options.simulationDistance().set(5);
        field(mc.gui.hud.getClass(),"isHidden").setBoolean(mc.gui.hud,true);mc.getTutorial().stop();
        KeyMapping.releaseAll();KeyMapping.resetToggleKeys();if(mc.player!=null)mc.player.setDeltaMovement(Vec3.ZERO);
        mc.setScreenAndShow(new InputLockScreen());mc.mouseHandler.releaseMouse();
        float density=mc.getWindow().getPixelDensity();
        mc.getWindow().setWindowed(Math.round(width/density),Math.round(height/density));mc.invalidateSurfaceConfiguration();
        return Map.of("ok",true,"requestedFramebufferWidth",width,"requestedFramebufferHeight",height,"frameLimiter","260 means unlimited in this exact Minecraft 26.3 client","note","Check status after resize events to verify actual render target dimensions");
      }
      if(op.equals("measure")){
        if(measurement!=null&&!measurement.saved)throw new IllegalStateException("Previous measurement still active or saving");
        String name=a[1];if(!name.matches("[a-zA-Z0-9_-]+"))throw new IllegalArgumentException("Invalid measurement name");
        if(Files.exists(directory.resolve("results").resolve(name+".json")))throw new IllegalArgumentException("Result already exists; choose a unique measurement name");
        double warmup=a.length>2?Double.parseDouble(a[2]):10,seconds=a.length>3?Double.parseDouble(a[3]):20;
        if(warmup<0||warmup>60||seconds<5||seconds>60)throw new IllegalArgumentException("Warmup 0-60 and sample 5-60 seconds required");
        if(mc.level==null||mc.isPaused())throw new IllegalStateException("Unpaused loaded world required");
        if(!(mc.gui.screen() instanceof InputLockScreen))throw new IllegalStateException("configure first to lock input");
        var target=mc.gameRenderer.mainRenderTarget();if(target.width!=1920||target.height!=1080)throw new IllegalStateException("Expected 1920x1080 actual framebuffer; found "+target.width+"x"+target.height);
        if(mc.getWindow().isIconified()||!mc.getFramerateLimitTracker().getThrottleReason().toString().equals("NONE"))throw new IllegalStateException("Window throttled");
        if(mc.options.enableVsync().get()||mc.getFramerateLimitTracker().getFramerateLimit()<260)throw new IllegalStateException("Vsync or frame limiter active");
        measurement=new Measurement(name,warmup,seconds,status());
        return Map.of("ok",true,"name",name,"warmupSeconds",warmup,"sampleSeconds",seconds,"output",directory.resolve("results").resolve(name+".json").toString());
      }
      if(op.equals("detach")){
        if(measurement!=null&&!measurement.complete)throw new IllegalStateException("Measurement in progress");
        loggerField.set(mc.getDebugOverlay(),originalLogger);running=false;return Map.of("ok",true,"loggerRestored",true);
      }
      throw new IllegalArgumentException("Unknown benchmark operation "+op);
    });
  }
  static final class Measurement {
    final String name,startedUtc=Instant.now().toString();final long start,end;final double warmup,seconds;final Map<String,Object> initial;
    final long[] wallNs=new long[MAX_SAMPLES],cpuSubmitNs=new long[MAX_SAMPLES];int count,invalidFrames;long sumNs;volatile boolean complete,saved;Map<String,Object> last;String error;
    Measurement(String name,double warmup,double seconds,Map<String,Object> initial){this.name=name;this.warmup=warmup;this.seconds=seconds;this.initial=initial;start=System.nanoTime()+(long)(warmup*1e9);end=start+(long)(seconds*1e9);}
  }
  public static final class FrameLogger extends LocalSampleLogger {
    FrameLogger(){super(1);}
    @Override public void logSample(long value){
      originalLogger.logSample(value);Measurement m=measurement;if(m==null||m.complete)return;
      long now=System.nanoTime();if(now<m.start)return;
      if(now<m.end&&m.count<MAX_SAMPLES){
        m.wallNs[m.count]=value;m.cpuSubmitNs[m.count]=mc.getFrameTimeNs();m.count++;m.sumNs+=value;
        if(mc.isPaused()||mc.level==null||mc.getWindow().isIconified()||mc.gameRenderer.mainRenderTarget().width!=1920||mc.gameRenderer.mainRenderTarget().height!=1080||mc.getFramerateLimitTracker().getFramerateLimit()<260||mc.options.enableVsync().get())m.invalidFrames++;
      }else{
        try{m.last=status();if(m.count>=MAX_SAMPLES)m.error="Sample capacity exceeded";}catch(Exception error){m.error=error.toString();}
        m.complete=true;
      }
    }
  }
  static double percentile(long[] sorted,double p){if(sorted.length==0)return 0;return sorted[(int)Math.ceil(p*(sorted.length-1))]/1e6;}
  static void saveMeasurement(Measurement m)throws Exception {
    Path out=directory.resolve("results");Files.createDirectories(out);Path samples=out.resolve(m.name+".csv");
    try(var writer=Files.newBufferedWriter(samples,StandardCharsets.UTF_8)){writer.write("frame,wall_interval_ns,cpu_render_segment_ns\n");for(int i=0;i<m.count;i++)writer.write(i+","+m.wallNs[i]+","+m.cpuSubmitNs[i]+"\n");}
    long[] sorted=Arrays.copyOf(m.wallNs,m.count);Arrays.sort(sorted);long over144=Arrays.stream(sorted).filter(v->v>1e9/144).count();int slowCount=Math.max(1,(int)Math.ceil(m.count*.01));double slowSum=0;for(int i=Math.max(0,m.count-slowCount);i<m.count;i++)slowSum+=sorted[i];
    var result=new LinkedHashMap<String,Object>();result.put("ok",m.error==null&&m.invalidFrames==0&&m.count>0);result.put("name",m.name);result.put("startedUtc",m.startedUtc);result.put("warmupSeconds",m.warmup);result.put("requestedSampleSeconds",m.seconds);result.put("sampledIntervalSeconds",m.sumNs/1e9);result.put("frameCount",m.count);
    result.put("averageFps",m.count*1e9/Math.max(1,m.sumNs));result.put("medianFrameMs",percentile(sorted,.50));result.put("p95FrameMs",percentile(sorted,.95));result.put("p99FrameMs",percentile(sorted,.99));result.put("slowestOnePercentAverageFps",slowCount*1e9/Math.max(1,slowSum));result.put("framesOver144Budget",over144);result.put("fractionOver144Budget",over144/(double)Math.max(1,m.count));result.put("invalidFrames",m.invalidFrames);
    result.put("method","Vanilla end-of-frame wall interval after command submission, present and frame limiter. The existing debug logger is wrapped, not polled; all frames in the window are retained. No synchronous GPU readback during sampling.");
    result.put("cpuRenderSegmentMeaning","Supplementary getFrameTimeNs is update/extract/render/blit CPU wall time before submit/present; it is not a complete frame interval or GPU duration.");result.put("gpuTiming","Not enabled; vanilla GPU timing queries are not modified.");
    result.put("initialState",m.initial);result.put("finalState",m.last);result.put("samples",samples.toString());if(m.error!=null)result.put("error",m.error);write(out.resolve(m.name+".json"),result);
  }
  public static final class InputLockScreen extends Screen {
    InputLockScreen(){super(Component.empty());}
    @Override public boolean isPauseScreen(){return false;}
    @Override public boolean isInputCaptured(){return true;}
    @Override public boolean isInGameUi(){return true;}
    @Override public void extractBackground(GuiGraphicsExtractor graphics,int mouseX,int mouseY,float partialTick){}
    @Override public void extractRenderState(GuiGraphicsExtractor graphics,int mouseX,int mouseY,float partialTick){}
  }
}
