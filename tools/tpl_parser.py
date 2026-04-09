"""
TPL (Texture Palette Library) parser for Wii/GameCube.
Reference: https://wiki.tockdom.com/wiki/TPL_(File_Format)
"""

import struct
from texture_decoder import decode_texture, FORMAT_NAMES


class TPLParser:
    def __init__(self, data):
        self.data = data
        self.images = []
        self._parse()

    def _parse(self):
        if len(self.data) < 12:
            return

        # TPL header
        magic = struct.unpack_from('>I', self.data, 0)[0]
        if magic != 0x0020AF30:
            raise ValueError(f"Not a TPL file (magic: 0x{magic:08X})")

        image_count = struct.unpack_from('>I', self.data, 4)[0]
        image_table_offset = struct.unpack_from('>I', self.data, 8)[0]

        # Sanity check
        if image_count > 1000:
            return

        for i in range(image_count):
            entry_off = image_table_offset + i * 8
            if entry_off + 8 > len(self.data):
                break

            image_header_off = struct.unpack_from('>I', self.data, entry_off)[0]
            palette_header_off = struct.unpack_from('>I', self.data, entry_off + 4)[0]

            if image_header_off == 0 or image_header_off + 0x24 > len(self.data):
                continue

            # Image header
            height = struct.unpack_from('>H', self.data, image_header_off)[0]
            width = struct.unpack_from('>H', self.data, image_header_off + 2)[0]
            fmt = struct.unpack_from('>I', self.data, image_header_off + 4)[0]
            data_offset = struct.unpack_from('>I', self.data, image_header_off + 8)[0]

            # Validate dimensions
            if width == 0 or height == 0 or width > 4096 or height > 4096:
                continue

            # Parse palette if present
            palette = None
            if palette_header_off != 0 and palette_header_off + 12 <= len(self.data):
                pal_count = struct.unpack_from('>H', self.data, palette_header_off)[0]
                pal_unpacked = struct.unpack_from('>B', self.data, palette_header_off + 2)[0]
                pal_fmt = struct.unpack_from('>I', self.data, palette_header_off + 4)[0]
                pal_data_off = struct.unpack_from('>I', self.data, palette_header_off + 8)[0]

                if pal_data_off > 0 and pal_count > 0:
                    palette = self._decode_palette(pal_data_off, pal_count, pal_fmt)

            self.images.append({
                'index': i,
                'width': width,
                'height': height,
                'format': fmt,
                'format_name': FORMAT_NAMES.get(fmt, f'unknown({fmt})'),
                'data_offset': data_offset,
                'palette': palette,
            })

    def _decode_palette(self, offset, count, fmt):
        """Decode a color palette."""
        from texture_decoder import decode_rgb565_pixel, decode_rgb5a3_pixel

        palette = []
        for i in range(count):
            pos = offset + i * 2
            if pos + 2 > len(self.data):
                break
            val = struct.unpack_from('>H', self.data, pos)[0]

            if fmt == 0:  # IA8
                intensity = val & 0xFF
                alpha = (val >> 8) & 0xFF
                palette.append((intensity, intensity, intensity, alpha))
            elif fmt == 1:  # RGB565
                palette.append(decode_rgb565_pixel(val))
            elif fmt == 2:  # RGB5A3
                palette.append(decode_rgb5a3_pixel(val))
            else:
                palette.append((128, 128, 128, 255))

        return palette

    def decode_images(self):
        """Decode all images to RGBA numpy arrays."""
        decoded = []
        for img in self.images:
            try:
                data = self.data[img['data_offset']:]
                pixels = decode_texture(
                    data, img['width'], img['height'],
                    img['format'], img.get('palette')
                )
                decoded.append({
                    'index': img['index'],
                    'width': img['width'],
                    'height': img['height'],
                    'format_name': img['format_name'],
                    'pixels': pixels,
                })
            except Exception as e:
                print(f"    Warning: Failed to decode TPL image {img['index']}: {e}")
        return decoded
