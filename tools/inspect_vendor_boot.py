import struct
import gzip
import io

def lz4_decompress_block(src):
    out = bytearray()
    pos = 0
    n = len(src)
    while pos < n:
        token = src[pos]
        pos += 1
        lit_len = token >> 4
        if lit_len == 15:
            while pos < n:
                b = src[pos]
                pos += 1
                lit_len += b
                if b != 255:
                    break
        out.extend(src[pos:pos+lit_len])
        pos += lit_len
        if pos >= n:
            break
        offset = src[pos] | (src[pos+1] << 8)
        pos += 2
        match_len = (token & 0x0F) + 4
        if match_len == 19:
            while pos < n:
                b = src[pos]
                pos += 1
                match_len += b
                if b != 255:
                    break
        start = len(out) - offset
        for i in range(match_len):
            out.append(out[start + i])
    return bytes(out)

def decompress_ramdisk(buf):
    if buf[:2] == b"\x1f\x8b":
        return "gzip", gzip.decompress(buf)
    elif buf[:4] == b"\x02\x21\x4c\x18":
        pos = 4
        out = bytearray()
        while pos + 4 <= len(buf):
            bsize = struct.unpack("<I", buf[pos:pos+4])[0]
            pos += 4
            if bsize == 0 or bsize == 0x184c2102 or pos + bsize > len(buf):
                if bsize == 0x184c2102:
                    continue
                break
            out.extend(lz4_decompress_block(buf[pos:pos+bsize]))
            pos += bsize
        return "lz4_legacy", bytes(out)
    elif buf[:6] == b"070701":
        return "raw_cpio", buf
    else:
        return f"unknown({buf[:8].hex()})", b""

def parse_cpio(data):
    pos = 0
    entries = []
    while pos + 110 <= len(data):
        if data[pos:pos+6] != b"070701":
            break
        namesize = int(data[pos+94:pos+102], 16)
        filesize = int(data[pos+54:pos+62], 16)
        mode = int(data[pos+14:pos+22], 16)
        name_start = pos + 110
        name = data[name_start:name_start+namesize-1].decode("utf-8", errors="replace")
        pos = name_start + namesize
        if pos % 4 != 0:
            pos += 4 - (pos % 4)
        content = data[pos:pos+filesize]
        entries.append((name, filesize, mode, content))
        pos += filesize
        if pos % 4 != 0:
            pos += 4 - (pos % 4)
        if name == "TRAILER!!!":
            break
    return entries, pos

def inspect_vb(path, label):
    print(f"=== {label}: {path} ===")
    with open(path, "rb") as f:
        data = f.read()
    magic = data[:8]
    version, page_size, kernel_addr, ramdisk_addr, vramdisk_size = struct.unpack("<5I", data[8:28])
    cmdline = data[28:28+2048].split(b"\x00")[0].decode()
    tags_addr = struct.unpack("<I", data[2076:2080])[0]
    name = data[2080:2096].split(b"\x00")[0].decode()
    header_size, dtb_size, dtb_addr = struct.unpack("<IIQ", data[2096:2112])
    print(f"magic={magic} v={version} page={page_size} vramdisk_size={vramdisk_size} dtb_size={dtb_size} hdr_size={header_size} dtb_addr=0x{dtb_addr:x}")
    print(f"cmdline={cmdline}")
    def align(x, p):
        return ((x + p - 1) // p) * p
    if version >= 4:
        vramdisk_table_size, vramdisk_table_entry_num, vramdisk_table_entry_size, bootconfig_size = struct.unpack("<4I", data[2112:2128])
        print(f"v4 table: size={vramdisk_table_size} num={vramdisk_table_entry_num} entry_size={vramdisk_table_entry_size} bootconfig_size={bootconfig_size}")
        o = align(header_size, page_size)
        r_off = o
        o += align(vramdisk_size, page_size)
        dtb_off = o
        o += align(dtb_size, page_size)
        table_off = o
        bc_off = table_off + align(vramdisk_table_size, page_size)
        print(f"bootconfig={data[bc_off:bc_off+bootconfig_size]!r}")
        for i in range(vramdisk_table_entry_num):
            e_off = table_off + i * vramdisk_table_entry_size
            r_size, r_offset, r_type = struct.unpack("<3I", data[e_off:e_off+12])
            r_name = data[e_off+12:e_off+44].split(b"\x00")[0].decode("utf-8", errors="replace")
            sub = data[r_off+r_offset:r_off+r_offset+r_size]
            kind, raw = decompress_ramdisk(sub)
            print(f"  Ramdisk[{i}]: size={r_size} offset={r_offset} type={r_type} name='{r_name}' kind={kind} decomp={len(raw)}")
            if raw:
                entries, _ = parse_cpio(raw)
                print(f"    entries={len(entries)}")
                for ename, esize, emode, econtent in entries[:40]:
                    print(f"      {ename} ({esize} B)")
    else:
        r_off = align(header_size, page_size)
        sub = data[r_off:r_off+vramdisk_size]
        kind, raw = decompress_ramdisk(sub)
        print(f"v3 ramdisk @ 0x{r_off:x} kind={kind} decomp={len(raw)}")
        if raw:
            off = 0
            idx = 0
            while off < len(raw):
                if raw[off:off+6] == b"070701":
                    entries, consumed = parse_cpio(raw[off:])
                    print(f"  CPIO archive #{idx} at offset {off}: {len(entries)} entries (consumed {consumed} bytes)")
                    for ename, esize, emode, econtent in entries:
                        if not ename.startswith("lib/modules/") or ename.endswith((".load", ".dep", ".alias", ".softdep")):
                            print(f"    {ename} ({esize} B)")
                    mod_count = sum(1 for e in entries if e[0].startswith("lib/modules/"))
                    print(f"    [Total lib/modules/* entries: {mod_count}]")
                    off += consumed
                    while off < len(raw) and raw[off] == 0:
                        off += 1
                    idx += 1
                else:
                    # check if multiple compressed archives concatenated inside v3 ramdisk!
                    break

if __name__ == "__main__":
    inspect_vb(r"C:\Users\İ_CEYLAN\.gemini\antigravity\scratch\x6710_twrp_fix\stock_241029\vendor_boot.img", "STOCK_241029")
    inspect_vb(r"D:\x6710twrp.ben yaptım.img", "USER_TWRP")

