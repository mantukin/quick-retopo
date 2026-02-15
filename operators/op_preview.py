import bpy
import gpu
import math
import bmesh
from collections import deque
from mathutils import Vector, Matrix
from mathutils.kdtree import KDTree
from gpu_extras.batch import batch_for_shader
from bpy_extras import view3d_utils

from .. import state
from .. import utils
def draw_callback_3d(self_op, context):
    if not self_op or not self_op.shader:
        return

    # --- Set GPU state for this addon's drawing ---
    if context.scene.retopo_x_ray_mode:
        gpu.state.depth_test_set('NONE')
    else:
        gpu.state.depth_test_set('LESS_EQUAL')
    gpu.state.blend_set('ALPHA')

    try:
        self_op.shader.bind()
        is_shift = self_op.key_state['shift']
        is_ctrl = self_op.key_state['ctrl']
        is_alt = self_op.key_state['alt']

        # --- Draw container meshes ---
        if self_op.batch_container_meshes:
            gpu.state.line_width_set(1.5)
            self_op.shader.uniform_float("color", (0.2, 0.5, 1.0, 0.9)) # Blue color
            for batch in self_op.batch_container_meshes:
                batch.draw(self_op.shader)

        # Draw line being created by user
        if self_op.batch_line:
            gpu.state.line_width_set(3.0)
            self_op.shader.uniform_float("color", (0.2, 0.9, 0.9, 1.0))
            self_op.batch_line.draw(self_op.shader)

        # Draw grid lines
        if self_op.batch_quads_front:
            gpu.state.line_width_set(2.0)
            color = (0.9, 0.7, 0.1, 1.0)
            if context.scene.retopo_x_ray_mode:
                # If in x-ray mode, make lines slightly transparent to reduce clutter
                color = (0.9, 0.7, 0.1, 0.8)
            
            self_op.shader.uniform_float("color", color)
            self_op.batch_quads_front.draw(self_op.shader)

        # Draw pinned vertices (always visible)
        if self_op.batch_pinned_verts:
            gpu.state.point_size_set(8.0)
            self_op.shader.uniform_float("color", (0.8, 0.1, 0.8, 1.0)) # Purple
            self_op.batch_pinned_verts.draw(self_op.shader)

        # --- CTRL or ALT MODE: VERTEX INTERACTION ---
        if is_ctrl or is_alt:
            # Draw all grid vertices
            if self_op.batch_verts:
                gpu.state.point_size_set(5.0)
                self_op.shader.uniform_float("color", (1.0, 0.5, 0.0, 0.8)) # Orange
                self_op.batch_verts.draw(self_op.shader)
            
            # Draw hovered vertex
            if self_op.batch_hover_vertex and state._hovered_vertex_data:
                gpu.state.point_size_set(10.0)
                # Cyan for pin hover, Yellow for move hover
                color = (0.5, 1.0, 1.0, 1.0) if is_alt else (1.0, 1.0, 0.0, 1.0)
                self_op.shader.uniform_float("color", color)
                self_op.batch_hover_vertex.draw(self_op.shader)
            
            # Draw hovered connection icon (only on ALT)
            if is_alt and self_op.batch_hover_connection and state._hovered_connection_data:
                gpu.state.line_width_set(3.0)
                handle = state._hovered_connection_data
                color = (0.2, 0.5, 1.0, 0.5)
                if self_op.mouse_pos:
                    click_radius = context.scene.retopo_arrow_click_radius
                    pos_2d = view3d_utils.location_3d_to_region_2d(context.region, context.space_data.region_3d, handle['pos'])
                    if pos_2d and (self_op.mouse_pos - pos_2d).length < click_radius:
                        color = (0.2, 0.5, 1.0, 1.0)
                self_op.shader.uniform_float("color", color)
                self_op.batch_hover_connection.draw(self_op.shader)

        # --- NORMAL MODE: ADD/DELETE/MOVE ---
        else:
            # Draw hovered center handle (either cross for delete or circle for move)
            if state._hovered_center_data:
                handle = state._hovered_center_data
                click_radius = context.scene.retopo_arrow_click_radius
                is_clickable = False
                if self_op.mouse_pos:
                    pos_2d = view3d_utils.location_3d_to_region_2d(context.region, context.space_data.region_3d, handle['pos'])
                    if pos_2d and (self_op.mouse_pos - pos_2d).length < click_radius:
                        is_clickable = True

                if is_shift:  # DELETE MODE
                    if self_op.batch_hover_cross:
                        gpu.state.line_width_set(3.0)
                        color = (1.0, 0.2, 0.1, 1.0) if is_clickable else (1.0, 0.2, 0.1, 0.4)
                        self_op.shader.uniform_float("color", color)
                        self_op.batch_hover_cross.draw(self_op.shader)
                else:  # MOVE MODE
                    if self_op.batch_hover_move:
                        gpu.state.line_width_set(2.0)
                        color = (0.2, 0.9, 0.9, 1.0) if is_clickable else (0.2, 0.9, 0.9, 0.5)
                        self_op.shader.uniform_float("color", color)
                        self_op.batch_hover_move.draw(self_op.shader)

            # Draw hovered green arrow for adding segments
            if self_op.batch_hover_arrow and state._hovered_arrow_data:
                handle = state._hovered_arrow_data
                color = (0.1, 0.9, 0.2, 0.4)
                if self_op.mouse_pos:
                    click_radius = context.scene.retopo_arrow_click_radius
                    pos_2d = view3d_utils.location_3d_to_region_2d(context.region, context.space_data.region_3d, handle['pos'])
                    if pos_2d and (self_op.mouse_pos - pos_2d).length < click_radius:
                        color = (0.1, 0.9, 0.2, 1.0)
                self_op.shader.uniform_float("color", color)
                self_op.batch_hover_arrow.draw(self_op.shader)

    finally:
        # --- Restore GPU state to Blender defaults ---
        gpu.state.depth_test_set('LESS_EQUAL')
        gpu.state.blend_set('NONE')
        # Reset line width and point size to a sensible default.
        gpu.state.line_width_set(1.0)
        gpu.state.point_size_set(1.0)
class QUICKRETOPO_OT_plane_preview(bpy.types.Operator):
    """Draws an interactive grid of retopology planes in the viewport."""
    bl_idname = "object.quick_retopo_plane_preview"
    bl_label = "Start Drawing Retopo Grid"
    bl_options = {'REGISTER'}

    action: bpy.props.StringProperty(name="Action", default="START")

    state: str
    key_state: dict
    line_point_a: Vector
    line_point_b: Vector
    active_cell: tuple = None
    last_deleted_cell: tuple = None
    active_vertex: tuple = None
    mouse_pos: Vector = None
    initial_move_data: dict = None
    
    shader: None
    batch_quads_front: None
    batch_quads_back: None
    batch_hover_arrow: None
    batch_hover_cross: None
    batch_hover_move: None
    batch_verts: None
    batch_hover_vertex: None
    batch_pinned_verts: None
    batch_hover_connection: None
    batch_line: None
    batch_container_meshes: None
    @classmethod
    def poll(cls, context):
        return utils.quickretopo_poll(cls, context)

    def modal(self, context, event):
        if state._should_stop:
            self.cancel_preview_cleanup()
            state._should_stop = False
            context.area.tag_redraw()
            return {'CANCELLED'}

        if state._needs_update:
            self.update_batches(context)
            state._needs_update = False
        
        if context.area:
            context.area.tag_redraw()

        self.mouse_pos = Vector((event.mouse_region_x, event.mouse_region_y))
        
        old_key_state = self.key_state.copy()
        self.key_state['shift'] = event.shift
        self.key_state['ctrl'] = event.ctrl
        self.key_state['alt'] = event.alt
        if self.key_state != old_key_state:
            self.update_hover_state(context, event)

        if event.type == 'ESC':
            self.cancel_preview_cleanup(report=True)
            return {'CANCELLED'}

        if context.mode != 'OBJECT' or not utils.quickretopo_poll(self, context):
            self.report({'WARNING'}, "Preview conditions are no longer met. Preview cancelled.")
            self.cancel_preview_cleanup()
            return {'CANCELLED'}

        if self.state == 'DRAWING_LINE_START':
            if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
                success, loc, _ = utils.get_mouse_location_on_surface(context, self.mouse_pos)
                if success:
                    self.line_point_a = loc; self.line_point_b = loc
                    self.state = 'DRAWING_LINE_END'
                    self.report({'INFO'}, "Release LMB to finish the line. Mouse Wheel to change size.")
                    self.update_line_and_quad_preview(context)
                else:
                    self.report({'INFO'}, "Could not find a surface under the cursor.")
            return {'RUNNING_MODAL'}

        elif self.state == 'DRAWING_LINE_END':
            if event.type == 'MOUSEMOVE':
                success, loc, _ = utils.get_mouse_location_on_surface(context, self.mouse_pos)
                if success:
                    self.line_point_b = loc
                    self.update_line_and_quad_preview(context)
            
            elif event.type in {'WHEELUPMOUSE', 'WHEELDOWNMOUSE'}:
                step = 0.05 if not event.shift else 0.01
                direction = 1 if event.type == 'WHEELUPMOUSE' else -1
                prop = bpy.types.Scene.bl_rna.properties['retopo_plane_size']
                min_size, max_size = prop.hard_min, prop.soft_max
                new_size = context.scene.retopo_plane_size + (step * direction)
                context.scene.retopo_plane_size = max(min_size, min(new_size, max_size))
                self.update_line_and_quad_preview(context)

            elif event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
                if self.line_point_a and self.line_point_b and (self.line_point_a - self.line_point_b).length > 0.01:
                    self.generate_quad_strip(context)
                    self.state = 'IDLE'
                    self.batch_line = None
                    self.update_batches(context)
                    self.report({'INFO'}, "Grid created. Add/delete segments. ESC to exit.")
                else:
                    self.state = 'DRAWING_LINE_START'; self.line_point_a = self.line_point_b = None
                    self.batch_line = None; state._grid_cells.clear(); self.update_batches(context)
                    self.report({'INFO'}, "Line is too short. Draw a line on the object's surface.")
            return {'RUNNING_MODAL'}

        elif self.state == 'IDLE':
            self.update_hover_state(context, event)

            if event.type in {'WHEELUPMOUSE', 'WHEELDOWNMOUSE'} and event.shift and not event.ctrl:
                if state._hovered_center_data:
                    cell_coord = state._hovered_center_data['cell']
                    if cell_coord in state._grid_cells:
                        cell_data = state._grid_cells[cell_coord]
                        
                        if 'size' not in cell_data:
                            # Initialize 'size' from 'size_mult' for compatibility with older data
                            global_size = context.scene.retopo_plane_size
                            size_mult = cell_data.get('size_mult', 1.0)
                            s = global_size * size_mult
                            cell_data['size'] = Vector((s, s))
                        
                        resize_ratio = context.scene.retopo_resize_ratio
                        ratio = resize_ratio if event.type == 'WHEELUPMOUSE' else (1 / resize_ratio)
                        new_size = cell_data['size'] * ratio
                        
                        # Prevent shrinking to zero or negative
                        if new_size.x >= 0.001 and new_size.y >= 0.001:
                            cell_data['size'] = new_size
                        
                        state._needs_update = True
                return {'RUNNING_MODAL'}

            if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
                click_radius = context.scene.retopo_arrow_click_radius
                
                # Priority: Pin > Vertex Move > Delete > Segment Move > Add > Connect
                if event.alt and not event.shift and not event.ctrl and state._hovered_vertex_data:
                    v_coord = state._hovered_vertex_data['coord']
                    remap = state._vertex_remap
                    def resolve(vc):
                        while vc in remap: vc = remap[vc]
                        return vc
                    
                    resolved_v = resolve(v_coord)
                    if resolved_v in state._pinned_vertices:
                        del state._pinned_vertices[resolved_v]
                        self.report({'INFO'}, f"Vertex {resolved_v} unpinned.")
                    else:
                        current_verts = utils.calculate_final_verts(
                            state._grid_cells, context.scene.retopo_plane_size,
                            state._vertex_remap, state._vertex_overrides, {} # Intentionally ignore pins to get dynamic pos
                        )
                        if resolved_v in current_verts:
                            state._pinned_vertices[resolved_v] = current_verts[resolved_v].copy()
                            self.report({'INFO'}, f"Vertex {resolved_v} pinned.")
                    
                    state._needs_update = True
                    return {'RUNNING_MODAL'}

                if event.ctrl and state._hovered_vertex_data:
                    v_coord = state._hovered_vertex_data['coord']
                    remap = state._vertex_remap
                    def resolve(vc):
                        while vc in remap: vc = remap[vc]
                        return vc
                        
                    self.state = 'MOVING_VERTEX'; self.active_vertex = state._hovered_vertex_data['coord']
                    return {'RUNNING_MODAL'}

                if event.shift and state._hovered_center_data:
                    handle = state._hovered_center_data
                    pos_2d = view3d_utils.location_3d_to_region_2d(context.region, context.space_data.region_3d, handle['pos'])
                    if pos_2d and (self.mouse_pos - pos_2d).length < click_radius:
                        if len(state._grid_cells) > 1:
                            del state._grid_cells[handle['cell']]
                            self.state = 'DELETING'; self.last_deleted_cell = handle['cell']
                            self.update_after_grid_change(context, event)
                        else: self.report({'INFO'}, "Cannot delete the last segment.")
                        return {'RUNNING_MODAL'}
                
                if not event.shift and not event.ctrl and not event.alt and state._hovered_center_data:
                    handle = state._hovered_center_data
                    pos_2d = view3d_utils.location_3d_to_region_2d(context.region, context.space_data.region_3d, handle['pos'])
                    if pos_2d and (self.mouse_pos - pos_2d).length < click_radius:
                        self.state = 'MOVING_SEGMENT'
                        self.active_cell = handle['cell']
                        
                        success_move_start, loc_move_start, _ = utils.get_mouse_location_on_surface(context, self.mouse_pos)
                        if not success_move_start:
                            self.state = 'IDLE'
                            return {'RUNNING_MODAL'}

                        # --- NEW: Build falloff map for smooth move ---
                        def resolve(v_coord):
                            while v_coord in state._vertex_remap: v_coord = state._vertex_remap[v_coord]
                            return v_coord

                        # 1. Build neighbor map for all cells
                        cell_neighbors = {cell: set() for cell in state._grid_cells}
                        all_edges = {}  # edge_tuple -> list of cells
                        for cell_coord in state._grid_cells:
                            ix, iy = cell_coord
                            corners = [(ix, iy), (ix + 1, iy), (ix + 1, iy + 1), (ix, iy + 1)]
                            resolved_corners = [resolve(c) for c in corners]
                            for i in range(4):
                                edge = tuple(sorted((resolved_corners[i], resolved_corners[(i + 1) % 4])))
                                if edge[0] == edge[1]: continue
                                if edge not in all_edges: all_edges[edge] = []
                                all_edges[edge].append(cell_coord)
                        
                        for edge, cells in all_edges.items():
                            if len(cells) > 1:
                                for i in range(len(cells)):
                                    for j in range(i + 1, len(cells)):
                                        cell1, cell2 = cells[i], cells[j]
                                        cell_neighbors[cell1].add(cell2)
                                        cell_neighbors[cell2].add(cell1)

                        # 2. BFS to find affected cells and their depth
                        q = deque([(self.active_cell, 0)])
                        visited_depths = {self.active_cell: 0}
                        max_depth = 2
                        while q:
                            current_cell, depth = q.popleft()
                            if depth < max_depth:
                                for neighbor in cell_neighbors.get(current_cell, []):
                                    if neighbor not in visited_depths:
                                        visited_depths[neighbor] = depth + 1
                                        q.append((neighbor, depth + 1))
                        
                        # 3. Store initial data for the move
                        self.initial_move_data = {
                            'initial_mouse_loc': loc_move_start,
                            'vert_locs': {},
                            'falloff_map': visited_depths
                        }
                        
                        final_verts = utils.calculate_final_verts(
                            state._grid_cells, context.scene.retopo_plane_size, state._vertex_remap, state._vertex_overrides, state._pinned_vertices
                        )
                        
                        # Store initial positions for all original vertices of affected cells
                        for cell_coord in visited_depths:
                            ix, iy = cell_coord
                            corners = [(ix, iy), (ix + 1, iy), (ix + 1, iy + 1), (ix, iy + 1)]
                            for corner_coord in corners:
                                if corner_coord not in self.initial_move_data['vert_locs']:
                                    resolved_v = resolve(corner_coord)
                                    if resolved_v in final_verts:
                                        self.initial_move_data['vert_locs'][corner_coord] = final_verts[resolved_v].copy()
                        
                        return {'RUNNING_MODAL'}

                if state._hovered_arrow_data:
                    handle = state._hovered_arrow_data
                    pos_2d = view3d_utils.location_3d_to_region_2d(context.region, context.space_data.region_3d, handle['pos'])
                    if pos_2d and (self.mouse_pos - pos_2d).length < click_radius:
                        new_cell_coord = self.add_segment(context, handle)
                        if new_cell_coord:
                            self.state = 'ADDING'; self.active_cell = new_cell_coord
                            self.update_after_grid_change(context, event)
                        return {'RUNNING_MODAL'}

                if event.alt and state._hovered_connection_data:
                    handle = state._hovered_connection_data
                    pos_2d = view3d_utils.location_3d_to_region_2d(context.region, context.space_data.region_3d, handle['pos'])
                    if pos_2d and (self.mouse_pos - pos_2d).length < click_radius:
                        self.connect_vertices(context, handle)
                        self.update_after_grid_change(context, event)
                        self.report({'INFO'}, "Vertices connected.")
                        return {'RUNNING_MODAL'}

            return {'PASS_THROUGH'}

        elif self.state == 'ADDING':
            if event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
                self.state = 'IDLE'; self.active_cell = None; return {'RUNNING_MODAL'}
            if event.type == 'MOUSEMOVE':
                success, mouse_loc, _ = utils.get_mouse_location_on_surface(context, self.mouse_pos)
                if not success: return {'RUNNING_MODAL'}
                active_cell_transform = state._grid_cells.get(self.active_cell)
                if not active_cell_transform: self.state = 'IDLE'; return {'RUNNING_MODAL'}
                size = context.scene.retopo_plane_size * active_cell_transform.get('size_mult', 1.0)
                if (mouse_loc - active_cell_transform['loc']).length < size * 0.7: return {'RUNNING_MODAL'}
                direction_vec = (mouse_loc - active_cell_transform['loc']).normalized()
                rot, ix, iy = active_cell_transform['rot'], self.active_cell[0], self.active_cell[1]
                dot_x, dot_y = direction_vec.dot(rot.col[0]), direction_vec.dot(rot.col[1])
                direction = (1, 0) if dot_x > 0 else (-1, 0) if abs(dot_x) > abs(dot_y) else (0, 1) if dot_y > 0 else (0, -1)
                if (ix + direction[0], iy + direction[1]) in state._grid_cells: self.active_cell = (ix + direction[0], iy + direction[1]); return {'RUNNING_MODAL'}
                best_handle = next((h for h in state._potential_arrow_handles if h['cell'] == self.active_cell and h['dir'] == direction), None)
                if best_handle:
                    new_cell_coord = self.add_segment(context, best_handle)
                    if new_cell_coord: self.active_cell = new_cell_coord; self.update_after_grid_change(context, event)
            return {'RUNNING_MODAL'}

        elif self.state == 'DELETING':
            if event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
                self.state = 'IDLE'; self.last_deleted_cell = None; return {'RUNNING_MODAL'}
            if event.type == 'MOUSEMOVE':
                self.update_hover_state(context, event)
                if state._hovered_center_data:
                    handle = state._hovered_center_data
                    cell_coord = handle['cell']
                    if cell_coord != self.last_deleted_cell and cell_coord in state._grid_cells:
                        if len(state._grid_cells) > 1:
                            del state._grid_cells[cell_coord]
                            if cell_coord in state._vertex_overrides: del state._vertex_overrides[cell_coord]
                            self.last_deleted_cell = cell_coord
                            self.update_after_grid_change(context, event)
            return {'RUNNING_MODAL'}

        elif self.state == 'MOVING_SEGMENT':
            if event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
                self.state = 'IDLE'; self.active_cell = None; self.initial_move_data = None
                state._needs_update = True
                return {'RUNNING_MODAL'}
            if event.type == 'MOUSEMOVE':
                if not self.initial_move_data:
                    self.state = 'IDLE'; return {'RUNNING_MODAL'}
                
                success, mouse_loc, _ = utils.get_mouse_location_on_surface(context, self.mouse_pos)
                if success:
                    delta = mouse_loc - self.initial_move_data['initial_mouse_loc']
                    falloff_map = self.initial_move_data['falloff_map']
                    initial_vert_locs = self.initial_move_data['vert_locs']
                    falloff_factors = [1.0, 0.6, 0.3]
                    def resolve(v_coord):
                        while v_coord in state._vertex_remap: v_coord = state._vertex_remap[v_coord]
                        return v_coord
                    
                    overridden_orig_verts = set()
                    
                    # Iterate by depth to apply strongest falloff first
                    for depth in range(len(falloff_factors)):
                        falloff = falloff_factors[depth]
                        for cell_coord, d in falloff_map.items():
                            if d != depth: continue
                            
                            ix, iy = cell_coord
                            corners = [(ix, iy), (ix + 1, iy), (ix + 1, iy + 1), (ix, iy + 1)]
                            
                            for corner_coord in corners:
                                if corner_coord in overridden_orig_verts: continue
                                
                                resolved_v = resolve(corner_coord)
                                if resolved_v in state._pinned_vertices: continue
                                
                                initial_pos = initial_vert_locs.get(corner_coord)
                                if not initial_pos: continue

                                overridden_orig_verts.add(corner_coord)
                                
                                new_pos = initial_pos + delta * falloff
                                
                                original_cell_rot = state._grid_cells[self.active_cell]['rot']
                                proj_loc, _, proj_success = utils.get_surface_transform_at_point(context, new_pos, original_cell_rot)
                                state._vertex_overrides[corner_coord] = proj_loc if proj_success else new_pos

                    for cell_coord in falloff_map:
                        self.update_transforms_for_cell(context, cell_coord)

                    state._needs_update = True
            return {'RUNNING_MODAL'}

        elif self.state == 'MOVING_VERTEX':
            if event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
                # If the moved vertex was pinned, update its pinned position to the new location.
                # Then, remove the temporary override so the vertex is now held by the pin.
                if self.active_vertex:
                    def resolve(vc):
                        while vc in state._vertex_remap: vc = state._vertex_remap[vc]
                        return vc
                    
                    resolved_v = resolve(self.active_vertex)
                    # If the vertex was pinned, its pinned position is updated to the new location.
                    # The override will persist, making the move "stick" until a global operation like
                    # "Straighten" is performed, which clears all overrides.
                    if resolved_v in state._pinned_vertices:
                        new_pos = state._vertex_overrides.get(self.active_vertex)
                        if new_pos:
                            state._pinned_vertices[resolved_v] = new_pos.copy()
                
                self.state = 'IDLE'
                self.active_vertex = None
                state._needs_update = True
                return {'RUNNING_MODAL'}
                
            if event.type == 'MOUSEMOVE':
                if self.active_vertex:
                    success, loc, _ = utils.get_mouse_location_on_surface(context, self.mouse_pos)
                    if success:
                        state._vertex_overrides[self.active_vertex] = loc
                        # self.update_affected_cell_transforms(context, self.active_vertex)
                        state._needs_update = True
            return {'RUNNING_MODAL'}

        return {'PASS_THROUGH'}
    def update_transforms_for_cell(self, context, cell_coord):
        grid_cells, remap = state._grid_cells, state._vertex_remap
        
        def resolve(v_coord):
            while v_coord in remap: v_coord = remap[v_coord]
            return v_coord
            
        final_verts = utils.calculate_final_verts(
            grid_cells, context.scene.retopo_plane_size, remap, state._vertex_overrides, state._pinned_vertices
        )
        
        transform = grid_cells.get(cell_coord)
        if not transform: return
        
        ix, iy = cell_coord
        corners = [(ix, iy), (ix + 1, iy), (ix + 1, iy + 1), (ix, iy + 1)]
        resolved_corners = [resolve(c) for c in corners]
        
        if all(c in final_verts for c in resolved_corners):
            # Get current vertex positions in order: bottom-left, bottom-right, top-right, top-left
            p_bl = final_verts[resolved_corners[0]]
            p_br = final_verts[resolved_corners[1]]
            p_tr = final_verts[resolved_corners[2]]
            p_tl = final_verts[resolved_corners[3]]

            new_center = (p_bl + p_br + p_tr + p_tl) / 4.0

            # Calculate a new guide rotation from the quad's current edges. This is
            # more robust than using the old, potentially stale, rotation matrix.
            avg_x_dir = (p_br - p_bl) + (p_tr - p_tl)
            avg_y_dir = (p_tl - p_bl) + (p_tr - p_br)
            
            new_guide_rot = Matrix.Identity(3)
            # Using length_squared is slightly more efficient.
            if avg_x_dir.length_squared > 1e-12:
                new_guide_rot.col[0] = avg_x_dir.normalized()
            if avg_y_dir.length_squared > 1e-12:
                new_guide_rot.col[1] = avg_y_dir.normalized()

            loc, rot, success = utils.get_surface_transform_at_point(context, new_center, new_guide_rot)
            
            if success:
                transform['loc'] = loc
                transform['rot'] = rot
    def update_affected_cell_transforms(self, context, moved_v_coord):
        grid_cells, remap = state._grid_cells, state._vertex_remap
        def resolve(v_coord):
            while v_coord in remap: v_coord = remap[v_coord]
            return v_coord
        
        resolved_moved_v = resolve(moved_v_coord)
        vx, vy = resolved_moved_v
        
        possible_cell_coords = [
            (vx, vy), (vx - 1, vy),
            (vx - 1, vy - 1), (vx, vy - 1)
        ]
        
        for cell_coord in possible_cell_coords:
            if cell_coord in grid_cells:
                self.update_transforms_for_cell(context, cell_coord)
    def add_segment(self, context, handle):
        # --- Handle adding a segment from a reference mesh in the container ---
        if handle.get('type') == 'reference':
            max_ix = -2  # Start at -2, so +2 gives a starting index of 0
            if state._grid_cells:
                try:
                    # Find the right-most coordinate used by any cell to avoid overlaps
                    max_ix = max(k[0] for k in state._grid_cells.keys())
                except ValueError:
                    pass  # Grid exists but is empty
            
            new_cell_coord = (max_ix + 2, 0)
            
            # Data is pre-calculated and stored in the handle by update_batches
            new_loc = handle['new_cell_loc']
            new_rot = handle['new_cell_rot']
            new_size = handle['new_cell_size'] # This is a float from the edge length
            
            # Create a square quad based on the edge length
            cell_size_vec = Vector((new_size, new_size))
            new_cell_data = {'loc': new_loc, 'rot': new_rot, 'ideal_rot': new_rot.copy(), 'size': cell_size_vec}
            state._grid_cells[new_cell_coord] = new_cell_data
            
            return new_cell_coord

        # --- Handle adding a segment from the active (orange) grid ---
        new_cell_coord = (handle['cell'][0] + handle['dir'][0], handle['cell'][1] + handle['dir'][1])
        if new_cell_coord in state._grid_cells: return None

        parent_coord = handle['cell']
        parent_transform = state._grid_cells[parent_coord]

        # --- Start: Calculate a more accurate current rotation for the parent quad ---
        def resolve(v_coord):
            # Local helper to resolve remapped vertices
            while v_coord in state._vertex_remap:
                v_coord = state._vertex_remap[v_coord]
            return v_coord
        
        final_verts = utils.calculate_final_verts(
            state._grid_cells, context.scene.retopo_plane_size, state._vertex_remap, state._vertex_overrides, state._pinned_vertices
        )
        
        ix, iy = parent_coord
        corners = [(ix, iy), (ix + 1, iy), (ix + 1, iy + 1), (ix, iy + 1)]
        resolved_corners = [resolve(c) for c in corners]

        parent_guide_rot = parent_transform['rot'].copy()  # Use old rot as a fallback
        
        # --- Start: Inherit REAL size from parent's current vertex positions ---
        new_cell_size = None
        if all(c in final_verts for c in resolved_corners):
            p_bl = final_verts[resolved_corners[0]]
            p_br = final_verts[resolved_corners[1]]
            p_tr = final_verts[resolved_corners[2]]
            p_tl = final_verts[resolved_corners[3]]
            
            # Derive orientation from the actual edges of the deformed quad
            avg_x_dir = (p_br - p_bl) + (p_tr - p_tl)
            avg_y_dir = (p_tl - p_bl) + (p_tr - p_br)
            
            # Create a guide matrix. It doesn't need to be perfectly orthonormal,
            # get_surface_transform_at_point will fix it based on the surface normal.
            guide_rot = Matrix.Identity(3)
            if avg_x_dir.length_squared > 1e-12:
                guide_rot.col[0] = avg_x_dir.normalized()
            if avg_y_dir.length_squared > 1e-12:
                guide_rot.col[1] = avg_y_dir.normalized()
            parent_guide_rot = guide_rot
            
            # Calculate actual average width and height from edges
            width1 = (p_br - p_bl).length
            width2 = (p_tr - p_tl).length
            avg_width = (width1 + width2) / 2.0
            
            height1 = (p_tl - p_bl).length
            height2 = (p_tr - p_br).length
            avg_height = (height1 + height2) / 2.0
            
            if avg_width > 0.001 and avg_height > 0.001:
                new_cell_size = Vector((avg_width, avg_height))

        # --- Fallback to stored size if real size calculation fails ---
        if new_cell_size is None:
            parent_size_prop = parent_transform.get('size')
            if not parent_size_prop:
                # Fallback for compatibility with older data format
                global_size = context.scene.retopo_plane_size
                size_mult = parent_transform.get('size_mult', 1.0)
                s = global_size * size_mult
                parent_size_prop = Vector((s, s))
            new_cell_size = parent_size_prop.copy()
        
        # The extrusion distance depends on the new cell's size (inherited from parent's actual shape).
        # If extruding along grid X (dir[0] != 0), use new cell's X size.
        # If extruding along grid Y (dir[1] != 0), use new cell's Y size.
        extrusion_dist = new_cell_size.x if handle['dir'][0] != 0 else new_cell_size.y

        extrusion_dir_world = (handle['pos'] - parent_transform['loc']).normalized()
        estimated_pos_world = handle['pos'] + extrusion_dir_world * (extrusion_dist / 2.0)

        # Determine which axis to preserve to prevent twisting.
        # If we extrude along the grid's Y-axis (up/down), we preserve the X-axis of the parent.
        # If we extrude along the grid's X-axis (left/right), we preserve the Y-axis.
        axis_to_preserve = 'X' if handle['dir'][0] == 0 else 'Y'
        new_loc, new_rot, success = utils.get_surface_transform_at_point(
            context, estimated_pos_world, parent_guide_rot, preserve_axis_of_parent=axis_to_preserve
        )

        if success:
            new_cell_data = {'loc': new_loc, 'rot': new_rot, 'ideal_rot': new_rot.copy(), 'size': new_cell_size}
        else:
            # Fallback if projection fails
            new_cell_data = { 'loc': estimated_pos_world, 'rot': parent_guide_rot.copy(), 'ideal_rot': parent_guide_rot.copy(), 'size': new_cell_size }

        state._grid_cells[new_cell_coord] = new_cell_data
        
        return new_cell_coord
    def connect_vertices(self, context, handle):
        remap = state._vertex_remap
        grid_cells = state._grid_cells
        overrides = state._vertex_overrides
        pinned = state._pinned_vertices
        
        def resolve(v_coord):
            # Safe resolve to prevent infinite loops on broken remaps
            path = {v_coord}
            while v_coord in remap:
                v_coord = remap.get(v_coord)
                if v_coord is None or v_coord in path: return None
                path.add(v_coord)
            return v_coord

        r1, r2 = resolve(handle['v1']), resolve(handle['v2'])
        if r1 is None or r2 is None or r1 == r2:
            return

        # Calculate positions BEFORE merge to determine the new center
        current_verts = utils.calculate_final_verts(
            grid_cells, context.scene.retopo_plane_size, remap, overrides, pinned
        )
        
        pos1 = current_verts.get(r1)
        pos2 = current_verts.get(r2)

        if pos1 is None or pos2 is None:
            self.report({'WARNING'}, "Could not find vertices to merge.")
            return

        is_r1_pinned, is_r2_pinned = r1 in pinned, r2 in pinned
        if is_r1_pinned and is_r2_pinned:
            self.report({'INFO'}, "Cannot merge two pinned vertices.")
            return

        # Determine which vertex merges into which
        if is_r1_pinned:
            r_to, r_from = r1, r2
            new_pos = pos1 # Pinned vertex dictates position
        elif is_r2_pinned:
            r_to, r_from = r2, r1
            new_pos = pos2 # Pinned vertex dictates position
        else:
            r_to, r_from = min(r1, r2), max(r1, r2)
            new_pos = (pos1 + pos2) / 2.0

        # Before creating the new remap, clear any existing overrides that affect the vertices being merged.
        for v_orig in list(overrides.keys()):
            if resolve(v_orig) in (r_from, r_to):
                del overrides[v_orig]

        remap[r_from] = r_to
        overrides[r_to] = new_pos
    def is_occluded(self, context, point_3d):
        """Checks if a 3D point is occluded by the target object from the current view."""
        if not context.scene.retopo_prevent_click_through:
            return False

        target_object = context.view_layer.objects.active
        if not target_object:
            return False

        region = context.region
        rv3d = context.space_data.region_3d

        pos_2d = view3d_utils.location_3d_to_region_2d(region, rv3d, point_3d)
        if pos_2d is None:
            return True

        ray_origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, pos_2d)
        ray_vector = view3d_utils.region_2d_to_vector_3d(region, rv3d, pos_2d)

        depsgraph = context.evaluated_depsgraph_get()
        target_eval = target_object.evaluated_get(depsgraph)

        try:
            matrix_inv = target_eval.matrix_world.inverted()
        except ValueError:
            return False # Un-invertible matrix, can't perform check
            
        ray_origin_local = matrix_inv @ ray_origin
        ray_direction_local = (matrix_inv.to_3x3() @ ray_vector).normalized()

        success, loc, _, _ = target_eval.ray_cast(ray_origin_local, ray_direction_local)
        
        if success:
            hit_pos_world = target_eval.matrix_world @ loc
            dist_to_hit = (hit_pos_world - ray_origin).length
            dist_to_handle = (point_3d - ray_origin).length
            
            epsilon = context.scene.retopo_draw_offset * 1.5 
            if dist_to_hit < dist_to_handle - epsilon:
                return True
        
        return False
    def update_after_grid_change(self, context, event):
        # Helper function to safely resolve vertex remaps and prevent infinite loops
        def safe_resolve(v_coord, remap_dict):
            path = {v_coord}
            while v_coord in remap_dict:
                v_coord = remap_dict.get(v_coord)
                if v_coord is None or v_coord in path: return None
                path.add(v_coord)
            return v_coord

        # --- Start of state cleanup to prevent "old buffer" issues ---
        if not state._grid_cells:
            state._vertex_remap.clear()
            state._vertex_overrides.clear()
            state._pinned_vertices.clear()
        else:
            # 1. Get all original vertex coordinates that are still part of the grid.
            all_active_coords = set()
            for ix, iy in state._grid_cells.keys():
                all_active_coords.add((ix, iy)); all_active_coords.add((ix + 1, iy))
                all_active_coords.add((ix + 1, iy + 1)); all_active_coords.add((ix, iy + 1))

            # 2. Clean up overrides for vertices that no longer exist.
            #    (Keys in _vertex_overrides are original, unresolved coordinates).
            overrides_to_del = [k for k in state._vertex_overrides if k not in all_active_coords]
            for k in overrides_to_del: del state._vertex_overrides[k]
            
            # 3. Get a set of all *resolved* coordinates that are still active.
            all_active_resolved_coords = {safe_resolve(c, state._vertex_remap) for c in all_active_coords}
            # Remove None in case of broken remap chains
            all_active_resolved_coords.discard(None)

            # 4. Clean up pins for vertices that no longer exist.
            #    (Keys in _pinned_vertices are already resolved coordinates).
            pins_to_del = [k for k in state._pinned_vertices if k not in all_active_resolved_coords]
            for k in pins_to_del: del state._pinned_vertices[k]

            # 5. Clean up remaps that point to or from non-existent vertices.
            old_remap = state._vertex_remap.copy()
            valid_remap = {}
            for k, v in old_remap.items():
                # The key 'k' must be an active original coordinate.
                if k in all_active_coords:
                    # The final destination of 'k' must be an active resolved coordinate.
                    final_dest = safe_resolve(k, old_remap)
                    if final_dest is not None and final_dest in all_active_resolved_coords:
                        valid_remap[k] = v
            
            state._vertex_remap.clear()
            state._vertex_remap.update(valid_remap)
        # --- End of state cleanup ---

        state._hovered_arrow_data = state._hovered_center_data = state._hovered_vertex_data = state._hovered_connection_data = None
        self.batch_hover_arrow = self.batch_hover_cross = self.batch_hover_move = self.batch_hover_vertex = self.batch_hover_connection = None
        self.batch_quads_front = self.batch_quads_back = None
        self.update_batches(context)
        self.update_hover_state(context, event)
    def update_hover_state(self, context, event):
        mouse_pos = self.mouse_pos
        is_ctrl = self.key_state['ctrl']
        is_alt = self.key_state['alt']
        radius = context.scene.retopo_arrow_radius
        
        # Reset all hover data
        state._hovered_arrow_data = None; state._hovered_center_data = None
        state._hovered_vertex_data = None; state._hovered_connection_data = None

        if is_ctrl or is_alt: # VERTEX EDIT, PINNING, OR MERGING
            # --- Find closest vertex handle ---
            found_vertex_handle = None
            min_dist_vert = context.scene.retopo_arrow_click_radius * 1.5
            closest_vert_dist = float('inf')
            
            for handle in state._vertex_handles:
                pos_2d = view3d_utils.location_3d_to_region_2d(context.region, context.space_data.region_3d, handle['pos'])
                if pos_2d:
                    dist = (mouse_pos - pos_2d).length
                    if dist < min_dist_vert and dist < closest_vert_dist:
                        if not self.is_occluded(context, handle['pos']):
                            closest_vert_dist = dist; found_vertex_handle = handle
            
            # --- Find closest connection handle (only on ALT) ---
            found_conn_handle = None
            closest_conn_dist = float('inf')
            if is_alt:
                for handle in state._potential_connection_handles:
                    pos_2d = view3d_utils.location_3d_to_region_2d(context.region, context.space_data.region_3d, handle['pos'])
                    if pos_2d and (dist := (mouse_pos - pos_2d).length) < radius and dist < closest_conn_dist:
                        if not self.is_occluded(context, handle['pos']):
                            closest_conn_dist = dist; found_conn_handle = handle

            # --- Prioritize: vertex is more specific than connection ---
            if found_vertex_handle:
                state._hovered_vertex_data = found_vertex_handle
            elif found_conn_handle:
                state._hovered_connection_data = found_conn_handle
            
            # Update batches for whatever was found (or not found)
            self.update_hover_vertex_batch(context)
            self.update_hover_connection_batch(context)

        else: # NORMAL MODE (ADD/DELETE/MOVE)
            # Arrow handles
            found_arrow_handle = None; closest_arrow_dist = float('inf')
            for handle in state._potential_arrow_handles:
                pos_2d = view3d_utils.location_3d_to_region_2d(context.region, context.space_data.region_3d, handle['pos'])
                if pos_2d and (dist := (mouse_pos - pos_2d).length) < radius and dist < closest_arrow_dist:
                    if not self.is_occluded(context, handle['pos']):
                        closest_arrow_dist = dist; found_arrow_handle = handle
            if found_arrow_handle != state._hovered_arrow_data:
                state._hovered_arrow_data = found_arrow_handle; self.update_hover_arrow_batch(context)
            
            # Center handles
            found_center_handle = None; closest_center_dist = float('inf')
            for handle in state._center_handles:
                pos_2d = view3d_utils.location_3d_to_region_2d(context.region, context.space_data.region_3d, handle['pos'])
                if pos_2d and (dist := (mouse_pos - pos_2d).length) < radius and dist < closest_center_dist:
                    if not self.is_occluded(context, handle['pos']):
                        closest_center_dist = dist; found_center_handle = handle
            if found_center_handle != state._hovered_center_data:
                state._hovered_center_data = found_center_handle; self.update_hover_center_batches(context)
    def update_hover_arrow_batch(self, context):
        self.batch_hover_arrow = None
        if not (handle := state._hovered_arrow_data): return
        size = handle.get('edge_length', context.scene.retopo_plane_size) * 0.2

        arrow_dir = handle['arrow_dir']
        edge_dir = handle['edge_vec']

        base_pos = handle['pos']
        tip = base_pos + arrow_dir * size
        # The wings should be parallel to the edge.
        wing_base = base_pos - arrow_dir * (size * 0.5)
        wing1 = wing_base + edge_dir * (size * 0.5)
        wing2 = wing_base - edge_dir * (size * 0.5)
        
        self.batch_hover_arrow = batch_for_shader(self.shader, 'TRIS', {"pos": [tip, wing1, wing2]}, indices=[(0, 1, 2)])
    def update_hover_center_batches(self, context):
        self.batch_hover_cross = self.batch_hover_move = None
        if not (handle := state._hovered_center_data): return
        
        size = handle.get('size', context.scene.retopo_plane_size)
        center, rot = handle['pos'], handle['rot']
        
        # Cross batch
        cross_size = size * 0.15
        x_off, y_off = rot.col[0] * cross_size, rot.col[1] * cross_size
        verts = [center - x_off - y_off, center + x_off + y_off, center - x_off + y_off, center + x_off - y_off]
        self.batch_hover_cross = batch_for_shader(self.shader, 'LINES', {"pos": verts}, indices=[(0, 1), (2, 3)])
        
        # Move (circle) batch
        move_radius = size * 0.12
        segments = 12
        verts = [(center + rot @ Vector((math.cos(a:=(2*math.pi*i/segments))*move_radius, math.sin(a)*move_radius, 0))) for i in range(segments)]
        indices = [(i, (i + 1) % segments) for i in range(segments)]
        self.batch_hover_move = batch_for_shader(self.shader, 'LINES', {"pos": verts}, indices=indices)
    def update_hover_vertex_batch(self, context):
        self.batch_hover_vertex = None
        if not (handle := state._hovered_vertex_data): return
        self.batch_hover_vertex = batch_for_shader(self.shader, 'POINTS', {"pos": [handle['pos']]})

    def update_hover_connection_batch(self, context):
        self.batch_hover_connection = None
        if not (handle := state._hovered_connection_data): return
        size = handle.get('dist', context.scene.retopo_plane_size) * 0.2
        center = handle['pos']
        _, rot, success = utils.get_surface_transform_at_point(context, center, Matrix.Identity(3))
        if not success: rot = Matrix.Identity(3)
        x_off, y_off = rot.col[0] * size, rot.col[1] * size
        verts = [center + x_off, center + y_off, center - x_off, center - y_off]
        self.batch_hover_connection = batch_for_shader(self.shader, 'LINES', {"pos": verts}, indices=[(0, 1), (1, 2), (2, 3), (3, 0)])
    def invoke(self, context, event):
        if context.area.type != 'VIEW_3D': self.report({'WARNING'}, "Active window must be a 3D View."); return {'CANCELLED'}
        if state._handle_3d is not None:
            if self.action == 'DELETE': state.clear_preview_state(); context.area.tag_redraw(); self.report({'INFO'}, "Grid deleted."); return {'CANCELLED'}
            else: state._should_stop = True; context.area.tag_redraw(); return {'CANCELLED'}
        
        state.clear_preview_state()
        self.batch_quads_front = self.batch_quads_back = self.batch_hover_arrow = self.batch_hover_cross = self.batch_hover_move = self.batch_verts = self.batch_hover_vertex = self.batch_pinned_verts = self.batch_hover_connection = self.batch_line = None
        self.batch_container_meshes = []
        self.active_cell = self.last_deleted_cell = self.active_vertex = self.mouse_pos = self.initial_move_data = None
        self.key_state = {'shift': event.shift, 'ctrl': event.ctrl, 'alt': event.alt}
        
        if self.action == 'START_REFERENCE':
            if not context.scene.retopo_container_items:
                self.report({'WARNING'}, "Container is empty. Add a mesh to start from.")
                return {'CANCELLED'}
            state._reference_mode_active = True
            self.state = 'IDLE'
            self.report({'INFO'}, "Click on a boundary edge of a blue mesh to add a new segment.")
        else:  # Default 'START' action
            state._reference_mode_active = False
            self.state = 'DRAWING_LINE_START'
            self.line_point_a = self.line_point_b = None
            self.report({'INFO'}, "Draw a line on the object's surface by holding LMB.")

        # Compatibility fix for Blender 4.0+ shader name changes
        shader_name = 'UNIFORM_COLOR' if bpy.app.version >= (4, 0, 0) else '3D_UNIFORM_COLOR'
        self.shader = gpu.shader.from_builtin(shader_name)
        
        # Build batches for container meshes
        depsgraph = context.evaluated_depsgraph_get()
        for item in context.scene.retopo_container_items:
            obj = item.obj
            if not obj or obj.type != 'MESH' or not obj.visible_get():
                continue
            
            obj_eval = obj.evaluated_get(depsgraph)
            mesh = None
            try:
                mesh = obj_eval.to_mesh()
                if not mesh or not mesh.edges:
                    continue
                
                matrix = obj.matrix_world
                verts_world = [matrix @ v.co for v in mesh.vertices]
                edges = [e.vertices[:] for e in mesh.edges]

                batch = batch_for_shader(self.shader, 'LINES', {"pos": verts_world}, indices=edges)
                self.batch_container_meshes.append(batch)
            finally:
                if mesh:
                    obj_eval.to_mesh_clear()
        
        state._handle_3d = bpy.types.SpaceView3D.draw_handler_add(draw_callback_3d, (self, context), 'WINDOW', 'POST_VIEW')
        context.window_manager.modal_handler_add(self)
        
        # Initial update to show reference handles if needed
        if state._reference_mode_active:
            self.update_batches(context)
            
        return {'RUNNING_MODAL'}
    def generate_quad_strip(self, context):
        state._grid_cells.clear(); state._vertex_remap.clear(); state._vertex_overrides.clear(); state._pinned_vertices.clear()
        if not self.line_point_a or not self.line_point_b: return
        size, vec = context.scene.retopo_plane_size, self.line_point_b - self.line_point_a
        if (length := vec.length) < 0.01 or size < 0.01: return
        num_quads = max(1, int(length / size))
        direction, last_rot = vec.normalized(), None
        for i in range(num_quads):
            center_pos = self.line_point_a + direction * (size * (i + 0.5))
            loc, rot, success = utils.get_strip_quad_transform(context, center_pos, direction, last_rot)
            if success:
                cell_size = Vector((size, size))
                state._grid_cells[(i, 0)] = {'loc': loc, 'rot': rot, 'ideal_rot': rot.copy(), 'size': cell_size}
                last_rot = rot.copy()
    def update_line_and_quad_preview(self, context):
        self.batch_line = batch_for_shader(self.shader, 'LINES', {"pos": [self.line_point_a, self.line_point_b]}) if self.line_point_a and self.line_point_b else None
        self.generate_quad_strip(context)
        self.update_batches(context)

    def update_batches(self, context):
        size, offset = context.scene.retopo_plane_size, context.scene.retopo_draw_offset
        grid_cells, remap, overrides, pinned = state._grid_cells, state._vertex_remap, state._vertex_overrides, state._pinned_vertices
        
        def resolve(v_coord):
            while v_coord in remap: v_coord = remap[v_coord]
            return v_coord
        
        state._potential_arrow_handles.clear(); state._center_handles.clear(); state._vertex_handles.clear(); state._potential_connection_handles.clear()

        final_verts = utils.calculate_final_verts(grid_cells, size, remap, overrides, pinned)
        
        # This check is now more complex. If there are no final_verts, we might still need to draw
        # reference handles. So we don't return early, but parts of the code must handle empty final_verts.
        if not final_verts:
            self.batch_quads_front = self.batch_quads_back = self.batch_verts = self.batch_pinned_verts = None
            # Do not return yet, proceed to reference handle generation.

        # --- 1. Create vertex list (only if there's an active grid) ---
        verts_list, vert_indices_map = [], {}
        if final_verts:
            for v_coord in sorted(final_verts.keys()):
                vert_indices_map[v_coord] = len(verts_list)
                verts_list.append(final_verts[v_coord])

        # --- 2. Calculate transforms and normals (only if there's an active grid) ---
        draw_transforms = {}
        if final_verts:
            for (ix, iy), transform in grid_cells.items():
                corners = [(ix, iy), (ix + 1, iy), (ix + 1, iy + 1), (ix, iy + 1)]
                resolved_corners = [resolve(c) for c in corners]
                if all(c in final_verts for c in resolved_corners):
                    p_bl,p_br,p_tr,p_tl = (final_verts[c] for c in resolved_corners)
                    center_pos = (p_bl + p_br + p_tr + p_tl) / 4.0
                    avg_x_dir = (p_br - p_bl) + (p_tr - p_tl)
                    avg_y_dir = (p_tl - p_bl) + (p_tr - p_br)
                    guide_rot = Matrix.Identity(3)
                    if avg_x_dir.length_squared > 1e-12: guide_rot.col[0] = avg_x_dir.normalized()
                    if avg_y_dir.length_squared > 1e-12: guide_rot.col[1] = avg_y_dir.normalized()
                    loc, rot, success = utils.get_surface_transform_at_point(context, center_pos, guide_rot)
                    draw_transforms[(ix, iy)] = {'loc': loc, 'rot': rot} if success else {'loc': center_pos, 'rot': guide_rot}
                else:
                    draw_transforms[(ix, iy)] = {'loc': transform['loc'], 'rot': transform['rot']}

        # --- 3. Create batch for all grid lines (only if there's an active grid) ---
        edge_counts = {}
        if final_verts:
            all_edge_indices = set()
            for ix, iy in grid_cells.keys():
                corners = [(ix, iy), (ix + 1, iy), (ix + 1, iy + 1), (ix, iy + 1)]
                resolved_corners = [resolve(c) for c in corners]
                if all(c in vert_indices_map for c in resolved_corners):
                    indices = [vert_indices_map[c] for c in resolved_corners]
                    quad_edges = {tuple(sorted((indices[i], indices[(i + 1) % 4]))) for i in range(4) if indices[i] != indices[(i + 1) % 4]}
                    all_edge_indices.update(quad_edges)

                    edge_coords_list = [tuple(sorted((resolved_corners[i], resolved_corners[(i+1)%4]))) for i in range(4)]
                    for edge in edge_coords_list:
                        if edge[0] != edge[1]: edge_counts[edge] = edge_counts.get(edge, 0) + 1
            
            self.batch_quads_front = batch_for_shader(self.shader, 'LINES', {"pos": verts_list}, indices=list(all_edge_indices)) if all_edge_indices else None
            self.batch_quads_back = None

        # --- 4. Calculate normals needed for offsetting (only if there's an active grid) ---
        vertex_normals = {}
        if final_verts:
            for v_coord in final_verts:
                vx, vy = v_coord
                possible_cell_coords = [(vx, vy-1), (vx-1, vy-1), (vx-1, vy), (vx, vy)]
                avg_normal = Vector(); count = 0
                for cell_coord in possible_cell_coords:
                    if cell_coord in draw_transforms:
                        avg_normal += draw_transforms[cell_coord]['rot'].col[2]
                        count += 1
                if count > 0: vertex_normals[v_coord] = avg_normal.normalized()

        # --- 5. Create offset geometry batches and handles for active grid ---
        if final_verts:
            offset_verts_list = []
            for v_coord in sorted(final_verts.keys()):
                pos = final_verts[v_coord]
                normal = vertex_normals.get(v_coord)
                offset_pos = pos + normal * offset if normal else pos
                offset_verts_list.append(offset_pos)
                state._vertex_handles.append({'pos': offset_pos, 'coord': v_coord})
            self.batch_verts = batch_for_shader(self.shader, 'POINTS', {"pos": offset_verts_list}) if offset_verts_list else None

            offset_pinned_verts = []
            for v_coord, pos in pinned.items():
                normal = vertex_normals.get(v_coord)
                offset_pos = pos + normal * offset if normal else pos
                offset_pinned_verts.append(offset_pos)
            self.batch_pinned_verts = batch_for_shader(self.shader, 'POINTS', {"pos": offset_pinned_verts}) if offset_pinned_verts else None

            for (ix, iy), d_transform in draw_transforms.items():
                normal = d_transform['rot'].col[2]
                offset_loc = d_transform['loc'] + normal * offset
                
                # --- START: Calculate actual segment size for icon scaling ---
                corners = [(ix, iy), (ix + 1, iy), (ix + 1, iy + 1), (ix, iy + 1)]
                resolved_corners = [resolve(c) for c in corners]
                avg_size = size # Fallback to global size
                if all(c in final_verts for c in resolved_corners):
                    p_bl, p_br, p_tr, p_tl = (final_verts[c] for c in resolved_corners)
                    width = ((p_br - p_bl).length + (p_tr - p_tl).length) / 2.0
                    height = ((p_tl - p_bl).length + (p_tr - p_br).length) / 2.0
                    avg_size = (width + height) / 2.0
                # --- END ---
                
                state._center_handles.append({'pos': offset_loc, 'rot': d_transform['rot'], 'cell': (ix, iy), 'size': avg_size})

                for d, v1c_tpl, v2c_tpl in [
                    ((1, 0), (ix + 1, iy), (ix + 1, iy + 1)), ((-1, 0), (ix, iy + 1), (ix, iy)),
                    ((0, 1), (ix + 1, iy + 1), (ix, iy + 1)), ((0, -1), (ix, iy), (ix + 1, iy))
                ]:
                    v1c, v2c = resolve(v1c_tpl), resolve(v2c_tpl)
                    edge_key = tuple(sorted((v1c, v2c)))
                    if edge_counts.get(edge_key, 0) == 1 and v1c in final_verts and v2c in final_verts:
                        p1, p2 = final_verts[v1c], final_verts[v2c]
                        edge_vec = p2 - p1
                        edge_length = edge_vec.length
                        if edge_length < 1e-6: continue
                        
                        mid_pos = (p1 + p2) / 2.0
                        offset_mid_pos = mid_pos + normal * offset

                        surface_normal = d_transform['rot'].col[2]
                        arrow_dir = edge_vec.cross(surface_normal).normalized()
                        state._potential_arrow_handles.append({
                            'pos': offset_mid_pos, 'dir': d, 'cell': (ix, iy),
                            'arrow_dir': arrow_dir, 'edge_vec': edge_vec.normalized(),
                            'edge_length': edge_length
                        })

            all_v_coords = set(final_verts.keys())
            if len(all_v_coords) > 1:
                all_v_list = list(all_v_coords)
                kd = KDTree(len(all_v_list)); [kd.insert(final_verts[v_coord], i) for i, v_coord in enumerate(all_v_list)]; kd.balance()
                merge_threshold, processed_pairs = size * 0.75, set()
                for i, v_coord1 in enumerate(all_v_list):
                    for _, index, _ in kd.find_range(final_verts[v_coord1], merge_threshold):
                        v_coord2 = all_v_list[index]
                        if v_coord1 == v_coord2: continue
                        pair = tuple(sorted((v_coord1, v_coord2)))
                        if pair in processed_pairs or pair in edge_counts: continue
                        processed_pairs.add(pair)
                        
                        pos1 = final_verts[v_coord1]
                        pos2 = final_verts[v_coord2]
                        dist_between = (pos1 - pos2).length
                        
                        mid_pos = (pos1 + pos2) / 2.0
                        n1, n2 = vertex_normals.get(v_coord1), vertex_normals.get(v_coord2)
                        normal = (n1 + n2).normalized() if n1 and n2 else None
                        if not normal:
                            _, rot, success = utils.get_surface_transform_at_point(context, mid_pos, Matrix.Identity(3))
                            if success: normal = rot.col[2]
                        
                        offset_mid_pos = mid_pos + normal * offset if normal else mid_pos
                        state._potential_connection_handles.append({'pos': offset_mid_pos, 'v1': v_coord1, 'v2': v_coord2, 'dist': dist_between})

        # --- 6. Generate handles for reference meshes in the container ---
        if state._reference_mode_active:
            depsgraph = context.evaluated_depsgraph_get()
            for item in context.scene.retopo_container_items:
                obj = item.obj
                if not obj or obj.type != 'MESH' or not obj.visible_get(): continue
                
                obj_eval = obj.evaluated_get(depsgraph)
                mesh = None
                try:
                    mesh = obj_eval.to_mesh()
                    if not mesh or not mesh.edges: continue
                    
                    bm = bmesh.new(); bm.from_mesh(mesh)
                    bm.edges.ensure_lookup_table(); bm.faces.ensure_lookup_table()
                    
                    matrix = obj.matrix_world
                    matrix_normal = matrix.inverted().transposed().to_3x3()

                    for edge in bm.edges:
                        if not edge.is_boundary or not edge.link_faces: continue
                        face = edge.link_faces[0]
                        
                        # --- Get consistent edge direction from the face's loop winding ---
                        edge_dir_local = None
                        for loop in face.loops:
                            if loop.edge == edge:
                                edge_dir_local = loop.link_loop_next.vert.co - loop.vert.co
                                break
                        
                        if edge_dir_local is None: # Fallback
                            edge_dir_local = edge.verts[1].co - edge.verts[0].co

                        # --- Calculate a guaranteed outward-pointing vector, robust to flipped normals ---
                        # 1. Vector from edge center to face center always points "inward" relative to the edge.
                        edge_center_local = (edge.verts[0].co + edge.verts[1].co) / 2.0
                        face_center_local = face.calc_center_median()
                        inward_vec_on_face = face_center_local - edge_center_local
                        
                        # 2. The desired outward vector is perpendicular to the edge and lies on the face plane.
                        #    We can get it with a cross product. The direction might be wrong, though.
                        outward_candidate_local = face.normal.cross(edge_dir_local)
                        
                        # 3. Check the direction. If the candidate points inward (dot product > 0), flip it.
                        if inward_vec_on_face.dot(outward_candidate_local) > 0:
                            outward_candidate_local.negate()
                        
                        # This is our guaranteed outward vector, normalized.
                        outward_vec_local = outward_candidate_local.normalized()
                        
                        # --- Use the calculated vectors to define the new quad's transform ---
                        size = (matrix @ edge.verts[0].co - matrix @ edge.verts[1].co).length
                        
                        # Transform key vectors to world space
                        mid_pos_world = matrix @ edge_center_local
                        outward_vec_world = (matrix.to_3x3() @ outward_vec_local).normalized()
                        edge_vec_world = (matrix.to_3x3() @ edge_dir_local).normalized()
                        face_normal_world = (matrix_normal @ face.normal).normalized()
                        
                        # Estimate where the new quad's center should be
                        estimated_center = mid_pos_world + outward_vec_world * (size / 2.0)
                        
                        # The new location is estimated directly, without re-projecting, to ensure it docks perfectly.
                        new_loc = estimated_center

                        # Create an orthonormal rotation matrix for the new quad.
                        # The Z-axis should match the face normal of the blue mesh.
                        # The X-axis should be the outward extrusion direction.
                        x_axis = outward_vec_world
                        z_axis = face_normal_world
                        y_axis = z_axis.cross(x_axis).normalized()
                        # Re-orthogonalize X to ensure a perfect matrix
                        x_axis = y_axis.cross(z_axis).normalized()

                        new_rot = Matrix.Identity(3)
                        new_rot.col[0] = x_axis
                        new_rot.col[1] = y_axis
                        new_rot.col[2] = z_axis
                        
                        # The handle itself should be drawn offset from the surface
                        offset_pos = mid_pos_world + face_normal_world * (offset * 2.0)

                        state._potential_arrow_handles.append({
                            'type': 'reference',
                            'pos': offset_pos,
                            'new_cell_loc': new_loc,
                            'new_cell_rot': new_rot,
                            'new_cell_size': size,
                            'arrow_dir': outward_vec_world,
                            'edge_vec': edge_vec_world, # This is already normalized
                            'edge_length': size,
                        })

                    bm.free()
                finally:
                    if mesh:
                        obj_eval.to_mesh_clear()
    def cancel_preview_cleanup(self, report=False):
        if state._handle_3d is not None:
            state.clear_preview_state()
            if report: self.report({'INFO'}, "Preview cancelled.")
        self.batch_pinned_verts = None
        self.batch_container_meshes = None

classes = (QUICKRETOPO_OT_plane_preview,)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
