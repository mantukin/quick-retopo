# Global state for the preview operator
_handle_3d = None
_should_stop = False
_needs_update = False
_grid_cells = {}
_vertex_remap = {}
_vertex_overrides = {}  # Stores { (ix, iy): Vector(pos) } for manually moved vertices
_pinned_vertices = {}   # Stores { (ix, iy): Vector(pos) } for pinned vertices
_potential_arrow_handles = []
_center_handles = []  # Represents the center of a grid cell
_vertex_handles = [] # Stores { 'pos': Vector, 'coord': (ix, iy) }
_potential_connection_handles = []
_hovered_arrow_data = None
_hovered_center_data = None  # Data for the hovered cell center
_hovered_vertex_data = None # Data for the hovered vertex
_hovered_connection_data = None
_reference_mode_active = False
def clear_preview_state():
    """Clears all data related to the interactive preview and removes draw handlers."""
    global _handle_3d, _should_stop, _needs_update, _grid_cells, _vertex_remap, _vertex_overrides, _pinned_vertices
    global _potential_arrow_handles, _center_handles, _vertex_handles, _potential_connection_handles
    global _hovered_arrow_data, _hovered_center_data, _hovered_vertex_data, _hovered_connection_data
    global _reference_mode_active
    
    if _handle_3d is not None:
        import bpy
        try:
            bpy.types.SpaceView3D.draw_handler_remove(_handle_3d, 'WINDOW')
        except ValueError:
            # Handle may have already been removed by other means
            pass
    
    _handle_3d = None
    _should_stop = False
    _needs_update = False
    _grid_cells.clear()
    _vertex_remap.clear()
    _vertex_overrides.clear()
    _pinned_vertices.clear()
    _potential_arrow_handles.clear()
    _center_handles.clear()
    _vertex_handles.clear()
    _potential_connection_handles.clear()
    _hovered_arrow_data = None
    _hovered_center_data = None
    _hovered_vertex_data = None
    _hovered_connection_data = None
    _reference_mode_active = False
