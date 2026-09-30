import com.google.gson.GsonBuilder;
import com.mojang.brigadier.StringReader;
import com.mojang.math.Transformation;
import net.minecraft.SharedConstants;
import net.minecraft.commands.Commands;
import net.minecraft.commands.arguments.NbtPathArgument.NbtPath;
import net.minecraft.commands.functions.CommandFunction;
import net.minecraft.core.component.DataComponentPatch;
import net.minecraft.core.component.DataComponents;
import net.minecraft.data.registries.VanillaRegistries;
import net.minecraft.nbt.CompoundTag;
import net.minecraft.nbt.NbtOps;
import net.minecraft.nbt.TagParser;
import net.minecraft.resources.RegistryOps;
import net.minecraft.server.Bootstrap;
import net.minecraft.server.permissions.PermissionSet;
import net.minecraft.world.entity.Display;
import net.minecraft.world.item.ItemDisplayContext;
import net.minecraft.world.item.Item;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.HashSet;

/** Uses unmodified 26.3 command parsers and codecs. Never executes a command,
 * starts a game/server, loads a world, or creates an entity. */
public class CheckExamples {
    public static void main(String[] args) throws Exception {
        Path root = Path.of(args[0]).toAbsolutePath().normalize();
        Path report = Path.of(args[1]);
        SharedConstants.tryDetectVersion();
        Bootstrap.bootStrap();
        var world = VanillaRegistries.createWorldLookup();
        var registries = VanillaRegistries.createReloadableLookup(world);
        var ops = RegistryOps.create(NbtOps.INSTANCE, registries);
        var dispatcher = new Commands(Commands.CommandSelection.ALL,
                Commands.createValidationContext(registries)).getDispatcher();
        var source = Commands.createCompilationContext(PermissionSet.ALL_PERMISSIONS);
        var results = new ArrayList<Map<String, Object>>();
        var errors = new ArrayList<String>();
        int commands = 0, summons = 0, modifications = 0, downwardSpots = 0, flashlightDirections = 0, scopedFlashlightSelectors = 0;
        var files = new ArrayList<>(List.of("docs/examples.mcfunction", "docs/examples-128.mcfunction", "docs/README.en.md", "docs/README.ru.md"));
        Path datapacks = root.resolve("datapacks");
        if (Files.isDirectory(datapacks)) {
            try (var paths = Files.walk(datapacks)) {
                paths.filter(p -> p.toString().endsWith(".mcfunction")).sorted()
                    .forEach(p -> files.add(root.relativize(p).toString().replace('\\', '/')));
            }
        }
        for (String file : files) {
            CompoundTag warmExample = null;
            var fixtureModels = new HashSet<String>();
            int fixtureSources = 0;
            var fixtureColours = new HashSet<Integer>();
            List<String> lines = Files.readAllLines(root.resolve(file), StandardCharsets.UTF_8);
            for (int i = 0; i < lines.size(); i++) {
                String command = lines.get(i).strip();
                if (file.endsWith(".md") && !command.startsWith("/")) continue;
                if (command.isBlank() || command.startsWith("#")) continue;
                command = Commands.trimOptionalPrefix(command);
                String location = file + ":" + (i + 1);
                try {
                    CommandFunction.parseCommand(dispatcher, source, new StringReader(command));
                    if (file.startsWith("datapacks/chroma_flashlight/")) {
                        var selectors = java.util.regex.Pattern.compile("@e\\[[^\\]]+\\]").matcher(command);
                        while (selectors.find()) {
                            var selector = new net.minecraft.commands.arguments.selector.EntitySelectorParser(
                                new StringReader(selectors.group()), true).parse();
                            // `execute in` alone does not scope @e: native findEntities
                            // otherwise scans getAllLevels(), deleting another dimension's lamp.
                            if (!selector.isWorldLimited())
                                throw new IllegalArgumentException("Flashlight selector crosses dimensions: " + selectors.group());
                            scopedFlashlightSelectors++;
                        }
                    }
                    commands++;
                    Map<String, Object> detail = new LinkedHashMap<>();
                    detail.put("location", location);
                    detail.put("command_parse", "passed");
                    if (command.startsWith("summon ") || command.contains(" run summon minecraft:item_display ")) {
                        CompoundTag nbt = TagParser.parseCompoundFully(command.substring(command.indexOf('{')));
                        CompoundTag item = nbt.getCompoundOrEmpty("item");
                        Item.CODEC.parse(ops, item.get("id")).getOrThrow();
                        CompoundTag components = item.getCompoundOrEmpty("components");
                        DataComponentPatch.CODEC.parse(ops, components).getOrThrow();
                        var model = DataComponents.ITEM_MODEL.codec().parse(ops, components.get("minecraft:item_model")).getOrThrow();
                        var data = DataComponents.CUSTOM_MODEL_DATA.codec().parse(ops, components.get("minecraft:custom_model_data")).getOrThrow();
                        if (model == null || data == null || data.colors().size() != 1)
                            throw new IllegalArgumentException("Missing model or exactly one custom colour");
                        Path modelPath = root.resolve("assets/" + model.getNamespace() + "/items/" + model.getPath() + ".json");
                        if (!Files.isRegularFile(modelPath)) throw new IllegalArgumentException("Missing model " + model);
                        var transformation = Transformation.EXTENDED_CODEC.parse(ops, nbt.get("transformation")).getOrThrow();
                        var billboard = Display.BillboardConstraints.CODEC.parse(ops, nbt.get("billboard")).getOrThrow();
                        var context = ItemDisplayContext.CODEC.parse(ops, nbt.get("item_display")).getOrThrow();
                        if (billboard != Display.BillboardConstraints.FIXED || context != ItemDisplayContext.NONE)
                            throw new IllegalArgumentException("Unexpected display context or billboard");
                        if (transformation.scale().x() <= 0 || transformation.scale().y() <= 0)
                            throw new IllegalArgumentException("Nonpositive marker scale");
                        int color = data.getColor(0);
                        if (file.endsWith("examples-128.mcfunction")) {
                            String primary = model.getPath();
                            if (!List.of("marker", "marker_spot_narrow", "marker_spot", "marker_spot_wide", "marker_dome").contains(primary))
                                throw new IllegalArgumentException("Fixture must use a primary shape ID without a source number: " + primary);
                            fixtureSources++;
                            fixtureModels.add(primary);
                            if (!fixtureColours.add(color)) throw new IllegalArgumentException("Duplicate fixture colour " + color);
                            if (model.getPath().contains("_spot")) {
                                // Live vanilla model readback establishes facing=-Z;
                                // the shader emits along its opposite, local +Z.
                                var axis = new org.joml.Vector3f(0, 0, 1)
                                    .rotate(transformation.rightRotation()).mul(transformation.scale())
                                    .rotate(transformation.leftRotation()).normalize();
                                if (axis.y() > -.999f) throw new IllegalArgumentException("Fixture spotlight is not aimed down: " + axis);
                                detail.put("downward_spot_axis", List.of(axis.x(), axis.y(), axis.z()));
                                downwardSpots++;
                            }
                        }
                        if (command.contains("chroma.demo.warm")) {
                            if (color != 0xFFBC4D) throw new IllegalArgumentException("Warm RGB mismatch");
                            warmExample = nbt.copy();
                        } else if (command.contains("chroma.demo.blue") && color != 0x66CCFF)
                            throw new IllegalArgumentException("Blue RGB mismatch");
                        if (file.endsWith("chroma_flashlight/function/update.mcfunction")) {
                            if (!model.toString().equals("chroma:marker_spot") || color != 0xFFFFFF
                                    || nbt.getIntOr("teleport_duration", 0) != 1)
                                throw new IllegalArgumentException("Unexpected flashlight default or interpolation");
                            // Native DisplayRenderer FIXED uses rotationYXZ(-yaw, pitch, 0).
                            // Compare the marker axis with Minecraft's view vector, including
                            // vertical looks and the +/-180 yaw crossing.
                            for (float yaw : new float[]{-180, -179.9f, -90, 0, 90, 179.9f, 180}) {
                                for (float pitch : new float[]{-90, -60, 0, 60, 90}) {
                                    var axis = new org.joml.Vector3f(0, 0, 1)
                                        .rotate(transformation.rightRotation()).mul(transformation.scale())
                                        .rotate(transformation.leftRotation()).normalize()
                                        .rotate(new org.joml.Quaternionf().rotationYXZ(
                                            -yaw * (float)Math.PI / 180, pitch * (float)Math.PI / 180, 0));
                                    var expected = net.minecraft.world.phys.Vec3.directionFromRotation(pitch, yaw);
                                    if (axis.distance((float)expected.x, (float)expected.y, (float)expected.z) > .0003f)
                                        throw new IllegalArgumentException("Flashlight axis differs from player view: " + yaw + ", " + pitch);
                                    flashlightDirections++;
                                }
                            }
                            detail.put("player_view_directions", 35);
                        }
                        detail.put("item_registry_codec", "passed");
                        detail.put("item_component_patch_codec", "passed");
                        detail.put("display_context_codec", "passed");
                        detail.put("billboard_codec", "passed");
                        detail.put("transformation_codec", "passed");
                        detail.put("model", model.toString());
                        detail.put("color_decimal", color);
                        detail.put("color_hex", String.format("#%06X", color));
                        detail.put("scale_x", transformation.scale().x());
                        detail.put("scale_y", transformation.scale().y());
                        summons++;
                    } else if (command.startsWith("data modify entity ")) {
                        if (warmExample == null) throw new IllegalStateException("No example NBT to validate modification");
                        int pathStart = command.indexOf("] ") + 2;
                        int valueStart = command.indexOf(" set value ", pathStart);
                        String pathText = command.substring(pathStart, valueStart);
                        String valueText = command.substring(valueStart + " set value ".length());
                        var value = TagParser.create(NbtOps.INSTANCE).parseFully(valueText);
                        NbtPath nbtPath = NbtPath.of(pathText);
                        if (nbtPath.countMatching(warmExample) != 1)
                            throw new IllegalArgumentException("Path does not resolve exactly once: " + pathText);
                        nbtPath.set(warmExample, value);
                        DataComponentPatch.CODEC.parse(ops,
                                warmExample.getCompoundOrEmpty("item").getCompoundOrEmpty("components")).getOrThrow();
                        Transformation.EXTENDED_CODEC.parse(ops, warmExample.get("transformation")).getOrThrow();
                        detail.put("in_memory_nbt_path_and_codec", "passed");
                        modifications++;
                    }
                    results.add(detail);
                } catch (Throwable failure) {
                    errors.add(location + ": " + failure);
                }
            }
            if (file.endsWith("examples-128.mcfunction") && (fixtureSources != 128 || fixtureColours.size() != 128 || fixtureModels.size() != 5))
                errors.add(file + ": must contain 128 sources, 128 distinct colours and all five unnumbered primary shape IDs");
        }
        var summary = new LinkedHashMap<String, Object>();
        summary.put("minecraft_version", SharedConstants.getCurrentVersion().name());
        summary.put("commands_parsed", commands);
        summary.put("summon_payloads_decoded", summons);
        summary.put("modifications_applied_to_memory_only", modifications);
        summary.put("downward_fixture_spotlights", downwardSpots);
        summary.put("flashlight_view_directions", flashlightDirections);
        summary.put("flashlight_dimension_scoped_selectors", scopedFlashlightSelectors);
        summary.put("results", results);
        summary.put("errors", errors);
        summary.put("boundaries", List.of(
                "Commands were parsed only, never dispatched or executed.",
                "Only detached NBT copies were modified to verify paths and codecs.",
                "Item identifiers and supplied component patches are decoded separately; full ItemStack defaults are not bootstrapped.",
                "No world, server, entity, renderer or gameplay behavior was tested.",
                "Selector syntax is checked; entity matching in an actual world is not."));
        String json = new GsonBuilder().setPrettyPrinting().disableHtmlEscaping().create().toJson(summary);
        Files.writeString(report, json, StandardCharsets.UTF_8);
        System.out.println("Minecraft " + SharedConstants.getCurrentVersion().name()
                + ": commands=" + commands + ", summon_payloads=" + summons
                + ", detached_nbt_modifications=" + modifications + ", errors=" + errors.size());
        for (String error : errors) System.err.println(error);
        System.out.println("Report: " + report.toAbsolutePath());
        System.exit(errors.isEmpty() ? 0 : 1);
    }
}
