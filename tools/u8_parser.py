"""
Nintendo U8 archive parser and unpacker.
U8 is a common Wii archive format that contains sub-files (BRRES, TPL, etc).

Format reference:
  0x00: u32 magic (0x55AA382D)
  0x04: u32 root_node_offset (typically 0x20)
  0x08: u32 header_size (nodes + strings, NOT total archive size)
  0x0C: u32 data_offset

Node table (12 bytes each):
  0x00: u8  type (0=file, 1=directory)
  0x01: u24 name_offset (relative to string table)
  0x04: u32 data_offset (file: from archive start; dir: parent index)
  0x08: u32 size (file: data size; dir: index of last child + 1)
"""

import struct
from pathlib import Path


MAGIC = 0x55AA382D


def calc_u8_size(data, offset=0):
    """
    Calculate total size of a U8 archive at the given offset.
    Works with both bytes and mmap objects.
    Returns None if the data doesn't look like a valid U8 archive.
    """
    if offset + 0x20 > len(data):
        return None

    magic = struct.unpack_from('>I', data, offset)[0]
    if magic != MAGIC:
        return None

    root_node_off = struct.unpack_from('>I', data, offset + 4)[0]
    header_size = struct.unpack_from('>I', data, offset + 8)[0]
    data_start = struct.unpack_from('>I', data, offset + 0xC)[0]

    # Sanity checks on header values
    if root_node_off < 0x10 or root_node_off > 0x1000:
        return None
    if header_size < 12 or header_size > 2_000_000:
        return None
    if data_start < header_size or data_start > 32_000_000:
        return None

    # Read root node to get total node count
    node_base = offset + root_node_off
    if node_base + 12 > len(data):
        return None

    root_type = data[node_base]
    if root_type != 1:  # Root must be a directory
        return None

    total_nodes = struct.unpack_from('>I', data, node_base + 8)[0]
    if total_nodes < 1 or total_nodes > 10000:
        return None

    # Verify node table fits in data
    node_table_end = node_base + total_nodes * 12
    if node_table_end > len(data):
        return None

    # Find the maximum extent of all file data
    max_end = data_start
    for i in range(1, total_nodes):
        n_off = node_base + i * 12
        n_type = data[n_off]

        if n_type == 0:  # File node
            n_data_off = struct.unpack_from('>I', data, n_off + 4)[0]
            n_size = struct.unpack_from('>I', data, n_off + 8)[0]

            # Sanity: file offset should be >= data_start
            if n_data_off < data_start:
                continue

            file_end = n_data_off + n_size
            if file_end > max_end:
                max_end = file_end

    if max_end < 32 or max_end > 64_000_000:
        return None

    return max_end


def validate_u8(data, offset=0):
    """Quick validation that offset looks like a real U8 archive."""
    if offset + 0x24 > len(data):
        return False

    root_node_off = struct.unpack_from('>I', data, offset + 4)[0]
    if root_node_off < 0x10 or root_node_off > 0x1000:
        return False

    # Check root node is a directory
    node_base = offset + root_node_off
    if node_base + 12 > len(data):
        return False

    root_type = data[node_base]
    if root_type != 1:
        return False

    total_nodes = struct.unpack_from('>I', data, node_base + 8)[0]
    if total_nodes < 1 or total_nodes > 10000:
        return False

    return True


class U8Archive:
    """Parse and extract files from a U8 archive."""

    def __init__(self, data):
        self.data = data
        self.entries = []
        self._parse()

    def _parse(self):
        if len(self.data) < 0x20:
            raise ValueError("Data too small for U8 archive")

        magic = struct.unpack_from('>I', self.data, 0)[0]
        if magic != MAGIC:
            raise ValueError(f"Not a U8 archive (magic: 0x{magic:08X})")

        self.root_node_off = struct.unpack_from('>I', self.data, 4)[0]
        self.header_size = struct.unpack_from('>I', self.data, 8)[0]
        self.data_start = struct.unpack_from('>I', self.data, 0xC)[0]

        # Read root node
        node_base = self.root_node_off
        if node_base + 12 > len(self.data):
            raise ValueError("Root node extends past data")

        root_type = self.data[node_base]
        if root_type != 1:
            raise ValueError("Root node is not a directory")

        self.total_nodes = struct.unpack_from('>I', self.data, node_base + 8)[0]
        if self.total_nodes > 10000:
            raise ValueError(f"Too many nodes: {self.total_nodes}")

        # String table starts after node table
        self.string_table_off = node_base + self.total_nodes * 12

        # Parse all nodes
        dir_stack = [('', self.total_nodes)]  # (path, end_index)

        for i in range(1, self.total_nodes):
            n_off = node_base + i * 12
            if n_off + 12 > len(self.data):
                break

            n_type = self.data[n_off]
            n_name_off = struct.unpack_from('>I', self.data, n_off)[0] & 0x00FFFFFF
            n_data_off = struct.unpack_from('>I', self.data, n_off + 4)[0]
            n_size = struct.unpack_from('>I', self.data, n_off + 8)[0]

            name = self._read_string(self.string_table_off + n_name_off)

            # Pop directories we've passed
            while dir_stack and i >= dir_stack[-1][1]:
                dir_stack.pop()

            current_path = dir_stack[-1][0] if dir_stack else ''

            if n_type == 1:  # Directory
                dir_path = f"{current_path}{name}/"
                dir_stack.append((dir_path, n_size))
                self.entries.append({
                    'type': 'dir',
                    'name': name,
                    'path': dir_path,
                    'index': i,
                })
            else:  # File
                self.entries.append({
                    'type': 'file',
                    'name': name,
                    'path': f"{current_path}{name}",
                    'data_offset': n_data_off,
                    'size': n_size,
                    'index': i,
                })

    def _read_string(self, offset):
        if offset >= len(self.data):
            return ''
        end = self.data.find(b'\x00', offset)
        if end == -1:
            end = min(offset + 256, len(self.data))
        return self.data[offset:end].decode('ascii', errors='replace')

    def list_files(self):
        """Return list of files in the archive."""
        return [e for e in self.entries if e['type'] == 'file']

    def get_file_data(self, entry):
        """Get the raw data for a file entry."""
        if entry['type'] != 'file':
            return None
        start = entry['data_offset']
        end = start + entry['size']
        if end > len(self.data):
            return None
        return self.data[start:end]

    def extract_all(self, output_dir):
        """Extract all files to output_dir. Returns list of extracted file info."""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        extracted = []

        for entry in self.entries:
            if entry['type'] == 'dir':
                (output_dir / entry['path']).mkdir(parents=True, exist_ok=True)
            elif entry['type'] == 'file' and entry['size'] > 0:
                file_data = self.get_file_data(entry)
                if file_data is None:
                    continue

                out_path = output_dir / entry['path']
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_bytes(file_data)

                extracted.append({
                    'name': entry['name'],
                    'path': entry['path'],
                    'size': entry['size'],
                    'full_path': str(out_path),
                })

        return extracted

    def summary(self):
        """Print a summary of archive contents."""
        files = self.list_files()
        dirs = [e for e in self.entries if e['type'] == 'dir']
        total_size = sum(f['size'] for f in files)

        lines = [
            f"U8 Archive: {len(files)} files, {len(dirs)} directories",
            f"Total data: {total_size:,} bytes",
        ]

        for f in files:
            lines.append(f"  {f['path']} ({f['size']:,} bytes)")

        return '\n'.join(lines)
