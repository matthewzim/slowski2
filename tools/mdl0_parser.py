"""
MDL0 (Wii 3D Model) parser.
Extracts vertex positions, normals, UVs, bones, and materials from MDL0 sub-files.
Reference: https://wiki.tockdom.com/wiki/MDL0_(File_Format)
"""

import struct
import numpy as np


class MDL0Parser:
    def __init__(self, data, endian='>'):
        self.data = data
        self.endian = endian
        self.bones = []
        self.vertices = []
        self.normals = []
        self.uvs = []
        self.colors = []
        self.materials = []
        self.polygons = []
        self.name = ''
        self._parse()

    def _parse(self):
        if len(self.data) < 16:
            return

        magic = self.data[0:4]
        if magic != b'MDL0':
            raise ValueError(f"Not a MDL0 file (magic: {magic})")

        e = self.endian
        self.size = struct.unpack_from(f'{e}I', self.data, 4)[0]
        self.version = struct.unpack_from(f'{e}I', self.data, 8)[0]
        self.brres_offset = struct.unpack_from(f'{e}i', self.data, 12)[0]

        # Section offsets depend on version
        # Common: offsets to section index groups
        self._parse_header()
        self._parse_sections()

    def _parse_header(self):
        """Parse MDL0 header to get section group offsets."""
        e = self.endian
        # v11 has 14 section groups, v9 has 11, v8 has fewer
        # The offsets start at byte 16

        if self.version >= 11:
            num_sections = 14
        elif self.version >= 9:
            num_sections = 11
        else:
            num_sections = 8

        self.section_offsets = []
        for i in range(num_sections):
            off_pos = 16 + i * 4
            if off_pos + 4 > len(self.data):
                self.section_offsets.append(0)
                continue
            off = struct.unpack_from(f'{e}i', self.data, off_pos)[0]
            self.section_offsets.append(off)

        # After section offsets: name offset, header size, etc.
        header_end = 16 + num_sections * 4
        if header_end + 16 <= len(self.data):
            name_off = struct.unpack_from(f'{e}I', self.data, header_end + 4)[0]
            if name_off > 0:
                self.name = self._read_string(name_off)

    def _parse_sections(self):
        """Parse each section index group."""
        # Section mapping (v11):
        # 0: DrawOpa/DrawXlu  1: Bones  2: Vertices  3: Normals
        # 4: Colors  5: UVs  6: FurVectors  7: FurLayers
        # 8: Materials  9: Shaders  10: Polygons/Objects  11: Texture Links
        section_handlers = {
            1: self._parse_bone_group,
            2: self._parse_vertex_group,
            3: self._parse_normal_group,
            4: self._parse_color_group,
            5: self._parse_uv_group,
            8: self._parse_material_group,
            10: self._parse_polygon_group,
        }

        for idx, handler in section_handlers.items():
            if idx < len(self.section_offsets) and self.section_offsets[idx] != 0:
                try:
                    handler(self.section_offsets[idx])
                except Exception as e:
                    print(f"    Warning: Failed to parse section {idx}: {e}")

    def _parse_index_group(self, offset):
        """Parse an MDL0 index group, return list of (name, data_offset) pairs."""
        e = self.endian
        if offset + 8 > len(self.data):
            return []

        group_size = struct.unpack_from(f'{e}I', self.data, offset)[0]
        entry_count = struct.unpack_from(f'{e}I', self.data, offset + 4)[0]

        entries = []
        entry_off = offset + 8 + 16  # Skip header entry

        for i in range(entry_count):
            if entry_off + 16 > len(self.data):
                break
            name_off = struct.unpack_from(f'{e}I', self.data, entry_off + 8)[0]
            data_off = struct.unpack_from(f'{e}I', self.data, entry_off + 12)[0]

            name = self._read_string(offset + name_off)
            abs_off = offset + data_off

            entries.append((name, abs_off))
            entry_off += 16

        return entries

    def _parse_bone_group(self, offset):
        """Parse bone section."""
        e = self.endian
        for name, data_off in self._parse_index_group(offset):
            if data_off + 0x88 > len(self.data):
                continue
            bone = {'name': name}

            # Bone header
            bone['header_size'] = struct.unpack_from(f'{e}I', self.data, data_off)[0]
            bone['bone_index'] = struct.unpack_from(f'{e}I', self.data, data_off + 8)[0]
            bone['node_id'] = struct.unpack_from(f'{e}I', self.data, data_off + 12)[0]

            # Transform: scale(3), rotation(3), translation(3)
            transform_off = data_off + 0x28
            if transform_off + 36 <= len(self.data):
                bone['scale'] = struct.unpack_from(f'{e}3f', self.data, transform_off)
                bone['rotation'] = struct.unpack_from(f'{e}3f', self.data, transform_off + 12)
                bone['translation'] = struct.unpack_from(f'{e}3f', self.data, transform_off + 24)

            self.bones.append(bone)

    def _parse_vertex_group(self, offset):
        """Parse vertex position data."""
        e = self.endian
        for name, data_off in self._parse_index_group(offset):
            if data_off + 0x40 > len(self.data):
                continue

            vg = {'name': name}
            vg['entry_count'] = struct.unpack_from(f'{e}H', self.data, data_off + 0x10)[0]
            vg['component_count'] = self.data[data_off + 0x13] if data_off + 0x14 <= len(self.data) else 3
            vg['format'] = self.data[data_off + 0x14] if data_off + 0x15 <= len(self.data) else 0
            vg['divisor'] = self.data[data_off + 0x15] if data_off + 0x16 <= len(self.data) else 0

            # Data offset within the vertex group
            data_start = data_off + 0x40
            num_components = 3 if vg['component_count'] >= 1 else 2

            positions = []
            divisor = 2 ** vg['divisor'] if vg['divisor'] > 0 else 1.0
            pos = data_start

            for i in range(vg['entry_count']):
                if vg['format'] == 0:  # uint8
                    if pos + num_components > len(self.data):
                        break
                    vals = struct.unpack_from(f'{e}{num_components}B', self.data, pos)
                    pos += num_components
                elif vg['format'] == 1:  # int8
                    if pos + num_components > len(self.data):
                        break
                    vals = struct.unpack_from(f'{e}{num_components}b', self.data, pos)
                    pos += num_components
                elif vg['format'] == 2:  # uint16
                    if pos + num_components * 2 > len(self.data):
                        break
                    vals = struct.unpack_from(f'{e}{num_components}H', self.data, pos)
                    pos += num_components * 2
                elif vg['format'] == 3:  # int16
                    if pos + num_components * 2 > len(self.data):
                        break
                    vals = struct.unpack_from(f'{e}{num_components}h', self.data, pos)
                    pos += num_components * 2
                elif vg['format'] == 4:  # float32
                    if pos + num_components * 4 > len(self.data):
                        break
                    vals = struct.unpack_from(f'{e}{num_components}f', self.data, pos)
                    pos += num_components * 4
                else:
                    break

                scaled = [v / divisor for v in vals]
                if num_components == 2:
                    scaled.append(0.0)
                positions.append(scaled)

            vg['positions'] = np.array(positions, dtype=np.float32) if positions else np.zeros((0, 3), dtype=np.float32)
            self.vertices.append(vg)

    def _parse_normal_group(self, offset):
        """Parse normal vector data."""
        e = self.endian
        for name, data_off in self._parse_index_group(offset):
            if data_off + 0x20 > len(self.data):
                continue

            ng = {'name': name}
            ng['entry_count'] = struct.unpack_from(f'{e}H', self.data, data_off + 0x10)[0]
            ng['format'] = self.data[data_off + 0x14] if data_off + 0x15 <= len(self.data) else 4
            ng['divisor'] = self.data[data_off + 0x15] if data_off + 0x16 <= len(self.data) else 0

            data_start = data_off + 0x20
            normals_list = []
            divisor = 2 ** ng['divisor'] if ng['divisor'] > 0 else 1.0
            pos = data_start

            for i in range(ng['entry_count']):
                if ng['format'] == 4:  # float32
                    if pos + 12 > len(self.data):
                        break
                    vals = struct.unpack_from(f'{e}3f', self.data, pos)
                    pos += 12
                elif ng['format'] == 3:  # int16
                    if pos + 6 > len(self.data):
                        break
                    vals = struct.unpack_from(f'{e}3h', self.data, pos)
                    pos += 6
                else:
                    break
                normals_list.append([v / divisor for v in vals])

            ng['normals'] = np.array(normals_list, dtype=np.float32) if normals_list else np.zeros((0, 3), dtype=np.float32)
            self.normals.append(ng)

    def _parse_color_group(self, offset):
        """Parse vertex color data."""
        e = self.endian
        for name, data_off in self._parse_index_group(offset):
            cg = {'name': name}
            # Simplified - just record metadata
            self.colors.append(cg)

    def _parse_uv_group(self, offset):
        """Parse UV texture coordinate data."""
        e = self.endian
        for name, data_off in self._parse_index_group(offset):
            if data_off + 0x20 > len(self.data):
                continue

            ug = {'name': name}
            ug['entry_count'] = struct.unpack_from(f'{e}H', self.data, data_off + 0x10)[0]
            ug['component_count'] = self.data[data_off + 0x13] if data_off + 0x14 <= len(self.data) else 1
            ug['format'] = self.data[data_off + 0x14] if data_off + 0x15 <= len(self.data) else 4
            ug['divisor'] = self.data[data_off + 0x15] if data_off + 0x16 <= len(self.data) else 0

            data_start = data_off + 0x20
            uvs_list = []
            divisor = 2 ** ug['divisor'] if ug['divisor'] > 0 else 1.0
            num_components = 2
            pos = data_start

            for i in range(ug['entry_count']):
                if ug['format'] == 4:  # float32
                    if pos + 8 > len(self.data):
                        break
                    vals = struct.unpack_from(f'{e}2f', self.data, pos)
                    pos += 8
                elif ug['format'] == 3:  # int16
                    if pos + 4 > len(self.data):
                        break
                    vals = struct.unpack_from(f'{e}2h', self.data, pos)
                    pos += 4
                else:
                    break
                uvs_list.append([v / divisor for v in vals])

            ug['uvs'] = np.array(uvs_list, dtype=np.float32) if uvs_list else np.zeros((0, 2), dtype=np.float32)
            self.uvs.append(ug)

    def _parse_material_group(self, offset):
        """Parse material definitions."""
        e = self.endian
        for name, data_off in self._parse_index_group(offset):
            mat = {'name': name, 'offset': data_off}
            self.materials.append(mat)

    def _parse_polygon_group(self, offset):
        """Parse polygon/object definitions."""
        e = self.endian
        for name, data_off in self._parse_index_group(offset):
            poly = {'name': name, 'offset': data_off}
            self.polygons.append(poly)

    def _read_string(self, offset):
        if offset >= len(self.data):
            return ''
        end = self.data.find(b'\x00', offset)
        if end == -1:
            end = min(offset + 256, len(self.data))
        return self.data[offset:end].decode('ascii', errors='replace')

    def get_summary(self):
        return {
            'name': self.name,
            'version': self.version,
            'bones': len(self.bones),
            'vertex_groups': len(self.vertices),
            'normal_groups': len(self.normals),
            'uv_groups': len(self.uvs),
            'materials': len(self.materials),
            'polygons': len(self.polygons),
            'total_vertices': sum(vg['positions'].shape[0] for vg in self.vertices),
        }
