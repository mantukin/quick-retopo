import bpy
import bmesh

class QUICKRETOPO_OT_snap_verts_to_surface(bpy.types.Operator):
    """Snaps selected vertices of the retopo mesh to the reference surface."""
    bl_idname = "object.quick_retopo_snap_vertices"
    bl_label = "Snap Selected to Surface"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return bool(obj and obj.mode == 'EDIT' and obj.type == 'MESH' and "retopo_target_object" in obj)

    def execute(self, context):
        me_obj = context.edit_object
        ref_obj_name = me_obj.get("retopo_target_object")
        if not ref_obj_name:
            self.report({'WARNING'}, "Reference object not found. The mesh must be created by the addon.")
            return {'CANCELLED'}

        ref_obj = bpy.data.objects.get(ref_obj_name)
        if not ref_obj:
            self.report({'WARNING'}, f"Reference object '{ref_obj_name}' not found in the scene.")
            return {'CANCELLED'}

        bm = bmesh.from_edit_mesh(me_obj.data)
        selected_verts = [v for v in bm.verts if v.select]

        if not selected_verts:
            self.report({'INFO'}, "No vertices selected.")
            bmesh.update_edit_mesh(me_obj.data)
            return {'CANCELLED'}
            
        depsgraph = context.evaluated_depsgraph_get()
        ref_eval = ref_obj.evaluated_get(depsgraph)

        ref_inv_mtx = ref_eval.matrix_world.inverted()
        me_mtx = me_obj.matrix_world
        me_inv_mtx = me_mtx.inverted()

        for v in selected_verts:
            p_world = me_mtx @ v.co
            p_local_ref = ref_inv_mtx @ p_world
            
            success, loc_local, _, _ = ref_eval.closest_point_on_mesh(p_local_ref)

            if success:
                new_p_world = ref_eval.matrix_world @ loc_local
                v.co = me_inv_mtx @ new_p_world
        
        bmesh.update_edit_mesh(me_obj.data)
        return {'FINISHED'}

classes = (
    QUICKRETOPO_OT_snap_verts_to_surface,
)
def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
