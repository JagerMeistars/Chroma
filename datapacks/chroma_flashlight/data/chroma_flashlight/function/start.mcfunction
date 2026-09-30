# Run as the player who should carry the one active test flashlight.
execute unless entity @s[type=minecraft:player] run return 0
function chroma_flashlight:stop
scoreboard players operation @s chroma.flash = #session chroma.flash
function chroma_flashlight:tick
