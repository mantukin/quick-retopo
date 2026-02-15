import bpy
import bmesh
import math
from mathutils import Vector, Matrix
from mathutils.kdtree import KDTree
from collections import Counter

from .. import state
from .. import utils
class QUICKRETOPO_OT_align_grid(bpy.types.Operator):
    """Snaps the preview grid's boundary vertices to the nearest vertices of finalized meshes in the Highlight Container."""
    bl_idname = "object.quick_retopo_align_grid"
    bl_label = "Align Grid"
    bl_options = {'REGISTER'}
    @classmethod
    def poll(cls, context):
        return state._handle_3d is not None and len(state._grid_cells) > 0

    def execute(self, context):
        scene = context.scene
        grid_cells = state._grid_cells
        remap = state._vertex_remap
        size = scene.retopo_plane_size

        if not scene.retopo_container_items:
            self.report({'WARNING'}, "Highlight container is empty. Nothing to snap to.")
            return {'CANCELLED'}

        # --- Part 1: Build KDTree from all vertices in the container meshes ---
        container_verts_world = []
        depsgraph = context.evaluated_depsgraph_get()

        for item in scene.retopo_container_items:
            obj = item.obj
            if not obj or obj.type != 'MESH':
                continue

            # Get the evaluated object which includes all modifiers
            obj_eval = obj.evaluated_get(depsgraph)
            
            try:
                # Create a temporary mesh from the evaluated object
                mesh = obj_eval.to_mesh()

                if not mesh or not mesh.vertices:
                    # If mesh creation failed or it's empty, skip to the finally block for cleanup
                    continue

                # Get world-space vertex coordinates and add them to our list
                matrix = obj_eval.matrix_world
                container_verts_world.extend([matrix @ v.co for v in mesh.vertices])

            finally:
                # IMPORTANT: Always free the temporary mesh data created by to_mesh().
                # This is the correct way to prevent memory leaks and the
                # "outside of main database" error.
                if obj_eval and hasattr(obj_eval, 'to_mesh_clear'):
                    obj_eval.to_mesh_clear()

        if not container_verts_world:
            self.report({'WARNING'}, "Could not find any geometry in the container objects.")
            return {'CANCELLED'}

        kd = KDTree(len(container_verts_world))
        for i, v_co in enumerate(container_verts_world):
            kd.insert(v_co, i)
        kd.balance()

        # --- Part 2: Resolve vertex positions and find boundary vertices ---
        def resolve(v_coord):
            while v_coord in remap:
                v_coord = remap[v_coord]
            return v_coord

        final_verts = utils.calculate_final_verts(grid_cells, size, remap, state._vertex_overrides, state._pinned_vertices)
        if not final_verts:
            return {'CANCELLED'}

        # This set will track container vertices that are already used as snap targets.
        # We pre-populate it by finding any grid vertices that are already very close to a target ("stuck").
        # This prevents quad collapses where multiple new vertices snap to the same target vertices.
        snapped_target_indices = set()
        stuck_threshold = 0.001 

        for v_pos in final_verts.values():
            try:
                _co, index, dist = kd.find(v_pos)
                if dist < stuck_threshold:
                    snapped_target_indices.add(index)
            except IndexError:
                # KDTree can be empty
                pass

        edge_counts = {}
        for ix, iy in grid_cells.keys():
            corners = [(ix, iy), (ix + 1, iy), (ix + 1, iy + 1), (ix, iy + 1)]
            resolved_corners = [resolve(c) for c in corners]
            edges = [
                tuple(sorted((resolved_corners[0], resolved_corners[1]))),
                tuple(sorted((resolved_corners[1], resolved_corners[2]))),
                tuple(sorted((resolved_corners[2], resolved_corners[3]))),
                tuple(sorted((resolved_corners[3], resolved_corners[0]))),
            ]
            for edge in edges:
                if edge[0] == edge[1]: continue
                if all(c in final_verts for c in edge):
                    edge_counts[edge] = edge_counts.get(edge, 0) + 1
        
        boundary_v_coords = set()
        for edge, count in edge_counts.items():
            if count == 1:
                boundary_v_coords.add(edge[0])
                boundary_v_coords.add(edge[1])

        # --- Part 3: Find and snap nearby boundary vertices ---
        snapped_count = 0
        search_radius = scene.retopo_align_distance
        
        # The snapped_target_indices set is now pre-populated.

        # 1. Build a list of candidate vertices to snap.
        snap_candidates = []
        processed_resolved_coords = set()
        
        all_original_v_coords = set()
        for ix, iy in grid_cells.keys():
            all_original_v_coords.add((ix, iy))
            all_original_v_coords.add((ix + 1, iy))
            all_original_v_coords.add((ix + 1, iy + 1))
            all_original_v_coords.add((ix, iy + 1))

        for v_coord_orig in all_original_v_coords:
            v_coord_resolved = resolve(v_coord_orig)
            
            if v_coord_resolved in processed_resolved_coords:
                continue

            if v_coord_resolved in boundary_v_coords and v_coord_resolved not in state._pinned_vertices:
                processed_resolved_coords.add(v_coord_resolved)
                current_pos = final_verts.get(v_coord_resolved)
                if not current_pos:
                    continue
                
                # Find distance to the absolute closest point to use for sorting.
                _co, _index, dist = kd.find(current_pos)
                
                if dist < search_radius:
                    # If a vertex is already perfectly aligned, don't consider it for snapping again.
                    # This prevents vertices from jumping between very close targets on repeated clicks.
                    if dist < 0.0001:
                        continue
                        
                    # Store the resolved coordinate, its position, and the distance for sorting.
                    snap_candidates.append({'resolved': v_coord_resolved, 'pos': current_pos, 'dist': dist})

        # 2. Sort candidates by distance, so the closest vertices get priority.
        snap_candidates.sort(key=lambda c: c['dist'])

        # 3. Iterate through sorted candidates and perform the snapping.
        for candidate in snap_candidates:
            # Find up to 5 nearest neighbors in the container geometry.
            # This provides fallbacks if the closest one is already taken.
            nearest_neighbors = kd.find_n(candidate['pos'], 5)
            
            for _co, index, dist in nearest_neighbors:
                # Check if this neighbor is within the search radius and hasn't been used.
                if dist < search_radius and index not in snapped_target_indices:
                    # This is a valid, available snap target.
                    snapped_pos = container_verts_world[index]
                    
                    # Apply override to the resolved coordinate for consistency.
                    state._vertex_overrides[candidate['resolved']] = snapped_pos
                    
                    # Mark the container vertex as used.
                    snapped_target_indices.add(index)
                    
                    snapped_count += 1
                    
                    # Break from the inner loop (nearest_neighbors) and move to the next candidate.
                    break
        
        if snapped_count > 0:
            state._needs_update = True
            context.area.tag_redraw()
            self.report({'INFO'}, f"Snapped {snapped_count} vertices to container geometry.")
        else:
            self.report({'INFO'}, "No nearby vertices found to snap.")

        return {'FINISHED'}
class QUICKRETOPO_OT_align_and_pin_grid(bpy.types.Operator):
    """Snaps the preview grid's boundary vertices and pins them."""
    bl_idname = "object.quick_retopo_align_and_pin_grid"
    bl_label = "Align and Pin Grid"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        return state._handle_3d is not None and len(state._grid_cells) > 0
    def execute(self, context):
        scene = context.scene
        grid_cells = state._grid_cells
        remap = state._vertex_remap
        size = scene.retopo_plane_size

        if not scene.retopo_container_items:
            self.report({'WARNING'}, "Highlight container is empty. Nothing to snap to.")
            return {'CANCELLED'}

        # --- Part 1: Build KDTree from all vertices in the container meshes ---
        container_verts_world = []
        depsgraph = context.evaluated_depsgraph_get()

        for item in scene.retopo_container_items:
            obj = item.obj
            if not obj or obj.type != 'MESH':
                continue
            obj_eval = obj.evaluated_get(depsgraph)
            try:
                mesh = obj_eval.to_mesh()
                if not mesh or not mesh.vertices:
                    continue
                matrix = obj_eval.matrix_world
                container_verts_world.extend([matrix @ v.co for v in mesh.vertices])
            finally:
                if obj_eval and hasattr(obj_eval, 'to_mesh_clear'):
                    obj_eval.to_mesh_clear()

        if not container_verts_world:
            self.report({'WARNING'}, "Could not find any geometry in the container objects.")
            return {'CANCELLED'}

        kd = KDTree(len(container_verts_world))
        for i, v_co in enumerate(container_verts_world):
            kd.insert(v_co, i)
        kd.balance()
        
        # --- Part 2: Resolve vertex positions and find boundary vertices ---
        def resolve(v_coord):
            while v_coord in remap:
                v_coord = remap[v_coord]
            return v_coord

        final_verts = utils.calculate_final_verts(grid_cells, size, remap, state._vertex_overrides, state._pinned_vertices)
        if not final_verts:
            return {'CANCELLED'}

        # Pre-populate used targets by finding "stuck" vertices to prevent collapses.
        snapped_target_indices = set()
        stuck_threshold = 0.001

        for v_pos in final_verts.values():
            try:
                _co, index, dist = kd.find(v_pos)
                if dist < stuck_threshold:
                    snapped_target_indices.add(index)
            except IndexError:
                pass

        edge_counts = {}
        for ix, iy in grid_cells.keys():
            corners = [(ix, iy), (ix + 1, iy), (ix + 1, iy + 1), (ix, iy + 1)]
            resolved_corners = [resolve(c) for c in corners]
            edges = [
                tuple(sorted((resolved_corners[0], resolved_corners[1]))),
                tuple(sorted((resolved_corners[1], resolved_corners[2]))),
                tuple(sorted((resolved_corners[2], resolved_corners[3]))),
                tuple(sorted((resolved_corners[3], resolved_corners[0]))),
            ]
            for edge in edges:
                if edge[0] == edge[1]: continue
                if all(c in final_verts for c in edge):
                    edge_counts[edge] = edge_counts.get(edge, 0) + 1
        
        boundary_v_coords = set()
        for edge, count in edge_counts.items():
            if count == 1:
                boundary_v_coords.add(edge[0])
                boundary_v_coords.add(edge[1])

        # --- Part 3: Find and snap nearby boundary vertices ---
        snapped_count = 0
        search_radius = scene.retopo_align_distance
        # snapped_target_indices is now pre-populated from above
        snap_candidates = []
        processed_resolved_coords = set()
        
        all_original_v_coords = set()
        for ix, iy in grid_cells.keys():
            all_original_v_coords.add((ix, iy))
            all_original_v_coords.add((ix + 1, iy))
            all_original_v_coords.add((ix + 1, iy + 1))
            all_original_v_coords.add((ix, iy + 1))

        for v_coord_orig in all_original_v_coords:
            v_coord_resolved = resolve(v_coord_orig)
            
            if v_coord_resolved in processed_resolved_coords:
                continue

            if v_coord_resolved in boundary_v_coords and v_coord_resolved not in state._pinned_vertices:
                processed_resolved_coords.add(v_coord_resolved)
                current_pos = final_verts.get(v_coord_resolved)
                if not current_pos:
                    continue
                
                _co, _index, dist = kd.find(current_pos)
                
                if dist < search_radius:
                    if dist < 0.0001:
                        continue
                    snap_candidates.append({'resolved': v_coord_resolved, 'pos': current_pos, 'dist': dist})

        snap_candidates.sort(key=lambda c: c['dist'])

        for candidate in snap_candidates:
            nearest_neighbors = kd.find_n(candidate['pos'], 5)
            
            for _co, index, dist in nearest_neighbors:
                if dist < search_radius and index not in snapped_target_indices:
                    snapped_pos = container_verts_world[index]
                    
                    # Apply override to the resolved coordinate for consistency.
                    state._vertex_overrides[candidate['resolved']] = snapped_pos
                    
                    # Pin the vertex using its resolved coordinate
                    state._pinned_vertices[candidate['resolved']] = snapped_pos
                    
                    snapped_target_indices.add(index)
                    snapped_count += 1
                    break
        
        if snapped_count > 0:
            state._needs_update = True
            context.area.tag_redraw()
            self.report({'INFO'}, f"Snapped and pinned {snapped_count} vertices.")
        else:
            self.report({'INFO'}, "No nearby vertices found to snap.")

        return {'FINISHED'}
class QUICKRETOPO_OT_straighten_grid(bpy.types.Operator):
    """Straightens the preview grid by aligning all segments to a calculated global orientation, making rows and columns straight."""
    bl_idname = "object.quick_retopo_straighten_grid"
    bl_label = "Straighten Grid"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        return state._handle_3d is not None and len(state._grid_cells) > 0
    def execute(self, context):
        grid_cells = state._grid_cells
        remap = state._vertex_remap
        size = context.scene.retopo_plane_size

        if not grid_cells:
            return {'CANCELLED'}

        # --- Part 1: Calculate averaged vertex positions to regularize segment size ---
        final_verts = utils.calculate_final_verts(grid_cells, size, remap, state._vertex_overrides, state._pinned_vertices)
        if not final_verts:
            return {'CANCELLED'}

        # --- Part 2: Determine a global reference rotation for the whole grid ---
        avg_x_dir = Vector()
        avg_y_dir = Vector()

        for transform in grid_cells.values():
            rot = transform['rot']
            avg_x_dir += rot.col[0]
            avg_y_dir += rot.col[1]

        # Check for invalid average directions (e.g., on a sharp U-turn)
        if avg_x_dir.length < 0.01 or avg_y_dir.length < 0.01:
            # Fallback to the "first" cell's rotation if averaging fails
            first_cell_coord = min(grid_cells.keys())
            ref_rot = grid_cells[first_cell_coord]['rot'].copy()
            self.report({'INFO'}, "Could not determine global orientation, using first segment's orientation as a fallback.")
        else:
            avg_x_dir.normalize()
            # Orthogonalize Y with respect to X (Gram-Schmidt process)
            avg_y_dir = (avg_y_dir - avg_y_dir.dot(avg_x_dir) * avg_x_dir)
            if avg_y_dir.length < 0.01:
                # If avg_y is parallel to avg_x, we need a fallback.
                # Create a perpendicular vector using a world axis.
                world_up = Vector((0.0, 0.0, 1.0))
                if abs(avg_x_dir.dot(world_up)) > 0.99:
                    world_up = Vector((0.0, 1.0, 0.0)) # Use world Y if X is aligned with Z
                avg_y_dir = avg_x_dir.cross(world_up).normalized()
            else:
                avg_y_dir.normalize()

            # Z is the cross product of the new X and Y
            avg_z_dir = avg_x_dir.cross(avg_y_dir).normalized()
            # Re-orthogonalize X to ensure the matrix is perfectly orthogonal
            avg_x_dir = avg_y_dir.cross(avg_z_dir).normalized()

            # Build the final reference rotation matrix
            ref_rot = Matrix.Identity(3)
            ref_rot.col[0] = avg_x_dir
            ref_rot.col[1] = avg_y_dir
            ref_rot.col[2] = avg_z_dir

        # --- Part 3: Update each cell's transform, conforming to surface but guided by global rotation ---
        def resolve(v_coord):
            while v_coord in remap:
                v_coord = remap[v_coord]
            return v_coord

        for (ix, iy), transform in grid_cells.items():
            c1, c2, c3, c4 = (ix, iy), (ix + 1, iy), (ix + 1, iy + 1), (ix, iy + 1)
            rc1, rc2, rc3, rc4 = resolve(c1), resolve(c2), resolve(c3), resolve(c4)
            
            if all(c in final_verts for c in [rc1, rc2, rc3, rc4]):
                p1, p2, p3, p4 = final_verts[rc1], final_verts[rc2], final_verts[rc3], final_verts[rc4]
                new_center = (p1 + p2 + p3 + p4) / 4.0
                
                # Project center to surface AND get new transform guided by ref_rot
                new_loc, new_rot, success = utils.get_surface_transform_at_point(context, new_center, ref_rot)
                
                if success:
                    transform['loc'] = new_loc
                    transform['rot'] = new_rot
                    transform['ideal_rot'] = new_rot.copy()
        
        # Unify cell sizes to the global setting
        global_size_vec = Vector((size, size))
        for transform in grid_cells.values():
            transform['size'] = global_size_vec.copy()
            
        # Clear manual overrides as this global operation defines a new base shape
        state._vertex_overrides.clear()
        state._needs_update = True
        context.area.tag_redraw()
        self.report({'INFO'}, "Grid straightened.")
        return {'FINISHED'}
class QUICKRETOPO_OT_strong_straighten_grid(bpy.types.Operator):
    """Strongly straightens the preview grid to a single global orientation, ignoring surface curvature."""
    bl_idname = "object.quick_retopo_strong_straighten_grid"
    bl_label = "Flatten Grid"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        return state._handle_3d is not None and len(state._grid_cells) > 0
    def execute(self, context):
        grid_cells = state._grid_cells
        remap = state._vertex_remap
        size = context.scene.retopo_plane_size

        if not grid_cells:
            return {'CANCELLED'}

        # --- Part 1: Calculate averaged vertex positions ---
        final_verts = utils.calculate_final_verts(grid_cells, size, remap, state._vertex_overrides, state._pinned_vertices)
        if not final_verts:
            return {'CANCELLED'}

        # --- Part 2: Determine a global reference rotation (same as regular straighten) ---
        avg_x_dir = Vector()
        avg_y_dir = Vector()

        for transform in grid_cells.values():
            rot = transform['rot']
            avg_x_dir += rot.col[0]
            avg_y_dir += rot.col[1]

        if avg_x_dir.length < 0.01 or avg_y_dir.length < 0.01:
            first_cell_coord = min(grid_cells.keys())
            ref_rot = grid_cells[first_cell_coord]['rot'].copy()
            self.report({'INFO'}, "Could not determine global orientation, using first segment's orientation as a fallback.")
        else:
            avg_x_dir.normalize()
            avg_y_dir = (avg_y_dir - avg_y_dir.dot(avg_x_dir) * avg_x_dir)
            if avg_y_dir.length < 0.01:
                world_up = Vector((0.0, 0.0, 1.0))
                if abs(avg_x_dir.dot(world_up)) > 0.99:
                    world_up = Vector((0.0, 1.0, 0.0))
                avg_y_dir = avg_x_dir.cross(world_up).normalized()
            else:
                avg_y_dir.normalize()
            avg_z_dir = avg_x_dir.cross(avg_y_dir).normalized()
            avg_x_dir = avg_y_dir.cross(avg_z_dir).normalized()
            ref_rot = Matrix.Identity(3)
            ref_rot.col[0] = avg_x_dir
            ref_rot.col[1] = avg_y_dir
            ref_rot.col[2] = avg_z_dir
        def resolve(v_coord):
            while v_coord in remap:
                v_coord = remap[v_coord]
            return v_coord

        # --- Part 3: Update each cell's transform using the global rotation only ---
        target_object = context.view_layer.objects.active
        depsgraph = context.evaluated_depsgraph_get()
        target_eval = target_object.evaluated_get(depsgraph)
        try:
            target_inv_mtx = target_eval.matrix_world.inverted()
        except ValueError:
             self.report({'WARNING'}, "Reference object's matrix cannot be inverted.")
             return {'CANCELLED'}

        for (ix, iy), transform in grid_cells.items():
            c1, c2, c3, c4 = (ix, iy), (ix + 1, iy), (ix + 1, iy + 1), (ix, iy + 1)
            rc1, rc2, rc3, rc4 = resolve(c1), resolve(c2), resolve(c3), resolve(c4)
            
            if all(c in final_verts for c in [rc1, rc2, rc3, rc4]):
                p1, p2, p3, p4 = final_verts[rc1], final_verts[rc2], final_verts[rc3], final_verts[rc4]
                new_center = (p1 + p2 + p3 + p4) / 4.0
                
                # Project center to surface to get new location, but ignore surface normal
                point_local = target_inv_mtx @ new_center
                success, location_local, _, _ = target_eval.closest_point_on_mesh(point_local)
                
                if success:
                    transform['loc'] = target_eval.matrix_world @ location_local
                    # CRITICAL DIFFERENCE: Apply the single global rotation to all cells
                    transform['rot'] = ref_rot.copy()
                    transform['ideal_rot'] = ref_rot.copy()

        state._vertex_overrides.clear()
        state._needs_update = True
        context.area.tag_redraw()
        self.report({'INFO'}, "Grid flattened.")
        return {'FINISHED'}
class QUICKRETOPO_OT_pin_all_grid_verts(bpy.types.Operator):
    """Toggles pinning for all vertices of the preview grid."""
    bl_idname = "object.quick_retopo_pin_all_grid_verts"
    bl_label = "Pin/Unpin All Vertices"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        return state._handle_3d is not None and len(state._grid_cells) > 0
    def execute(self, context):
        # If there are any pinned vertices, unpin all. Otherwise, pin all.
        if state._pinned_vertices:
            state._pinned_vertices.clear()
            self.report({'INFO'}, "All vertices unpinned.")
        else:
            grid_cells = state._grid_cells
            remap = state._vertex_remap
            overrides = state._vertex_overrides
            size = context.scene.retopo_plane_size

            # We calculate final verts *without* pins to get their dynamic location
            final_verts = utils.calculate_final_verts(grid_cells, size, remap, overrides, {})

            if not final_verts:
                self.report({'WARNING'}, "Could not calculate vertex positions to pin.")
                return {'CANCELLED'}
            
            # Since final_verts keys are resolved, we pin the resolved coordinates
            for v_coord, pos in final_verts.items():
                state._pinned_vertices[v_coord] = pos.copy()

            self.report({'INFO'}, f"Pinned {len(final_verts)} vertices.")

        state._needs_update = True
        context.area.tag_redraw()
        return {'FINISHED'}

classes = (
    QUICKRETOPO_OT_align_grid,
    QUICKRETOPO_OT_align_and_pin_grid,
    QUICKRETOPO_OT_straighten_grid,
    QUICKRETOPO_OT_strong_straighten_grid,
    QUICKRETOPO_OT_pin_all_grid_verts,
)
def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
