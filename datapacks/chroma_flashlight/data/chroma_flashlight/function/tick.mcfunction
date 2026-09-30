# Rebuild the online-owner tag so an old owner cannot take over on reconnect.
tag @a[tag=chroma.flashlight.owner] remove chroma.flashlight.owner
execute as @a if score @s chroma.flash = #session chroma.flash run tag @s add chroma.flashlight.owner
execute in minecraft:overworld run function chroma_flashlight:cleanup
execute in minecraft:the_nether run function chroma_flashlight:cleanup
execute in minecraft:the_end run function chroma_flashlight:cleanup
# Server eye position includes crouching/swimming, but not render-only view bob.
execute as @a[tag=chroma.flashlight.owner] at @s rotated as @s anchored eyes positioned ^ ^ ^0.15 run function chroma_flashlight:update
