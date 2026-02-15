import bpy

class QUICKRETOPO_PG_retopo_container_item(bpy.types.PropertyGroup):
    """An item in the retopo container list."""
    obj: bpy.props.PointerProperty(
        name="Object",
        type=bpy.types.Object,
        description="A finalized retopo mesh to be used as a reference for highlighting",
        poll=lambda self, obj: obj.type == 'MESH'
    )
def register():
    """Registers the addon's scene properties."""
    bpy.utils.register_class(QUICKRETOPO_PG_retopo_container_item)
    
    bpy.types.Scene.retopo_plane_size = bpy.props.FloatProperty(
        name="Size",
        description="Size of the retopology plane segments",
        default=0.5,
        min=0.01,
        soft_max=10.0,
        step=1,
        precision=2,
        unit='LENGTH'
    )
    
    bpy.types.Scene.retopo_align_distance = bpy.props.FloatProperty(
        name="Align Distance",
        description="Maximum distance to search for a target vertex to snap to",
        default=0.5,
        min=0.001,
        soft_max=10.0,
        step=1,
        precision=3,
        unit='LENGTH'
    )
    
    bpy.types.Scene.retopo_arrow_radius = bpy.props.FloatProperty(
        name="Hover Radius",
        description="Hover radius in pixels to show interactive handles (add/delete)",
        default=35.0,
        min=5.0,
        max=100.0,
        step=1,
        precision=0,
        subtype='PIXEL'
    )
    bpy.types.Scene.retopo_arrow_click_radius = bpy.props.FloatProperty(
        name="Click Radius",
        description="Click activation radius in pixels for interactive handles (add/delete)",
        default=15.0,
        min=2.0,
        max=50.0,
        precision=0,
        subtype='PIXEL'
    )
    bpy.types.Scene.retopo_draw_offset = bpy.props.FloatProperty(
        name="Draw Offset",
        description="Offset for drawing UI elements above the surface to prevent Z-fighting",
        default=0.005,
        min=0.0,
        soft_max=0.1,
        step=1,
        precision=4,
        unit='LENGTH'
    )

    bpy.types.Scene.retopo_resize_ratio = bpy.props.FloatProperty(
        name="Resize Ratio",
        description="Ratio for resizing segments with Shift+Mouse Wheel",
        default=1.1,
        min=1.01,
        soft_max=2.0,
        step=10,
        precision=2,
    )
    
    bpy.types.Scene.retopo_x_ray_mode = bpy.props.BoolProperty(
        name="X-Ray Mode",
        description="Draw the grid through the reference model",
        default=True
    )
    bpy.types.Scene.retopo_prevent_click_through = bpy.props.BoolProperty(
        name="Prevent Click-Through",
        description="Prevents interaction with grid elements that are occluded by the reference model",
        default=True
    )
    
    # Post-creation options
    bpy.types.Scene.retopo_add_modifiers = bpy.props.BoolProperty(
        name="Add Modifiers",
        description="Automatically add and configure Subdivision Surface and Shrinkwrap modifiers to the final mesh",
        default=False
    )
    
    bpy.types.Scene.retopo_enable_snapping = bpy.props.BoolProperty(
        name="Enable Snapping",
        description="Automatically enable face snapping after creating the mesh",
        default=False
    )
    
    # New property for edit mode action
    bpy.types.Scene.retopo_edit_mode = bpy.props.EnumProperty(
        name="Mode",
        description="Determines the action of the final operator button",
        items=[
            ('CREATE', "Create Mesh", "Create a new mesh object from the grid"),
            ('SELECT', "Select Polygons", "Select polygons on the reference mesh under the grid")
        ],
        default='CREATE'
    )
    
    # New properties for the container
    bpy.types.Scene.retopo_container_items = bpy.props.CollectionProperty(
        type=QUICKRETOPO_PG_retopo_container_item
    )
    bpy.types.Scene.retopo_container_active_index = bpy.props.IntProperty()
def unregister():
    """Unregisters the addon's scene properties."""
    try:
        del bpy.types.Scene.retopo_plane_size
        del bpy.types.Scene.retopo_align_distance
        del bpy.types.Scene.retopo_arrow_radius
        del bpy.types.Scene.retopo_arrow_click_radius
        del bpy.types.Scene.retopo_draw_offset
        del bpy.types.Scene.retopo_resize_ratio
        
        del bpy.types.Scene.retopo_x_ray_mode
        del bpy.types.Scene.retopo_prevent_click_through
        
        del bpy.types.Scene.retopo_add_modifiers
        del bpy.types.Scene.retopo_enable_snapping
        
        del bpy.types.Scene.retopo_edit_mode
        
        # Unregister container properties
        del bpy.types.Scene.retopo_container_items
        del bpy.types.Scene.retopo_container_active_index
    except AttributeError:
        # Properties might not be registered if there was an error
        pass
        
    bpy.utils.unregister_class(QUICKRETOPO_PG_retopo_container_item)
