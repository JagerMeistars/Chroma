# Chroma 26.3 — command reference / справочник команд
# This file is NOT an installed datapack. Copy only the section you need.
# Это НЕ установленный датапак. Копируйте только нужный раздел.
# Use command blocks or functions for long summon commands; add / for chat.
# Длинные команды summon вводите в командные блоки/функции; в чате добавляйте /.

# CREATE / СОЗДАТЬ
# Run once; model names may be reused. / Выполните один раз; названия моделей можно повторять.
# Warm point light, radius 8, intensity 0.3.
# Тёплый точечный источник, радиус 8, яркость 0,3.
summon minecraft:item_display ~ ~2 ~ {Tags:["chroma.demo","chroma.demo.warm"],billboard:"fixed",item_display:"none",view_range:4f,width:0f,height:0f,item:{id:"minecraft:paper",count:1,components:{"minecraft:item_model":"chroma:marker","minecraft:custom_model_data":{colors:[16759885]}}},transformation:{translation:[0f,0f,0f],left_rotation:[0f,0f,0f,1f],scale:[8f,0.3f,1f],right_rotation:[0f,0f,0f,1f]}}

# Blue downward dome, radius 6, intensity 0.2.
# Голубая полусфера вниз, радиус 6, яркость 0,2.
summon minecraft:item_display ~4 ~3 ~ {Tags:["chroma.demo","chroma.demo.blue"],billboard:"fixed",item_display:"none",view_range:4f,width:0f,height:0f,item:{id:"minecraft:paper",count:1,components:{"minecraft:item_model":"chroma:marker_dome","minecraft:custom_model_data":{colors:[6737151]}}},transformation:{translation:[0f,0f,0f],left_rotation:[0f,0f,0f,1f],scale:[6f,0.2f,1f],right_rotation:[0f,0f,0f,1f]}}

# Tags select entities for commands; they are not lighting IDs.
# Теги выбирают сущности для команд; это не идентификаторы света.

# EDIT / ИЗМЕНИТЬ
# Run individually after creation. / Выполняйте по отдельности после создания.
data modify entity @e[type=minecraft:item_display,tag=chroma.demo.warm,sort=nearest,limit=1] item.components."minecraft:custom_model_data".colors set value [6737151]
data modify entity @e[type=minecraft:item_display,tag=chroma.demo.warm,sort=nearest,limit=1] transformation.scale[0] set value 12f
data modify entity @e[type=minecraft:item_display,tag=chroma.demo.warm,sort=nearest,limit=1] transformation.scale[1] set value 0.15f
data modify entity @e[type=minecraft:item_display,tag=chroma.demo.warm,sort=nearest,limit=1] item.components."minecraft:item_model" set value "chroma:marker_dome"
tp @e[type=minecraft:item_display,tag=chroma.demo.warm,sort=nearest,limit=1] ~ ~2 ~

# CLEANUP / УДАЛИТЬ
# Only the demo markers in this dimension. / Только маркеры примеров в этом измерении.
kill @e[type=minecraft:item_display,distance=0..,tag=chroma.demo]
