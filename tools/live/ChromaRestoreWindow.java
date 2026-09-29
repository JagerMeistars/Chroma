import java.lang.instrument.Instrumentation;
import java.nio.file.*;
public class ChromaRestoreWindow {
 public static void agentmain(String argument,Instrumentation i)throws Exception{
  Class<?> c=Class.forName("net.minecraft.client.Minecraft");Object mc=c.getMethod("getInstance").invoke(null);
  Path actual=((java.io.File)c.getField("gameDirectory").get(mc)).getCanonicalFile().toPath();
  Path expected=Path.of(System.getProperty("user.home"),"AppData","Roaming","PrismLauncher","instances","chroma-direct-audit-26.3","minecraft");
  if(!actual.equals(expected))throw new SecurityException("Wrong isolated game directory");
  c.getMethod("execute",Runnable.class).invoke(mc,(Runnable)()->{try{
   Object w=c.getMethod("getWindow").invoke(mc);long h=(long)w.getClass().getMethod("handle").invoke(w);
   Object ok=Class.forName("org.lwjgl.sdl.SDLVideo").getMethod("SDL_RestoreWindow",long.class).invoke(null,h);
   Files.writeString(Path.of(argument),"SDL_RestoreWindow own audit window: "+ok);
  }catch(Exception e){throw new RuntimeException(e);}});
 }
}
