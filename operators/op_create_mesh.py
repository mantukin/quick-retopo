import bpy
import bmesh

from .. import state
from .. import utils

class QUICKRETOPO_OT_create_mesh(bpy.types.Operator):
    """Creates a mesh from the preview grid and snaps it to the target"""
    bl_idname = "object.quick_retopo_create_mesh"
    bl_label = "Create Retopo Mesh"
    bl_options = {'REGISTER', 'UNDO'}
    @classmethod
    def poll(cls, context):
        return utils.quickretopo_poll(cls, context)

    def execute(self, context):
        if state._handle_3d is not None:
            state._should_stop = True
            self.report({'INFO'}, "Preview stopped before creating mesh.")

        grid_cells_data = state._grid_cells
        if not grid_cells_data:
            self.report({'WARNING'}, "No grid data to create from. Start the preview first.")
            return {'CANCELLED'}

        target_object = context.view_layer.objects.active
        scene = context.scene
        size = scene.retopo_plane_size
        remap = state._vertex_remap
        overrides = state._vertex_overrides
        pinned_verts = state._pinned_vertices

        if scene.retopo_edit_mode == 'CREATE':
            def resolve(v_coord):
                while v_coord in remap:
                    v_coord = remap[v_coord]
                return v_coord

            final_verts = utils.calculate_final_verts(grid_cells_data, size, remap, overrides, pinned_verts)
            verts, vert_indices = [], {}
            for v_coord in sorted(final_verts.keys()):
                vert_indices[v_coord] = len(verts)
                verts.append(final_verts[v_coord])

            faces = []
            for ix, iy in sorted(grid_cells_data.keys()):
                c1, c2, c3, c4 = (ix, iy), (ix + 1, iy), (ix + 1, iy + 1), (ix, iy + 1)
                rc1, rc2, rc3, rc4 = resolve(c1), resolve(c2), resolve(c3), resolve(c4)
                
                if all(c in vert_indices for c in [rc1, rc2, rc3, rc4]):
                    indices_with_dupes = [vert_indices[c] for c in [rc1, rc2, rc3, rc4]]
                    # Preserve order while getting unique indices
                    unique_indices = list(dict.fromkeys(indices_with_dupes))
                    
                    # Create face if it's a triangle or a quad. Skip lines/points.
                    if len(unique_indices) >= 3:
                        faces.append(unique_indices)

            if not verts or not faces:
                self.report({'WARNING'}, "Failed to generate vertices or faces. The grid is empty or contains only degenerate faces.")
                return {'CANCELLED'}

            mesh_data = bpy.data.meshes.new("Retopo_Mesh_Data")
            mesh_data.from_pydata(verts, [], faces)
            
            # Merge by distance to weld the remapped vertices
            bm = bmesh.new()
            bm.from_mesh(mesh_data)
            bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.0001)
            bm.to_mesh(mesh_data)
            bm.free()
            
            mesh_data.update(); mesh_data.validate()

            plane_obj = bpy.data.objects.new("Retopo_Plane", mesh_data)
            context.collection.objects.link(plane_obj)
            
            # Store reference object name in a custom property
            plane_obj["retopo_target_object"] = target_object.name

            bpy.ops.object.select_all(action='DESELECT')
            plane_obj.select_set(True)
            context.view_layer.objects.active = plane_obj
            bpy.ops.object.origin_set(type='ORIGIN_GEOMETRY', center='BOUNDS')

            # Apply modifiers if the option is enabled
            if scene.retopo_add_modifiers:
                subdiv_mod = plane_obj.modifiers.new(name="Subdivision", type='SUBSURF')
                subdiv_mod.levels = 1; subdiv_mod.render_levels = 2; subdiv_mod.show_viewport = False
                shrinkwrap_mod = plane_obj.modifiers.new(name="Shrinkwrap", type='SHRINKWRAP')
                shrinkwrap_mod.target = target_object; shrinkwrap_mod.show_viewport = False

            # Enable snapping if the option is enabled
            if scene.retopo_enable_snapping:
                ts = scene.tool_settings
                ts.use_snap = True
                ts.snap_target = 'CLOSEST'
                ts.use_snap_self = False
                ts.use_snap_align_rotation = True
                ts.use_snap_backface_culling = True

                # Handle API change for snap projection in Blender 4.1+
                if bpy.app.version >= (4, 1, 0):
                    ts.snap_elements = {'FACE_PROJECT'}
                else:
                    ts.snap_elements = {'FACE'}
                    ts.use_snap_project = True

            self.report({'INFO'}, f"Retopology mesh created for '{target_object.name}'.")
            return {'FINISHED'}

        elif scene.retopo_edit_mode == 'SELECT':
            # --- New mode: Select polygons on the reference mesh under the grid ---
            from mathutils import Vector
            
            # Helper function for 2D point-in-polygon test using the ray casting algorithm.
            def is_point_in_poly_2d(point_2d, poly_verts_2d):
                n = len(poly_verts_2d)
                inside = False
                p1x, p1y = poly_verts_2d[0]
                for i in range(n + 1):
                    p2x, p2y = poly_verts_2d[i % n]
                    if min(p1y, p2y) < point_2d.y <= max(p1y, p2y) and point_2d.x <= max(p1x, p2x):
                        if p1y != p2y:
                            xinters = (point_2d.y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                        if p1x == p2x or point_2d.x <= xinters:
                            inside = not inside
                    p1x, p1y = p2x, p2y
                return inside

            # Helper to find the final destination of a remapped vertex.
            def resolve(v_coord):
                while v_coord in remap: v_coord = remap[v_coord]
                return v_coord

            # 1. Calculate the final 3D world positions of all grid vertices.
            final_verts = utils.calculate_final_verts(grid_cells_data, size, remap, overrides, pinned_verts)
            if not final_verts:
                self.report({'WARNING'}, "Could not calculate grid vertices.")
                return {'CANCELLED'}
            
            # 2. Prepare the target object for selection in Edit Mode.
            if context.mode != 'OBJECT':
                bpy.ops.object.mode_set(mode='OBJECT')
            bpy.ops.object.select_all(action='DESELECT')
            context.view_layer.objects.active = target_object
            target_object.select_set(True)

            bpy.ops.object.mode_set(mode='EDIT')
            bpy.ops.mesh.select_all(action='DESELECT')
            
            me = target_object.data
            bm = bmesh.from_edit_mesh(me)
            bm.faces.ensure_lookup_table()

            # 3. For performance, pre-calculate the world-space center and normal of every face on the target mesh.
            # This avoids recalculating matrix multiplications inside the main loop.
            face_data_world = {}
            world_mtx = target_object.matrix_world
            normal_mtx = world_mtx.inverted_safe().transposed().to_3x3()
            for f in bm.faces:
                face_data_world[f.index] = {
                    'center': world_mtx @ f.calc_center_median(),
                    'normal': (normal_mtx @ f.normal).normalized()
                }
            
            selected_faces_count = 0
            
            # 4. Iterate through each quad of the preview grid.
            for ix, iy in sorted(grid_cells_data.keys()):
                c1, c2, c3, c4 = (ix, iy), (ix + 1, iy), (ix + 1, iy + 1), (ix, iy + 1)
                rc1, rc2, rc3, rc4 = resolve(c1), resolve(c2), resolve(c3), resolve(c4)
                
                if all(c in final_verts for c in [rc1, rc2, rc3, rc4]):
                    p1, p2, p3, p4 = final_verts[rc1], final_verts[rc2], final_verts[rc3], final_verts[rc4]
                    
                    # 5. For each grid quad, define a local 2D plane based on its vertices.
                    center = (p1 + p2 + p3 + p4) / 4.0
                    n1 = (p2 - p1).cross(p4 - p1)
                    n2 = (p4 - p3).cross(p2 - p3)
                    normal = (n1 + n2)
                    if normal.length_squared < 1e-9: continue
                    normal.normalize()

                    # Create an orthonormal basis (x_axis, y_axis) for the plane.
                    x_axis = (p2 - p1)
                    if x_axis.length_squared < 1e-9: continue
                    x_axis.normalize()
                    y_axis = normal.cross(x_axis).normalized()
                    
                    # 6. Project the 3D quad vertices into the 2D plane.
                    quad_2d = []
                    for p_world in [p1, p2, p3, p4]:
                        vec = p_world - center
                        quad_2d.append(Vector((vec.dot(x_axis), vec.dot(y_axis))))
                        
                    # 7. Iterate through target faces and check if their center lies within the 2D quad.
                    for face in bm.faces:
                        if face.select: continue # Skip already selected faces
                        
                        face_data = face_data_world[face.index]
                        fc_world = face_data['center']
                        face_normal_world = face_data['normal']
                        
                        # BUGFIX: Add checks to prevent selecting faces on the other side of the mesh.
                        # Check 1: Normal alignment. Face normal must point in a similar direction to the quad normal.
                        # A dot product > 0.1 means they are in the same general hemisphere, with tolerance for curves.
                        if face_normal_world.dot(normal) > 0.1:
                            # Check 2: Proximity. Face center must be close to the quad's average plane.
                            distance_to_plane = abs((fc_world - center).dot(normal))
                            
                            # Define a threshold based on the quad's average dimension. This is generous to handle curvature.
                            quad_width = ((p2 - p1).length + (p4 - p3).length) / 2.0
                            quad_height = ((p4 - p1).length + (p3 - p2).length) / 2.0
                            # Use half of the average dimension as a more conservative threshold
                            # to better handle curved surfaces without grabbing distant polygons.
                            threshold = (quad_width + quad_height) / 4.0
                            
                            if distance_to_plane < threshold:
                                # Project the face's 3D center into the quad's 2D plane.
                                vec_fc = fc_world - center
                                fc_2d = Vector((vec_fc.dot(x_axis), vec_fc.dot(y_axis)))
                                
                                # 8. If it's inside, select the face.
                                if is_point_in_poly_2d(fc_2d, quad_2d):
                                    face.select = True
                                    selected_faces_count += 1
            
            # 9. Update the mesh in the viewport to show the new selection.
            bmesh.update_edit_mesh(me)
            
            self.report({'INFO'}, f"Selected {selected_faces_count} polygons on '{target_object.name}'.")
            return {'FINISHED'}

classes = (
    QUICKRETOPO_OT_create_mesh,
)
def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
