# Invalidating the session also retires old offline owners / unloaded lamps.
execute unless entity @s[type=minecraft:player] run return 0
scoreboard players add #session chroma.flash 1
tag @a[tag=chroma.flashlight.owner] remove chroma.flashlight.owner
execute in minecraft:overworld run kill @e[type=minecraft:item_display,distance=0..,tag=chroma.flashlight]
execute in minecraft:the_nether run kill @e[type=minecraft:item_display,distance=0..,tag=chroma.flashlight]
execute in minecraft:the_end run kill @e[type=minecraft:item_display,distance=0..,tag=chroma.flashlight]
