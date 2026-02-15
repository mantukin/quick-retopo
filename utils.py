import bpy
import bmesh
import math
from collections import deque
from mathutils import Vector, Matrix
from mathutils.kdtree import KDTree
from gpu_extras.batch import batch_for_shader
from bpy_extras import view3d_utils

from . import state
def quickretopo_poll(cls, context):
    """Common poll function for operators that work in Object Mode on a mesh."""
    if context.mode != 'OBJECT':
        cls.poll_message_set("Operator requires Object Mode.")
        return False

    obj = context.view_layer.objects.active

    if obj is None:
        cls.poll_message_set("Please select a high-poly object.")
        return False

    if obj.type != 'MESH':
        cls.poll_message_set("The selected object must be a MESH.")
        return False

    if obj.name.startswith("Retopo_Plane"):
        cls.poll_message_set("Select the high-poly mesh, not the retopology plane.")
        return False

    return True
def get_mouse_location_on_surface(context, mouse_pos):
    """
    Projects the mouse cursor onto the active object's surface.
    Returns (success, location, normal)
    """
    target_object = context.view_layer.objects.active
    if not target_object or target_object.type != 'MESH':
        return False, None, None

    region = context.region
    rv3d = context.space_data.region_3d

    view_vector = view3d_utils.region_2d_to_vector_3d(region, rv3d, mouse_pos)
    ray_origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, mouse_pos)
    
    depsgraph = context.evaluated_depsgraph_get()
    target_eval = target_object.evaluated_get(depsgraph)

    matrix_inv = target_eval.matrix_world.inverted()
    ray_origin_local = matrix_inv @ ray_origin
    ray_direction_local = (matrix_inv.to_3x3() @ view_vector).normalized()

    success, location_local, normal_local, _ = target_eval.ray_cast(ray_origin_local, ray_direction_local)

    if success:
        location_world = target_eval.matrix_world @ location_local
        inv_trans_matrix = target_eval.matrix_world.inverted_safe().transposed()
        normal_world = (inv_trans_matrix.to_3x3() @ normal_local).normalized()
        return True, location_world, normal_world
    else:
        return False, None, None
def get_surface_transform_at_point(context, point_world, parent_rot_matrix, preserve_axis_of_parent='Y'):
    """
    Calculates location and rotation for a plane on the active object's surface
    at a given world-space point, guided by the parent's orientation.
    The `preserve_axis_of_parent` argument ('X' or 'Y') determines which axis of the
    parent_rot_matrix should be maintained as closely as possible.
    Returns: (location, rotation_matrix, success)
    """
    target_object = context.view_layer.objects.active
    if not target_object or target_object.type != 'MESH':
        return point_world, Matrix.Identity(3), False

    depsgraph = context.evaluated_depsgraph_get()
    target_eval = target_object.evaluated_get(depsgraph)

    try:
        point_local = target_eval.matrix_world.inverted() @ point_world
    except ValueError: # Matrix is not invertible
        return point_world, Matrix.Identity(3), False

    success, location_local, normal_local, _ = target_eval.closest_point_on_mesh(point_local)

    if not success:
        return point_world, Matrix.Identity(3), False

    location_world = target_eval.matrix_world @ location_local
    inv_trans_matrix = target_eval.matrix_world.inverted_safe().transposed()
    normal_world = (inv_trans_matrix.to_3x3() @ normal_local).normalized()

    z_axis = normal_world
    x_axis, y_axis = Vector(), Vector()

    if preserve_axis_of_parent == 'X':
        # --- Try to preserve X axis of parent ---
        ref_x = parent_rot_matrix.col[0]
        x_axis_proj = (ref_x - ref_x.dot(z_axis) * z_axis)
        
        if x_axis_proj.length > 0.01:
            x_axis = x_axis_proj.normalized()
            y_axis = z_axis.cross(x_axis).normalized()
        else: # Fallback: try to use parent's Y axis to define new Y
            ref_y = parent_rot_matrix.col[1]
            y_axis_proj = (ref_y - ref_y.dot(z_axis) * z_axis)
            if y_axis_proj.length > 0.01:
                y_axis = y_axis_proj.normalized()
                x_axis = y_axis.cross(z_axis).normalized()
            else: # Ultimate fallback
                world_up = Vector((0.0, 0.0, 1.0))
                if abs(z_axis.dot(world_up)) > 0.999: world_up = Vector((0.0, 1.0, 0.0))
                y_axis = (world_up - world_up.dot(z_axis) * z_axis).normalized()
                x_axis = y_axis.cross(z_axis).normalized()
    else: # Default behavior: preserve 'Y'
        # --- Try to preserve Y axis of parent ---
        ref_y = parent_rot_matrix.col[1]
        y_axis_proj = (ref_y - ref_y.dot(z_axis) * z_axis)

        if y_axis_proj.length > 0.01:
            y_axis = y_axis_proj.normalized()
            x_axis = y_axis.cross(z_axis).normalized()
        else: # Fallback: try to use parent's X axis to define new X
            ref_x = parent_rot_matrix.col[0]
            x_axis_proj = (ref_x - ref_x.dot(z_axis) * z_axis)
            
            if x_axis_proj.length > 0.01:
                x_axis = x_axis_proj.normalized()
                y_axis = z_axis.cross(x_axis).normalized()
            else: # Ultimate fallback
                world_up = Vector((0.0, 0.0, 1.0))
                if abs(z_axis.dot(world_up)) > 0.999: world_up = Vector((0.0, 1.0, 0.0))
                y_axis = (world_up - world_up.dot(z_axis) * z_axis).normalized()
                x_axis = y_axis.cross(z_axis).normalized()

    rot_matrix = Matrix.Identity(3)
    rot_matrix.col[0] = x_axis
    rot_matrix.col[1] = y_axis
    rot_matrix.col[2] = z_axis
    
    return location_world, rot_matrix, True
def get_strip_quad_transform(context, point_world, guide_direction, parent_rot):
    """
    Calculates location and rotation for a quad in the initial strip,
    aligned to a guide direction.
    """
    target_object = context.view_layer.objects.active
    if not target_object or target_object.type != 'MESH': return point_world, Matrix.Identity(3), False
    depsgraph = context.evaluated_depsgraph_get()
    target_eval = target_object.evaluated_get(depsgraph)
    try: point_local = target_eval.matrix_world.inverted() @ point_world
    except ValueError: return point_world, Matrix.Identity(3), False
    success, location_local, normal_local, _ = target_eval.closest_point_on_mesh(point_local)
    if not success: return point_world, Matrix.Identity(3), False
    location_world = target_eval.matrix_world @ location_local
    inv_trans_matrix = target_eval.matrix_world.inverted_safe().transposed()
    normal_world = (inv_trans_matrix.to_3x3() @ normal_local).normalized()

    z_axis = normal_world
    x_axis_proj = (guide_direction - guide_direction.dot(z_axis) * z_axis)
    
    if x_axis_proj.length > 0.01:
        x_axis = x_axis_proj.normalized()
    elif parent_rot:
        ref_x = parent_rot.col[0]
        x_axis_proj_2 = (ref_x - ref_x.dot(z_axis) * z_axis)
        if x_axis_proj_2.length > 0.01:
            x_axis = x_axis_proj_2.normalized()
        else:
            ref_y = parent_rot.col[1]
            y_axis_proj = (ref_y - ref_y.dot(z_axis) * z_axis).normalized()
            x_axis = y_axis_proj.cross(z_axis).normalized()
    else:
        world_up = Vector((0.0, 0.0, 1.0))
        if abs(z_axis.dot(world_up)) > 0.999: world_up = Vector((0.0, 1.0, 0.0))
        y_axis = (world_up - world_up.dot(z_axis) * z_axis).normalized()
        x_axis = y_axis.cross(z_axis).normalized()

    y_axis = z_axis.cross(x_axis).normalized()
    rot_matrix = Matrix.Identity(3)
    rot_matrix.col[0] = x_axis
    rot_matrix.col[1] = y_axis
    rot_matrix.col[2] = z_axis
    return location_world, rot_matrix, True
def calculate_final_verts(grid_cells, global_size, vertex_remap={}, vertex_overrides={}, pinned_vertices={}):
    """Calculates the averaged vertex positions for the grid, respecting per-cell size, merging, position overrides, and pinned vertices."""
    if not grid_cells:
        return {}
    
    def resolve(v_coord):
        # Follow the chain of remappings to find the final target vertex.
        while v_coord in vertex_remap:
            v_coord = vertex_remap[v_coord]
        return v_coord

    vertex_positions = {}
    for (ix, iy), transform in grid_cells.items():
        loc, rot = transform['loc'], transform['rot']
        
        cell_size = transform.get('size')
        if cell_size:
            s_x = cell_size.x / 2.0
            s_y = cell_size.y / 2.0
        else:
            # Fallback for older data format or initial strip
            size_mult = transform.get('size_mult', 1.0)
            s = (global_size * size_mult) / 2.0
            s_x = s
            s_y = s
        
        corners_offsets = {
            (ix, iy): Vector((-s_x, -s_y, 0)), (ix + 1, iy): Vector((s_x, -s_y, 0)),
            (ix + 1, iy + 1): Vector((s_x, s_y, 0)), (ix, iy + 1): Vector((-s_x, s_y, 0)),
        }
        for v_coord, offset in corners_offsets.items():
            resolved_v = resolve(v_coord)
            if resolved_v not in vertex_positions: vertex_positions[resolved_v] = []
            vertex_positions[resolved_v].append(loc + rot @ offset)

    final_verts = {v_coord: sum(pos_list, Vector()) / len(pos_list) for v_coord, pos_list in vertex_positions.items()}
    
    # Apply overrides after averaging. An override for a vertex coordinate applies to its resolved target.
    # Keep track of which vertices were moved by an override.
    overridden_resolved_verts = set()
    for v_coord, pos in vertex_overrides.items():
        resolved_v = resolve(v_coord)
        if resolved_v in final_verts:
            final_verts[resolved_v] = pos
            overridden_resolved_verts.add(resolved_v)
    
    # Apply pinned vertices last, but only if they weren't just moved by the user via an override.
    for v_coord, pos in pinned_vertices.items():
        # The key (v_coord) in pinned_vertices is already the resolved coordinate.
        # A manual override takes precedence over a pin.
        if v_coord in final_verts and v_coord not in overridden_resolved_verts:
            final_verts[v_coord] = pos
            
    return final_verts
