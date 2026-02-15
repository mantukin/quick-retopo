from . import op_preview
from . import op_grid_ops
from . import op_create_mesh
from . import op_edit_mode
from . import op_container

# Expose classes for easier access from other modules
from .op_preview import QUICKRETOPO_OT_plane_preview
from .op_grid_ops import (
    QUICKRETOPO_OT_align_grid,
    QUICKRETOPO_OT_align_and_pin_grid,
    QUICKRETOPO_OT_straighten_grid,
    QUICKRETOPO_OT_strong_straighten_grid,
    QUICKRETOPO_OT_pin_all_grid_verts
)
from .op_create_mesh import QUICKRETOPO_OT_create_mesh
from .op_edit_mode import QUICKRETOPO_OT_snap_verts_to_surface
from .op_container import (
    QUICKRETOPO_OT_container_add,
    QUICKRETOPO_OT_container_remove,
    QUICKRETOPO_OT_stitch_meshes
)

_modules = (
    op_preview,
    op_grid_ops,
    op_create_mesh,
    op_edit_mode,
    op_container,
)
def register():
    for mod in _modules:
        mod.register()

def unregister():
    for mod in reversed(_modules):
        mod.unregister()
