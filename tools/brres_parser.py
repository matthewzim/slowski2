"""
BRRES (Binary Revolution RESource) container parser.
Parses .brres files to extract sub-files: MDL0, TEX0, CHR0, SRT0, etc.
Reference: https://wiki.tockdom.com/wiki/BRRES_(File_Format)
"""

import struct
from pathlib import Path

from texture_decoder import decode_texture, FORMAT_NAMES


# BRRES sub-file magic bytes
SUB_FILE_TYPES = {
    b'MDL0': 'model',
    b'TEX0': 'texture',
    b'SRT0': 'tex_anim',
    b'CHR0': 'bone_anim',
    b'PAT0': 'pattern_anim',
    b'CLR0': 'color_anim',
    b'SHP0': 'shape_anim',
    b'SCN0': 'scene',
    b'VIS0': 'visibility_anim',
}


class BRRESParser:
    def __init__(self, data):
        self.data = data
        self.sub_files = []
        self._parse()

    def _parse(self):
        """Parse the BRRES header and root section."""
        if len(self.data) < 16:
            return

        magic = self.data[0:4]
        if magic != b'bres':
            raise ValueError(f"Not a BRRES file (magic: {magic})")

        bom = struct.unpack_from('>H', self.data, 4)[0]
        self.big_endian = bom == 0xFEFF
        self.endian = '>' if self.big_endian else '<'

        self.version = struct.unpack_from(f'{self.endian}H', self.data, 6)[0]
        self.file_size = struct.unpack_from(f'{self.endian}I', self.data, 8)[0]
        self.root_offset = struct.unpack_from(f'{self.endian}H', self.data, 12)[0]
        self.section_count = struct.unpack_from(f'{self.endian}H', self.data, 14)[0]

        # Sanity checks to avoid OOM on corrupt/false-positive data
        if self.file_size > len(self.data) + 16:
            raise ValueError(f"BRRES claimed size {self.file_size} exceeds data length {len(self.data)}")
        if self.section_count > 100:
            raise ValueError(f"BRRES section count {self.section_count} is unreasonable")

        # Parse root section
        self._parse_root()

    def _parse_root(self):
        """Parse the root section index group."""
        offset = self.root_offset
        if offset + 8 > len(self.data):
            return

        root_magic = self.data[offset:offset + 4]
        root_size = struct.unpack_from(f'{self.endian}I', self.data, offset + 4)[0]

        # Parse root index group at offset + 8
        self._parse_index_group(offset + 8, is_root=True)

    def _parse_index_group(self, offset, is_root=False, depth=0):
        """Parse a BRRES index group (tree structure)."""
        if depth > 4:
            return  # Prevent infinite recursion on corrupt data
        if offset + 8 > len(self.data):
            return

        group_size = struct.unpack_from(f'{self.endian}I', self.data, offset)[0]
        entry_count = struct.unpack_from(f'{self.endian}I', self.data, offset + 4)[0]
        if entry_count > 1000:
            return  # Sanity cap - real BRRES files have < 100 entries

        # Each entry is 16 bytes: id(2), unk(2), left(2), right(2), name_offset(4), data_offset(4)
        entry_offset = offset + 8
        # Skip the root entry (first one)
        entry_offset += 16

        for i in range(entry_count):
            if entry_offset + 16 > len(self.data):
                break

            _id = struct.unpack_from(f'{self.endian}H', self.data, entry_offset)[0]
            _unk = struct.unpack_from(f'{self.endian}H', self.data, entry_offset + 2)[0]
            _left = struct.unpack_from(f'{self.endian}H', self.data, entry_offset + 4)[0]
            _right = struct.unpack_from(f'{self.endian}H', self.data, entry_offset + 6)[0]
            name_off = struct.unpack_from(f'{self.endian}I', self.data, entry_offset + 8)[0]
            data_off = struct.unpack_from(f'{self.endian}I', self.data, entry_offset + 12)[0]

            # Name is relative to the index group
            name = self._read_string(offset + name_off)

            if is_root:
                # Root entries point to sub-index-groups
                abs_data_off = offset + data_off
                self._parse_index_group(abs_data_off, depth=depth + 1)
            else:
                # Sub entries point to actual sub-files
                abs_data_off = offset + data_off
                if abs_data_off < len(self.data):
                    sub_magic = self.data[abs_data_off:abs_data_off + 4]
                    sub_type = SUB_FILE_TYPES.get(sub_magic, 'unknown')

                    # Try to read sub-file size
                    sub_size = None
                    if abs_data_off + 8 <= len(self.data):
                        sub_size = struct.unpack_from(f'{self.endian}I', self.data, abs_data_off + 4)[0]

                    self.sub_files.append({
                        'name': name,
                        'type': sub_type,
                        'magic': sub_magic.decode('ascii', errors='replace'),
                        'offset': abs_data_off,
                        'size': sub_size,
                    })

            entry_offset += 16

    def _read_string(self, offset):
        """Read a null-terminated string."""
        if offset >= len(self.data):
            return ''
        end = self.data.find(b'\x00', offset)
        if end == -1:
            end = min(offset + 256, len(self.data))
        return self.data[offset:end].decode('ascii', errors='replace')

    def extract_sub_files(self, output_dir):
        """Extract all sub-files to disk."""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        extracted = []

        for sf in self.sub_files:
            if sf['size'] and sf['offset'] + sf['size'] <= len(self.data):
                data = self.data[sf['offset']:sf['offset'] + sf['size']]
                ext = f".{sf['magic'].lower().strip()}"
                filename = f"{sf['name']}{ext}"
                out_path = output_dir / filename
                with open(out_path, 'wb') as f:
                    f.write(data)
                extracted.append({**sf, 'filename': filename})

        return extracted


class TEX0Parser:
    """Parse TEX0 texture sub-files from BRRES."""

    def __init__(self, data, endian='>'):
        self.data = data
        self.endian = endian
        self.textures = []
        self._parse()

    def _parse(self):
        if len(self.data) < 0x40:
            return

        magic = self.data[0:4]
        if magic != b'TEX0':
            return

        size = struct.unpack_from(f'{self.endian}I', self.data, 4)[0]
        version = struct.unpack_from(f'{self.endian}I', self.data, 8)[0]

        # Section 0 offset (image data)
        if version == 3:
            header_size = 0x40
        else:
            header_size = 0x30

        if header_size > len(self.data):
            return

        # TEX0 v3 header fields at 0x18+
        if version == 3 and len(self.data) >= 0x40:
            width = struct.unpack_from(f'{self.endian}H', self.data, 0x1C)[0]
            height = struct.unpack_from(f'{self.endian}H', self.data, 0x1E)[0]
            fmt = struct.unpack_from(f'{self.endian}I', self.data, 0x20)[0]
            mipmap_count = struct.unpack_from(f'{self.endian}I', self.data, 0x24)[0]
        elif len(self.data) >= 0x30:
            width = struct.unpack_from(f'{self.endian}H', self.data, 0x10)[0]
            height = struct.unpack_from(f'{self.endian}H', self.data, 0x12)[0]
            fmt = struct.unpack_from(f'{self.endian}I', self.data, 0x14)[0]
            mipmap_count = struct.unpack_from(f'{self.endian}I', self.data, 0x18)[0]
        else:
            return

        # Image data starts after header
        img_data = self.data[header_size:]

        self.textures.append({
            'width': width,
            'height': height,
            'format': fmt,
            'format_name': FORMAT_NAMES.get(fmt, f'unknown({fmt})'),
            'mipmap_count': mipmap_count,
            'data': img_data,
        })

    def decode_textures(self):
        """Decode all textures to RGBA numpy arrays."""
        decoded = []
        for tex in self.textures:
            try:
                pixels = decode_texture(tex['data'], tex['width'], tex['height'], tex['format'])
                decoded.append({
                    'width': tex['width'],
                    'height': tex['height'],
                    'format_name': tex['format_name'],
                    'pixels': pixels,
                })
            except Exception as e:
                print(f"    Warning: Failed to decode texture ({tex['format_name']}): {e}")
        return decoded
