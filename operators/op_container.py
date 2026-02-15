import bpy

class QUICKRETOPO_OT_container_add(bpy.types.Operator):
    """Adds the selected mesh to the container for highlighting."""
    bl_idname = "object.quickretopo_container_add"
    bl_label = "Add to Container"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == 'MESH'
    def execute(self, context):
        scene = context.scene
        obj = context.active_object
        
        # Check if object is already in the list
        if any(item.obj == obj for item in scene.retopo_container_items):
            self.report({'INFO'}, f"Object '{obj.name}' is already in the container.")
            return {'CANCELLED'}
        
        new_item = scene.retopo_container_items.add()
        new_item.obj = obj
        scene.retopo_container_active_index = len(scene.retopo_container_items) - 1
        
        self.report({'INFO'}, f"Object '{obj.name}' added to the container.")
        return {'FINISHED'}
class QUICKRETOPO_OT_container_remove(bpy.types.Operator):
    """Removes the selected item from the container."""
    bl_idname = "object.quickretopo_container_remove"
    bl_label = "Remove from Container"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return len(context.scene.retopo_container_items) > 0
    def execute(self, context):
        scene = context.scene
        index = scene.retopo_container_active_index
        
        if not (0 <= index < len(scene.retopo_container_items)):
            return {'CANCELLED'}
            
        item_to_remove = scene.retopo_container_items[index]
        obj_name = item_to_remove.obj.name if item_to_remove.obj else "..."
        
        scene.retopo_container_items.remove(index)
        
        # Adjust active index
        if len(scene.retopo_container_items) > 0:
            if index >= len(scene.retopo_container_items):
                scene.retopo_container_active_index = len(scene.retopo_container_items) - 1
        else:
            scene.retopo_container_active_index = 0
            
        self.report({'INFO'}, f"Object '{obj_name}' removed from the container.")
        return {'FINISHED'}
class QUICKRETOPO_OT_stitch_meshes(bpy.types.Operator):
    """Joins selected retopo meshes and merges overlapping vertices."""
    bl_idname = "object.quickretopo_stitch_meshes"
    bl_label = "Stitch Selected Meshes"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        if context.mode != 'OBJECT':
            return False
        
        selected_objects = context.selected_objects
        if len(selected_objects) < 2:
            return False
        
        # Check if all selected are retopo meshes created by the addon
        return all(obj.type == 'MESH' and "retopo_target_object" in obj for obj in selected_objects)
    def execute(self, context):
        num_objects = len(context.selected_objects)
        
        # Ensure we have an active object among the selected, which is required for join
        if context.active_object not in context.selected_objects:
            context.view_layer.objects.active = context.selected_objects[0]

        bpy.ops.object.join()
        
        # The joined object is now the active object
        active_obj = context.active_object
        
        # Switch to Edit Mode, select all, and merge vertices by distance
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.mesh.remove_doubles(threshold=0.0001)
        bpy.ops.object.mode_set(mode='OBJECT')
        
        self.report({'INFO'}, f"Stitched {num_objects} objects into '{active_obj.name}'.")
        return {'FINISHED'}

classes = (
    QUICKRETOPO_OT_container_add,
    QUICKRETOPO_OT_container_remove,
    QUICKRETOPO_OT_stitch_meshes,
)
def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
