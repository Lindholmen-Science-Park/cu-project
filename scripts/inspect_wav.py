import struct
import sys
import uuid

path = sys.argv[1]
with open(path, 'rb') as f:
    h = f.read(4096)

print('first 12:', h[:12])
print('RIFF size:', struct.unpack('<I', h[4:8])[0])

i = 12
while i < len(h) - 8:
    cid = h[i:i+4]
    csize = struct.unpack('<I', h[i+4:i+8])[0]
    print(f'chunk {cid} size={csize} at {i}')
    if cid == b'fmt ':
        fmt = h[i+8:i+8+csize]
        fmt_code = struct.unpack('<H', fmt[0:2])[0]
        ch = struct.unpack('<H', fmt[2:4])[0]
        sr = struct.unpack('<I', fmt[4:8])[0]
        br = struct.unpack('<I', fmt[8:12])[0]
        ba = struct.unpack('<H', fmt[12:14])[0]
        bps = struct.unpack('<H', fmt[14:16])[0]
        print(f'  fmt_code={fmt_code:#x} channels={ch} sampleRate={sr} byteRate={br} blockAlign={ba} bitsPerSample={bps}')
        if fmt_code == 0xFFFE and csize >= 40:
            mask = struct.unpack('<I', fmt[20:24])[0]
            subfmt = fmt[24:40]
            g = uuid.UUID(bytes_le=subfmt)
            print(f'  WAVE_FORMAT_EXTENSIBLE channelMask=0x{mask:X} subFormat={g}')
    if cid == b'data':
        break
    i += 8 + csize + (csize & 1)
