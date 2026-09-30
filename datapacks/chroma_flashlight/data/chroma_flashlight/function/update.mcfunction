# This context is already at the player's eye + 0.15 forward, with their rotation.
# Fixed-display local +Z is the spotlight axis; native yaw/pitch aim it correctly.
execute unless entity @e[type=minecraft:item_display,distance=0..,tag=chroma.flashlight] run summon minecraft:item_display ~ ~ ~ {Tags:["chroma.flashlight"],billboard:"fixed",item_display:"none",view_range:4f,width:0f,height:0f,teleport_duration:1,item:{id:"minecraft:paper",count:1,components:{"minecraft:item_model":"chroma:marker_spot","minecraft:custom_model_data":{colors:[16777215]}}},transformation:{translation:[0f,0f,0f],left_rotation:[0f,0f,0f,1f],scale:[16f,0.3f,1f],right_rotation:[0f,0f,0f,1f]}}
# Retire duplicate old lamps after a chunk/dimension is loaded again.
tag @e[type=minecraft:item_display,distance=0..,tag=chroma.flashlight,sort=nearest,limit=1] add chroma.flashlight.keep
kill @e[type=minecraft:item_display,distance=0..,tag=chroma.flashlight,tag=!chroma.flashlight.keep]
tag @e[type=minecraft:item_display,distance=0..,tag=chroma.flashlight] remove chroma.flashlight.keep
scoreboard players operation @e[type=minecraft:item_display,distance=0..,tag=chroma.flashlight,limit=1] chroma.flash = #session chroma.flash
tp @e[type=minecraft:item_display,distance=0..,tag=chroma.flashlight,limit=1] ~ ~ ~ ~ ~
