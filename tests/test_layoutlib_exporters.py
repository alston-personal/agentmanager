from capabilities.layoutlib import spatial_ir_to_mesh_objects, spatial_ir_to_obj


def sample_ir():
    return {
        "units": "m",
        "walls": [
            {
                "id": "wall-1",
                "start": {"x": 0, "y": 0},
                "end": {"x": 4, "y": 0},
                "height": 2.7,
                "thickness": 0.12,
                "source": "manual",
            }
        ],
    }


def test_wall_becomes_exporter_neutral_box_mesh():
    objects = spatial_ir_to_mesh_objects(sample_ir())
    assert len(objects) == 1
    wall = objects[0]
    assert wall.name == "wall-1"
    assert len(wall.vertices) == 8
    assert len(wall.faces) == 6
    assert wall.metadata["kind"] == "wall"


def test_obj_export_is_derived_from_spatial_ir():
    text = spatial_ir_to_obj(sample_ir())
    assert "# Generated from LayoutLib Spatial IR" in text
    assert "o wall-1" in text
    assert text.count("\nv ") == 8
    assert text.count("\nf ") == 6
