"""
Convert parsed MDL0 model data to glTF 2.0 format.
Uses pygltflib to create .glb files that Three.js can load.
"""

import struct
import json
import numpy as np
from pathlib import Path

try:
    from pygltflib import GLTF2, Scene, Node, Mesh, Primitive, Buffer, BufferView, Accessor, Material, Asset
    from pygltflib import FLOAT, UNSIGNED_SHORT, ARRAY_BUFFER, ELEMENT_ARRAY_BUFFER, TRIANGLES
    HAS_PYGLTFLIB = True
except ImportError:
    HAS_PYGLTFLIB = False


def mdl0_to_gltf(mdl0_parser, output_path, textures_dir=None):
    """
    Convert a parsed MDL0 model to glTF 2.0 (.glb).

    Args:
        mdl0_parser: Parsed MDL0Parser instance
        output_path: Output .glb file path
        textures_dir: Optional directory containing PNG textures
    """
    if not HAS_PYGLTFLIB:
        return _mdl0_to_gltf_manual(mdl0_parser, output_path, textures_dir)

    gltf = GLTF2()
    gltf.asset = Asset(version="2.0", generator="slowski2-extractor")
    gltf.scene = 0
    gltf.scenes = [Scene(nodes=[0])]

    # Binary data buffer
    bin_data = bytearray()

    # Root node
    root_node = Node(name=mdl0_parser.name or "model")
    mesh_primitives = []

    # Process each vertex group into mesh primitives
    for vg in mdl0_parser.vertices:
        positions = vg['positions']
        if len(positions) == 0:
            continue

        attributes = {}

        # Position accessor
        pos_data = positions.astype(np.float32).tobytes()
        pos_view_offset = len(bin_data)
        bin_data.extend(pos_data)

        pos_min = positions.min(axis=0).tolist()
        pos_max = positions.max(axis=0).tolist()

        buf_view_idx = len(gltf.bufferViews)
        gltf.bufferViews.append(BufferView(
            buffer=0,
            byteOffset=pos_view_offset,
            byteLength=len(pos_data),
            target=ARRAY_BUFFER,
        ))

        acc_idx = len(gltf.accessors)
        gltf.accessors.append(Accessor(
            bufferView=buf_view_idx,
            byteOffset=0,
            componentType=FLOAT,
            count=len(positions),
            type="VEC3",
            max=pos_max,
            min=pos_min,
        ))
        attributes["POSITION"] = acc_idx

        # Generate triangle indices (simple fan/strip for now)
        num_verts = len(positions)
        if num_verts >= 3:
            indices = []
            for i in range(1, num_verts - 1):
                indices.extend([0, i, i + 1])
            indices = np.array(indices, dtype=np.uint16)

            idx_data = indices.tobytes()
            idx_view_offset = len(bin_data)
            bin_data.extend(idx_data)
            # Pad to 4 byte boundary
            while len(bin_data) % 4 != 0:
                bin_data.append(0)

            idx_view_idx = len(gltf.bufferViews)
            gltf.bufferViews.append(BufferView(
                buffer=0,
                byteOffset=idx_view_offset,
                byteLength=len(idx_data),
                target=ELEMENT_ARRAY_BUFFER,
            ))

            idx_acc_idx = len(gltf.accessors)
            gltf.accessors.append(Accessor(
                bufferView=idx_view_idx,
                byteOffset=0,
                componentType=UNSIGNED_SHORT,
                count=len(indices),
                type="SCALAR",
                max=[int(indices.max())],
                min=[int(indices.min())],
            ))

            mesh_primitives.append(Primitive(
                attributes=attributes,
                indices=idx_acc_idx,
                mode=TRIANGLES,
            ))
        else:
            mesh_primitives.append(Primitive(
                attributes=attributes,
                mode=TRIANGLES,
            ))

    if mesh_primitives:
        root_node.mesh = 0
        gltf.meshes = [Mesh(
            name=mdl0_parser.name or "mesh",
            primitives=mesh_primitives,
        )]

    gltf.nodes = [root_node]

    # Add buffer
    gltf.buffers = [Buffer(byteLength=len(bin_data))]

    # Save as GLB
    gltf.set_binary_blob(bytes(bin_data))
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    gltf.save(str(output_path))
    return True


def _mdl0_to_gltf_manual(mdl0_parser, output_path, textures_dir=None):
    """
    Fallback: manually construct a minimal glTF JSON + binary without pygltflib.
    """
    bin_data = bytearray()
    accessors = []
    buffer_views = []
    meshes = []
    primitives = []

    for vg in mdl0_parser.vertices:
        positions = vg['positions']
        if len(positions) == 0:
            continue

        # Position data
        pos_data = positions.astype(np.float32).tobytes()
        pos_offset = len(bin_data)
        bin_data.extend(pos_data)

        pos_min = positions.min(axis=0).tolist()
        pos_max = positions.max(axis=0).tolist()

        bv_idx = len(buffer_views)
        buffer_views.append({
            "buffer": 0,
            "byteOffset": pos_offset,
            "byteLength": len(pos_data),
            "target": 34962,  # ARRAY_BUFFER
        })

        acc_idx = len(accessors)
        accessors.append({
            "bufferView": bv_idx,
            "byteOffset": 0,
            "componentType": 5126,  # FLOAT
            "count": len(positions),
            "type": "VEC3",
            "max": pos_max,
            "min": pos_min,
        })

        # Indices
        num_verts = len(positions)
        if num_verts >= 3:
            indices = []
            for i in range(1, num_verts - 1):
                indices.extend([0, i, i + 1])
            idx_array = np.array(indices, dtype=np.uint16)
            idx_data = idx_array.tobytes()
            idx_offset = len(bin_data)
            bin_data.extend(idx_data)
            while len(bin_data) % 4 != 0:
                bin_data.append(0)

            idx_bv = len(buffer_views)
            buffer_views.append({
                "buffer": 0,
                "byteOffset": idx_offset,
                "byteLength": len(idx_data),
                "target": 34963,  # ELEMENT_ARRAY_BUFFER
            })

            idx_acc = len(accessors)
            accessors.append({
                "bufferView": idx_bv,
                "byteOffset": 0,
                "componentType": 5123,  # UNSIGNED_SHORT
                "count": len(idx_array),
                "type": "SCALAR",
                "max": [int(idx_array.max())],
                "min": [int(idx_array.min())],
            })

            primitives.append({
                "attributes": {"POSITION": acc_idx},
                "indices": idx_acc,
                "mode": 4,  # TRIANGLES
            })

    if not primitives:
        return False

    gltf_json = {
        "asset": {"version": "2.0", "generator": "slowski2-extractor"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"name": mdl0_parser.name or "model", "mesh": 0}],
        "meshes": [{"name": mdl0_parser.name or "mesh", "primitives": primitives}],
        "accessors": accessors,
        "bufferViews": buffer_views,
        "buffers": [{"byteLength": len(bin_data)}],
    }

    # Write GLB
    json_str = json.dumps(gltf_json, separators=(',', ':')).encode('utf-8')
    # Pad JSON to 4-byte boundary
    while len(json_str) % 4 != 0:
        json_str += b' '

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'wb') as f:
        # GLB header
        total_size = 12 + 8 + len(json_str) + 8 + len(bin_data)
        f.write(struct.pack('<I', 0x46546C67))  # magic "glTF"
        f.write(struct.pack('<I', 2))  # version
        f.write(struct.pack('<I', total_size))  # total length

        # JSON chunk
        f.write(struct.pack('<I', len(json_str)))  # chunk length
        f.write(struct.pack('<I', 0x4E4F534A))  # type "JSON"
        f.write(json_str)

        # Binary chunk
        f.write(struct.pack('<I', len(bin_data)))  # chunk length
        f.write(struct.pack('<I', 0x004E4942))  # type "BIN\0"
        f.write(bin_data)

    return True
