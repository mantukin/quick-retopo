bl_info = {
    "name": "Quick Retopo",
    "author": "mantukin (IPD Workshop)",
    "version": (1, 0, 0),
    "blender": (3, 3, 0),
    "location": "View3D > Sidebar > Retopo Tab",
    "description": "An interactive tool for quick, quad-based retopology by drawing and extending a grid on a high-poly surface.",
    "warning": "",
    "doc_url": "https://github.com/mantukin/quick-retopo",
    "category": "Mesh",
}

import bpy

# Reload logic for development
if "bpy" in locals():
    import importlib
    from . import state, utils, properties, ui, operators
    from .operators import op_preview, op_grid_ops, op_create_mesh, op_edit_mode, op_container
    
    importlib.reload(state)
    importlib.reload(utils)
    importlib.reload(properties)
    importlib.reload(op_preview)
    importlib.reload(op_grid_ops)
    importlib.reload(op_create_mesh)
    importlib.reload(op_edit_mode)
    importlib.reload(op_container)
    importlib.reload(operators)
    importlib.reload(ui)

from . import state
from . import properties
from . import ui
from . import operators

def register():
    """Registers the addon modules."""
    properties.register()
    operators.register()
    ui.register()

def unregister():
    """Unregisters the addon modules."""
    # Ensure preview is stopped on unregister to remove draw handlers etc.
    if state._handle_3d:
        state.clear_preview_state()
        
    ui.unregister()
    operators.unregister()
    properties.unregister()

if __name__ == "__main__":
    register()
