import bpy
from . import state
from . import operators

class QUICKRETOPO_UL_container_list(bpy.types.UIList):
    """UIList for the retopo container."""
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        obj = item.obj
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            if obj:
                layout.prop(obj, "name", text="", emboss=False, icon_value=icon)
            else:
                layout.label(text="<Empty>", icon='ERROR')
        elif self.layout_type == 'GRID':
            layout.alignment = 'CENTER'
            layout.label(text="", icon_value=icon)
class QUICKRETOPO_PT_panel(bpy.types.Panel):
    """Creates a Panel in the 3D View Sidebar"""
    bl_label = "Quick Retopo"
    bl_idname = "QUICKRETOPO_PT_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Retopo'
    def draw(self, context):
        layout = self.layout
        scene = context.scene
        obj = context.active_object

        col = layout.column(align=True)
        col.label(text="Grid Settings:")
        col.prop(scene, "retopo_plane_size")
        col.prop(scene, "retopo_align_distance")
        col.prop(scene, "retopo_arrow_radius")
        col.prop(scene, "retopo_arrow_click_radius")
        col.prop(scene, "retopo_draw_offset")
        col.prop(scene, "retopo_resize_ratio")
        
        box = layout.box()
        box.prop(scene, "retopo_x_ray_mode")
        box.prop(scene, "retopo_prevent_click_through")
        layout.separator()
        
        # Preview controls
        col = layout.column(align=True)
        col.label(text="Preview:")
        is_preview_running = state._handle_3d is not None
        
        if is_preview_running:
            box = col.box()
            op_groups_col = box.column(align=True)
            
            # --- Align Group ---
            row1 = op_groups_col.row(align=True)
            row1.operator(operators.QUICKRETOPO_OT_align_grid.bl_idname, text="Align", icon='SNAP_ON')
            row1.operator(operators.QUICKRETOPO_OT_align_and_pin_grid.bl_idname, text="Align and Pin", icon='SNAP_VERTEX')
            
            op_groups_col.separator()

            # --- Shape Group ---
            row2 = op_groups_col.row(align=True)
            row2.operator(operators.QUICKRETOPO_OT_straighten_grid.bl_idname, text="Straighten", icon='GRID')
            row2.operator(operators.QUICKRETOPO_OT_strong_straighten_grid.bl_idname, text="Flatten", icon='CON_ROTLIKE')

            op_groups_col.separator()

            # --- State Group ---
            row3 = op_groups_col.row(align=True)
            if state._pinned_vertices:
                row3.operator(operators.QUICKRETOPO_OT_pin_all_grid_verts.bl_idname, text="Unpin All", icon='UNPINNED')
            else:
                row3.operator(operators.QUICKRETOPO_OT_pin_all_grid_verts.bl_idname, text="Pin All", icon='PINNED')

            op = row3.operator(operators.QUICKRETOPO_OT_plane_preview.bl_idname, text="Delete Grid", icon='X')
            op.action = 'DELETE'
        else:
            row = col.row(align=True)
            op_start = row.operator(operators.QUICKRETOPO_OT_plane_preview.bl_idname, text="Start Drawing", icon='GREASEPENCIL')
            op_start.action = 'START'
            
            op_ref = row.operator(operators.QUICKRETOPO_OT_plane_preview.bl_idname, text="Start from Container", icon='LINKED')
            op_ref.action = 'START_REFERENCE'
        
        layout.separator()

        # --- Final Action ---
        final_action_col = layout.column()
        # Enable options only if there is a grid to work with.
        final_action_col.enabled = len(state._grid_cells) > 0
        
        final_action_col.label(text="Final Action:")
        final_action_col.row().prop(scene, "retopo_edit_mode", expand=True)
        
        if scene.retopo_edit_mode == 'CREATE':
            box = final_action_col.box()
            box.prop(scene, "retopo_add_modifiers")
            box.prop(scene, "retopo_enable_snapping")
            
            final_action_col.operator(operators.QUICKRETOPO_OT_create_mesh.bl_idname, text="Create Retopo Mesh", icon='ADD')
        else: # 'SELECT'
            final_action_col.operator(operators.QUICKRETOPO_OT_create_mesh.bl_idname, text="Select Polygons", icon='RESTRICT_SELECT_OFF')

        layout.separator()

        # Edit mode controls
        col = layout.column(align=True)
        col.label(text="Edit:")
        edit_col = col.column()
        
        # Determine if the button should be enabled and set it *before* drawing the operator.
        is_edit_mode = bool(obj and obj.mode == 'EDIT' and obj.type == 'MESH' and "retopo_target_object" in obj)
        edit_col.enabled = is_edit_mode
        
        edit_col.operator(operators.QUICKRETOPO_OT_snap_verts_to_surface.bl_idname, text="Snap Selected to Surface", icon='MOD_SHRINKWRAP')
        
        # Stitch operator (Object Mode)
        col.operator(operators.QUICKRETOPO_OT_stitch_meshes.bl_idname, text="Stitch Selected", icon='AUTOMERGE_ON')
        layout.separator()

        # Container controls
        col = layout.column(align=True)
        col.label(text="Highlight Container:")
        
        row = col.row()
        row.template_list(
            "QUICKRETOPO_UL_container_list",
            "",
            scene,
            "retopo_container_items",
            scene,
            "retopo_container_active_index"
        )
        
        subcol = row.column(align=True)
        subcol.operator(operators.QUICKRETOPO_OT_container_add.bl_idname, text="", icon='ADD')
        
        remove_col = subcol.column(align=True)
        
        # Disable remove button if list is empty or index is out of bounds
        is_removable = len(scene.retopo_container_items) > 0 and 0 <= scene.retopo_container_active_index < len(scene.retopo_container_items)
        remove_col.enabled = is_removable
        
        remove_col.operator(operators.QUICKRETOPO_OT_container_remove.bl_idname, text="", icon='REMOVE')

classes = (
    QUICKRETOPO_UL_container_list,
    QUICKRETOPO_PT_panel,
)
def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
