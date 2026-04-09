"""
BRSTM audio extractor.
Decodes ADPCM audio from BRSTM files and saves as WAV.
Reference: https://wiibrew.org/wiki/BRSTM_file
"""

import struct
import wave
import numpy as np
from pathlib import Path


class BRSTMParser:
    def __init__(self, data):
        self.data = data
        self.sample_rate = 0
        self.num_channels = 0
        self.total_samples = 0
        self.loop_start = 0
        self.loop_end = 0
        self.loops = False
        self.codec = 0
        self._parse()

    def _parse(self):
        if len(self.data) < 0x40:
            return

        magic = self.data[0:4]
        if magic != b'RSTM':
            raise ValueError("Not a BRSTM file")

        bom = struct.unpack_from('>H', self.data, 4)[0]
        self.big_endian = bom == 0xFEFF
        e = '>' if self.big_endian else '<'
        self.endian = e

        self.version = struct.unpack_from(f'{e}H', self.data, 6)[0]
        self.file_size = struct.unpack_from(f'{e}I', self.data, 8)[0]
        self.header_size = struct.unpack_from(f'{e}H', self.data, 12)[0]
        self.section_count = struct.unpack_from(f'{e}H', self.data, 14)[0]

        # Section offsets (HEAD, ADPC, DATA)
        self.head_offset = struct.unpack_from(f'{e}I', self.data, 16)[0]
        self.head_size = struct.unpack_from(f'{e}I', self.data, 20)[0]
        self.adpc_offset = struct.unpack_from(f'{e}I', self.data, 24)[0]
        self.adpc_size = struct.unpack_from(f'{e}I', self.data, 28)[0]
        self.data_offset = struct.unpack_from(f'{e}I', self.data, 32)[0]
        self.data_size = struct.unpack_from(f'{e}I', self.data, 36)[0]

        self._parse_head()

    def _parse_head(self):
        """Parse HEAD section to get audio parameters."""
        e = self.endian
        off = self.head_offset

        if off + 8 > len(self.data):
            return

        head_magic = self.data[off:off + 4]
        if head_magic != b'HEAD':
            return

        # HEAD chunk 1 reference at off+8
        ref1_type = struct.unpack_from(f'{e}I', self.data, off + 8)[0]
        ref1_off = struct.unpack_from(f'{e}I', self.data, off + 12)[0]

        chunk1_off = off + 8 + ref1_off
        if chunk1_off + 0x30 > len(self.data):
            return

        self.codec = self.data[chunk1_off]
        self.loops = self.data[chunk1_off + 1] != 0
        self.num_channels = self.data[chunk1_off + 2]
        self.sample_rate = struct.unpack_from(f'{e}H', self.data, chunk1_off + 4)[0]
        self.loop_start = struct.unpack_from(f'{e}I', self.data, chunk1_off + 8)[0]
        self.total_samples = struct.unpack_from(f'{e}I', self.data, chunk1_off + 12)[0]

        self.adpcm_data_offset = struct.unpack_from(f'{e}I', self.data, chunk1_off + 16)[0]
        self.total_blocks = struct.unpack_from(f'{e}I', self.data, chunk1_off + 20)[0]
        self.block_size = struct.unpack_from(f'{e}I', self.data, chunk1_off + 24)[0]
        self.samples_per_block = struct.unpack_from(f'{e}I', self.data, chunk1_off + 28)[0]
        self.last_block_size = struct.unpack_from(f'{e}I', self.data, chunk1_off + 32)[0]
        self.last_block_samples = struct.unpack_from(f'{e}I', self.data, chunk1_off + 36)[0]
        self.last_block_padded = struct.unpack_from(f'{e}I', self.data, chunk1_off + 40)[0]

        # Parse ADPCM coefficients from HEAD chunk 3
        self.coefficients = []
        ref3_off = struct.unpack_from(f'{e}I', self.data, off + 20)[0]
        if ref3_off:
            chunk3_off = off + 8 + ref3_off
            for ch in range(self.num_channels):
                ch_ref_off = chunk3_off + 8 * ch
                if ch_ref_off + 8 > len(self.data):
                    break
                ch_type = struct.unpack_from(f'{e}I', self.data, ch_ref_off)[0]
                ch_off = struct.unpack_from(f'{e}I', self.data, ch_ref_off + 4)[0]
                abs_off = chunk3_off + ch_off

                if abs_off + 32 > len(self.data):
                    self.coefficients.append([0] * 16)
                    continue

                coefs = []
                for i in range(16):
                    coefs.append(struct.unpack_from(f'{e}h', self.data, abs_off + i * 2)[0])
                self.coefficients.append(coefs)

    def decode_adpcm(self):
        """Decode ADPCM audio data to PCM16 samples."""
        if self.codec != 2:  # Only ADPCM supported
            print(f"    Unsupported codec: {self.codec}")
            return None

        if self.num_channels == 0 or self.total_samples == 0:
            return None

        e = self.endian
        pcm_data = np.zeros((self.num_channels, self.total_samples), dtype=np.int16)

        data_start = self.data_offset + 0x20  # Skip DATA header

        for ch in range(self.num_channels):
            if ch >= len(self.coefficients):
                break

            coefs = self.coefficients[ch]
            yn1 = 0  # History sample n-1
            yn2 = 0  # History sample n-2
            sample_idx = 0

            for block in range(self.total_blocks):
                if block == self.total_blocks - 1:
                    block_size = self.last_block_size
                    num_samples = self.last_block_samples
                else:
                    block_size = self.block_size
                    num_samples = self.samples_per_block

                # Calculate block offset (interleaved per channel)
                if self.num_channels > 1:
                    if block == self.total_blocks - 1:
                        ch_block_off = data_start + block * self.block_size * self.num_channels + ch * self.last_block_padded
                    else:
                        ch_block_off = data_start + block * self.block_size * self.num_channels + ch * self.block_size
                else:
                    ch_block_off = data_start + block * self.block_size

                if ch_block_off >= len(self.data):
                    break

                # First byte: predictor/scale
                ps = self.data[ch_block_off]
                predictor = (ps >> 4) & 0x07
                scale = 1 << (ps & 0x0F)

                coef1 = coefs[predictor * 2] if predictor * 2 < len(coefs) else 0
                coef2 = coefs[predictor * 2 + 1] if predictor * 2 + 1 < len(coefs) else 0

                byte_offset = ch_block_off + 1
                for s in range(num_samples):
                    if sample_idx >= self.total_samples:
                        break

                    byte_idx = byte_offset + s // 2
                    if byte_idx >= len(self.data):
                        break

                    if s % 2 == 0:
                        nibble = (self.data[byte_idx] >> 4) & 0x0F
                    else:
                        nibble = self.data[byte_idx] & 0x0F

                    # Sign extend nibble
                    if nibble >= 8:
                        nibble -= 16

                    # Decode sample
                    sample = (scale * nibble + coef1 * yn1 + coef2 * yn2 + 1024) >> 11
                    sample = max(-32768, min(32767, sample))

                    pcm_data[ch, sample_idx] = sample
                    yn2 = yn1
                    yn1 = sample
                    sample_idx += 1

        return pcm_data

    def save_wav(self, output_path):
        """Decode and save as WAV file."""
        pcm_data = self.decode_adpcm()
        if pcm_data is None:
            return False

        output_path = Path(output_path)

        # Interleave channels
        if self.num_channels > 1:
            interleaved = np.zeros(self.total_samples * self.num_channels, dtype=np.int16)
            for ch in range(self.num_channels):
                interleaved[ch::self.num_channels] = pcm_data[ch]
        else:
            interleaved = pcm_data[0]

        with wave.open(str(output_path), 'wb') as wf:
            wf.setnchannels(self.num_channels)
            wf.setsampwidth(2)  # 16-bit
            wf.setframerate(self.sample_rate)
            wf.writeframes(interleaved.tobytes())

        return True

    def get_summary(self):
        return {
            'codec': 'ADPCM' if self.codec == 2 else f'Unknown({self.codec})',
            'sample_rate': self.sample_rate,
            'channels': self.num_channels,
            'total_samples': self.total_samples,
            'duration_seconds': self.total_samples / self.sample_rate if self.sample_rate > 0 else 0,
            'loops': self.loops,
        }
