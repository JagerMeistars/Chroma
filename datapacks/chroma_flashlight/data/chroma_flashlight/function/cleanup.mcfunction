# distance=0.. restricts player matching to this dimension, including @a.
execute unless entity @a[tag=chroma.flashlight.owner,distance=0..] run kill @e[type=minecraft:item_display,distance=0..,tag=chroma.flashlight]
execute as @e[type=minecraft:item_display,distance=0..,tag=chroma.flashlight] unless score @s chroma.flash = #session chroma.flash run kill @s
