import java.lang.instrument.Instrumentation;
import java.nio.file.Files;
import java.nio.file.Path;
import net.minecraft.client.Minecraft;
import net.minecraft.client.KeyMapping;
import net.minecraft.client.gui.GuiGraphicsExtractor;
import net.minecraft.client.gui.screens.Screen;
import net.minecraft.network.chat.Component;
import net.minecraft.world.phys.Vec3;

/** Invisible, non-pausing screen for stable captures in the isolated Chroma audit client. */
public final class ChromaLiveInputLock {
  static void verify(Minecraft mc) throws Exception {
    Path actual=mc.gameDirectory.getCanonicalFile().toPath();
    Path expected=Path.of(System.getProperty("user.home"),"AppData","Roaming","PrismLauncher","instances","chroma-direct-audit-26.3","minecraft").toFile().getCanonicalFile().toPath();
    if(!actual.equals(expected))throw new SecurityException("Refusing non-isolated Chroma game directory: "+actual);
  }
  public static void agentmain(String argument,Instrumentation instrumentation) throws Exception {
    Minecraft mc=Minecraft.getInstance();verify(mc);
    Path result=Path.of(argument).toAbsolutePath();
    mc.execute(()->{
      try{
        verify(mc);
        mc.options.fov().set(70);
        mc.options.bobView().set(false);
        mc.options.pauseOnLostFocus=false;
        KeyMapping.releaseAll();
        KeyMapping.resetToggleKeys();
        if(mc.player!=null)mc.player.setDeltaMovement(Vec3.ZERO);
        mc.setScreenAndShow(new InputLockScreen());
        mc.mouseHandler.releaseMouse();
        Files.writeString(result,"Input lock active; isolated PID="+ProcessHandle.current().pid()+"; transparent non-pausing screen; FOV=70; Escape or close-screen restores gameplay input.\n");
      }catch(Throwable error){try{Files.writeString(result,"ERROR: "+error+"\n");}catch(Exception ignored){}}
    });
  }
  public static final class InputLockScreen extends Screen {
    public InputLockScreen(){super(Component.empty());}
    @Override public boolean isPauseScreen(){return false;}
    @Override public boolean isInputCaptured(){return true;}
    @Override public boolean isInGameUi(){return true;}
    @Override public void extractBackground(GuiGraphicsExtractor graphics,int mouseX,int mouseY,float partialTick){}
    @Override public void extractRenderState(GuiGraphicsExtractor graphics,int mouseX,int mouseY,float partialTick){}
  }
}
