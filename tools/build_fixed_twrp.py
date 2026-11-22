import os
import sys
import struct
import pickle
import hashlib
import subprocess

BASE_DIR = r"C:\Users\İ_CEYLAN\.gemini\antigravity\scratch\x6710_twrp_fix"
sys.path.insert(0, BASE_DIR)
from inspect_vendor_boot import lz4_decompress_block, parse_cpio, decompress_ramdisk

def decomp_erofs_blk(blk):
    nz = len(blk) - len(blk.lstrip(b"\x00"))
    return lz4_decompress_block(blk[nz:])

def extract_erofs_file(blocks, blks, exp=None):
    out = bytearray()
    for b in blks:
        blk = blocks[b]
        try:
            out.extend(decomp_erofs_blk(blk))
        except Exception:
            out.extend(blk)
    if exp is not None:
        return bytes(out[:exp])
    if out[:4] == b"\x7fELF" and out[4] == 2:
        e_shoff = struct.unpack("<Q", out[40:48])[0]
        e_shentsize, e_shnum = struct.unpack("<2H", out[58:62])
        return bytes(out[:e_shoff + e_shnum * e_shentsize])
    return bytes(out)

def build_cpio(entries):
    out = bytearray()
    ino = 300000
    for name, size, mode, content in entries:
        if name == "TRAILER!!!":
            continue
        size = len(content)
        name_bytes = name.encode("utf-8") + b"\x00"
        namesize = len(name_bytes)
        nlink = 2 if (mode & 0o170000) == 0o040000 else 1
        hdr = (
            f"070701"
            f"{ino:08X}"
            f"{mode:08X}"
            f"{0:08X}"
            f"{0:08X}"
            f"{nlink:08X}"
            f"{0:08X}"
            f"{size:08X}"
            f"{0:08X}"
            f"{0:08X}"
            f"{0:08X}"
            f"{0:08X}"
            f"{namesize:08X}"
            f"{0:08X}"
        ).encode("ascii")
        ino += 1
        out.extend(hdr)
        out.extend(name_bytes)
        if len(out) % 4 != 0:
            out.extend(b"\x00" * (4 - (len(out) % 4)))
        out.extend(content)
        if len(out) % 4 != 0:
            out.extend(b"\x00" * (4 - (len(out) % 4)))
    # Add TRAILER!!!
    t_name = b"TRAILER!!!\x00"
    t_hdr = (
        f"070701"
        f"{0:08X}{0:08X}{0:08X}{0:08X}{1:08X}{0:08X}"
        f"{0:08X}{0:08X}{0:08X}{0:08X}{0:08X}"
        f"{len(t_name):08X}{0:08X}"
    ).encode("ascii")
    out.extend(t_hdr)
    out.extend(t_name)
    if len(out) % 4 != 0:
        out.extend(b"\x00" * (4 - (len(out) % 4)))
    # Pad to 512-byte boundary as mkbootfs does
    if len(out) % 512 != 0:
        out.extend(b"\x00" * (512 - (len(out) % 512)))
    return bytes(out)

def main():
    print("1. Loading cached stock.cpio, twrp.cpio, and super_blocks.pkl...")
    with open(os.path.join(BASE_DIR, "stock.cpio"), "rb") as f:
        s_entries, _ = parse_cpio(f.read())
    with open(os.path.join(BASE_DIR, "twrp.cpio"), "rb") as f:
        t_entries, _ = parse_cpio(f.read())
    with open(os.path.join(BASE_DIR, "super_blocks.pkl"), "rb") as f:
        sb = pickle.load(f)

    blocks = sb["blocks"]
    with open(os.path.join(BASE_DIR, "stock_241029", "installed-files-vendor.txt")) as f:
        ven_sizes = {l.split()[1]: int(l.split()[0]) for l in f if len(l.split()) == 2}

    stock_map = {n: (s, m, c) for n, s, m, c in s_entries if n != "TRAILER!!!"}
    twrp_map = {}
    for n, s, m, c in t_entries:
        if n == "TRAILER!!!":
            continue
        twrp_map[n] = (s, m, c)

    # 2. Fix #1 & #2: Replace all first_stage_ramdisk/* and lib/modules/* with 100% original STOCK_241029 entries
    # (including STOCK_241029's exact lib/modules/modules.load.recovery, modules.load, modules.dep, modules.alias, modules.softdep, and all 220 .ko modules)
    print("2. Restoring 100% stock 241029 first_stage_ramdisk/* and lib/modules/* (including stock modules.load.recovery)...")
    for k in list(twrp_map.keys()):
        if k == "first_stage_ramdisk" or k.startswith("first_stage_ramdisk/") or k.startswith("lib/modules/"):
            del twrp_map[k]

    for n, s, m, c in s_entries:
        if n == "first_stage_ramdisk" or n.startswith("first_stage_ramdisk/") or n.startswith("lib/modules/"):
            twrp_map[n] = (s, m, c)

    # 3. Fix #3: Add all missing DT_NEEDED shared libraries and binaries extracted from stock 241029 super.img
    print("3. Adding missing Keymaster 4.1, Gatekeeper 1.0, and Trustonic TEE libraries from stock super.img...")
    add_vendor_files = [
        ("/vendor/lib64/android.hardware.gatekeeper@1.0.so", 0o100644),
        ("/vendor/lib64/android.hardware.keymaster@3.0.so", 0o100644),
        ("/vendor/lib64/android.hardware.keymaster@4.0.so", 0o100644),
        ("/vendor/lib64/android.hardware.keymaster@4.1.so", 0o100644),
        ("/vendor/lib64/libcppbor_external.so", 0o100644),
        ("/vendor/lib64/libcppcose_rkp.so", 0o100644),
        ("/vendor/lib64/libsoft_attestation_cert.so", 0o100644),
        ("/vendor/lib64/libkeymaster4.so", 0o100644),
        ("/vendor/lib64/libkeymaster41.so", 0o100644),
        ("/vendor/lib64/libkmsetkey.so", 0o100644),
        ("/vendor/lib64/vendor.mediatek.hardware.keymaster_attestation@1.0.so", 0o100644),
        ("/vendor/lib64/vendor.mediatek.hardware.keymaster_attestation@1.1.so", 0o100644),
        ("/vendor/lib64/hw/vendor.mediatek.hardware.keymaster_attestation@1.1-impl.so", 0o100644),
        ("/vendor/bin/hw/vendor.mediatek.hardware.keymaster_attestation@1.1-service", 0o100755),
        ("/vendor/bin/kmsetkey_ca.trustonic", 0o100755),
        ("/vendor/app/mcRegistry/98fb95bcb4bf42d26473eae48690d7ea.tabin", 0o100644),
    ]
    for vpath, mode in add_vendor_files:
        data = extract_erofs_file(blocks, sb["ven_files"][vpath], ven_sizes.get(vpath))
        rel = vpath.lstrip("/")
        twrp_map[rel] = (len(data), mode, data)

    # Extract libgatekeeper.so from system_a and remove unused keystore_cli_v2 test binary
    gk_data = extract_erofs_file(blocks, sb["sys_files"]["//system/lib64/libgatekeeper.so"])
    twrp_map["system/lib64/libgatekeeper.so"] = (len(gk_data), 0o100644, gk_data)
    twrp_map["vendor/lib64/libgatekeeper.so"] = (len(gk_data), 0o100644, gk_data)
    if "system/bin/keystore_cli_v2" in twrp_map:
        del twrp_map["system/bin/keystore_cli_v2"]

    # Also add system/lib64/libtranlog.so from stock.cpio
    if "system/lib64/libtranlog.so" in stock_map:
        s, m, c = stock_map["system/lib64/libtranlog.so"]
        twrp_map["system/lib64/libtranlog.so"] = (s, m, c)
        twrp_map["vendor/lib64/libtranlog.so"] = (s, m, c)

    # Mirror ALL top-level vendor/lib64/*.so libraries into system/lib64/*.so so linker64 finds them regardless of namespace
    for k in list(twrp_map.keys()):
        if k.startswith("vendor/lib64/") and k.endswith(".so") and "/" not in k[len("vendor/lib64/"):]:
            srel = "system/lib64/" + k[len("vendor/lib64/"):]
            twrp_map[srel] = twrp_map[k]

    # Fix system/etc/ld.config.txt and system/etc/init/hw/init.rc LD_LIBRARY_PATH
    ld_cfg = """dir.recovery = /system/bin
dir.vendor = /vendor/bin

[recovery]
namespace.default.isolated = false
namespace.default.search.paths = /system/${LIB}:/vendor/${LIB}:/vendor/${LIB}/hw:/system/${LIB}/hw
namespace.default.asan.search.paths = /data/asan/system/${LIB}:/system/${LIB}:/vendor/${LIB}:/vendor/${LIB}/hw:/system/${LIB}/hw

[vendor]
namespace.default.isolated = false
namespace.default.search.paths = /vendor/${LIB}:/system/${LIB}:/vendor/${LIB}/hw:/system/${LIB}/hw
namespace.default.asan.search.paths = /vendor/${LIB}:/system/${LIB}:/vendor/${LIB}/hw:/system/${LIB}/hw
"""
    ld_cfg_bytes = ld_cfg.encode("utf-8")
    twrp_map["system/etc/ld.config.txt"] = (len(ld_cfg_bytes), 0o100644, ld_cfg_bytes)

    hw_init_rc = twrp_map["system/etc/init/hw/init.rc"][2].decode("utf-8")
    hw_init_rc = hw_init_rc.replace(
        "export LD_LIBRARY_PATH /system/lib64:/vendor/lib64/hw",
        "export LD_LIBRARY_PATH /system/lib64:/vendor/lib64:/vendor/lib64/hw:/system/lib64/hw"
    )
    hw_init_rc_bytes = hw_init_rc.encode("utf-8")
    twrp_map["system/etc/init/hw/init.rc"] = (len(hw_init_rc_bytes), 0o100644, hw_init_rc_bytes)

    # 4. Fix #4: Fix system/etc/recovery.fstab to enable FBEv2 + inlinecrypt + keydirectory=/metadata/vold/metadata_encryption
    print("4. Fixing system/etc/recovery.fstab with FBEv2 inlinecrypt + metadata_encryption flags...")
    rec_fstab = twrp_map["system/etc/recovery.fstab"][2].decode("utf-8")
    old_data_line = "/dev/block/by-name/userdata     /data           f2fs    noatime,nosuid,nodev,discard,noflush_merge,fsync_mode=nobarrier,reserve_root=134217,resgid=1065     wait,check,formattable,quota,latemount,resize,reservedsize=128m,checkpoint=fs"
    new_data_line = "/dev/block/by-name/userdata     /data           f2fs    noatime,nosuid,nodev,discard,noflush_merge,fsync_mode=nobarrier,reserve_root=134217,resgid=1065,inlinecrypt     wait,check,formattable,quota,latemount,resize,reservedsize=128m,checkpoint=fs,fileencryption=aes-256-xts:aes-256-cts:v2+inlinecrypt_optimized,keydirectory=/metadata/vold/metadata_encryption,fsverity"
    assert old_data_line in rec_fstab, "Expected /data line not found in recovery.fstab!"
    rec_fstab = rec_fstab.replace(old_data_line, new_data_line)
    extra_fstab = (
        "\n/dev/block/by-name/persist      /mnt/vendor/persist  ext4    noatime,nosuid,nodev,noauto_da_alloc,commit=1,nodelalloc    wait,check,formattable\n"
        "/dev/block/by-name/tranfs       /tranfs              ext4    noatime,nosuid,nodev,noauto_da_alloc,discard                wait,check,formattable,nofail\n"
    )
    if "/mnt/vendor/persist" not in rec_fstab:
        rec_fstab += extra_fstab
    rec_fstab_bytes = rec_fstab.encode("utf-8")
    twrp_map["system/etc/recovery.fstab"] = (len(rec_fstab_bytes), 0o100644, rec_fstab_bytes)

    # 5. Fix #5: Fix init.recovery.trustonic.rc (remove --sfs-reformat, add disabled + setenv LD_LIBRARY_PATH)
    # and init.recovery.mt6893.rc (mount persist/tranfs before starting mobicore, insmod TEE/FP/touch drivers)
    print("5. Fixing init.recovery.trustonic.rc and init.recovery.mt6893.rc...")
    trust_rc = twrp_map["init.recovery.trustonic.rc"][2].decode("utf-8")
    trust_rc = trust_rc.replace("mcDriverDaemon --sfs-reformat --P1", "mcDriverDaemon --P1")
    trust_rc = trust_rc.replace(
        "    user root\n    group root\n    seclabel u:r:recovery:s0",
        "    user root\n    group root\n    setenv LD_LIBRARY_PATH /vendor/lib64:/vendor/lib:/system/lib64:/system/lib:/vendor/lib64/hw:/system/lib64/hw:/sbin\n    disabled\n    seclabel u:r:recovery:s0"
    )
    trust_rc_bytes = trust_rc.encode("utf-8")
    twrp_map["init.recovery.trustonic.rc"] = (len(trust_rc_bytes), 0o100644, trust_rc_bytes)

    mt_rc = """import /init.recovery.trustonic.rc

on early-init
    insmod /lib/modules/tnek.ko
    insmod /lib/modules/transsion_tranlog.ko
    insmod /lib/modules/mcDrvModule.ko
    insmod /lib/modules/spi-mt65xx.ko
    insmod /lib/modules/mtk_disp_notify.ko
    insmod /lib/modules/tran_fp.ko
    insmod /lib/modules/adaptive-ts.ko
    insmod /lib/modules/focaltech_ft3681.ko
    insmod /lib/modules/aw862xx_haptic.ko

on init
    setprop sys.usb.configfs 1
    setprop sys.usb.ffs.aio_compat 1
    export LD_LIBRARY_PATH /system/lib64:/vendor/lib64:/vendor/lib64/hw:/system/lib64/hw
    mkdir /mnt/vendor 0755 root root
    mkdir /mnt/vendor/persist 0771 system system
    mkdir /mnt/vendor/nvcfg 0771 system system
    mkdir /mnt/vendor/protect_f 0770 system system
    mkdir /mnt/vendor/protect_s 0770 system system
    mkdir /tranfs 0771 system system

on fs
    wait /dev/block/by-name/persist 5
    mount ext4 /dev/block/by-name/persist /mnt/vendor/persist noatime nosuid nodev commit=1
    chown system system /mnt/vendor/persist
    chmod 0771 /mnt/vendor/persist
    mkdir /mnt/vendor/persist/mcRegistry 0771 system system
    mkdir /mnt/vendor/persist/paytrigger 0777 system system
    mkdir /mnt/vendor/persist/startPara 0777 system system
    wait /dev/block/by-name/tranfs 5
    mount ext4 /dev/block/by-name/tranfs /tranfs noatime nosuid nodev
    mkdir /tranfs/startPara 0777 system system
    mount ext4 /dev/block/by-name/nvcfg /mnt/vendor/nvcfg noatime nosuid nodev commit=1
    mount ext4 /dev/block/by-name/protect1 /mnt/vendor/protect_f noatime nosuid nodev commit=1
    mount ext4 /dev/block/by-name/protect2 /mnt/vendor/protect_s noatime nosuid nodev commit=1
    chmod 0600 /dev/mobicore
    chown system system /dev/mobicore
    chmod 0666 /dev/mobicore-user
    chown system system /dev/mobicore-user
    setprop vendor.persist.ready 1

on post-fs
    # Support A/B feature for EMMC and UFS boot region
    symlink /dev/block/sda /dev/block/mmcblk0boot0
    symlink /dev/block/sdb /dev/block/mmcblk0boot1
    symlink /dev/block/mmcblk0boot0 /dev/block/platform/bootdevice/by-name/preloader_a
    symlink /dev/block/mmcblk0boot1 /dev/block/platform/bootdevice/by-name/preloader_b

    # Support A/B feature for combo emmc and ufs OTA update
    symlink /dev/block/platform/bootdevice/by-name/preloader_a /dev/block/platform/bootdevice/by-name/preloader_emmc_a
    symlink /dev/block/platform/bootdevice/by-name/preloader_b /dev/block/platform/bootdevice/by-name/preloader_emmc_b
    symlink /dev/block/platform/bootdevice/by-name/preloader_a /dev/block/platform/bootdevice/by-name/preloader_ufs_a
    symlink /dev/block/platform/bootdevice/by-name/preloader_b /dev/block/platform/bootdevice/by-name/preloader_ufs_b

    symlink /dev/block/platform/bootdevice/by-name/preloader_a /dev/block/by-name/preloader_emmc_a
    symlink /dev/block/platform/bootdevice/by-name/preloader_b /dev/block/by-name/preloader_emmc_b
    symlink /dev/block/platform/bootdevice/by-name/preloader_a /dev/block/by-name/preloader_ufs_a
    symlink /dev/block/platform/bootdevice/by-name/preloader_b /dev/block/by-name/preloader_ufs_b

    exec u:r:update_engine:s0 root root -- /system/bin/mtk_plpath_utils
    start mtk.plpath.utils.link

    symlink /dev/block/mapper/pl_a /dev/block/by-name/preloader_raw_a
    symlink /dev/block/mapper/pl_b /dev/block/by-name/preloader_raw_b
    symlink /dev/block/mapper/pl_a /dev/block/platform/bootdevice/by-name/preloader_raw_a
    symlink /dev/block/mapper/pl_b /dev/block/platform/bootdevice/by-name/preloader_raw_b

    start mobicore
    start tee-1-1
    start keymaster-4-1
    start keymaster_attestation-1-1
    start gatekeeper-1-0

on boot
    start boot-hal-1-2
    start health-hal-2-1
    setprop sys.usb.controller "11201000.usb0"

on property:ro.crypto.state=encrypted && property:ro.crypto.type=file
    install_keyring

service keystore_auth /system/bin/keystore_auth
    oneshot
    user system
    group root
    disabled
    seclabel u:r:recovery:s0

service keystore /system/bin/keystore /tmp/misc/keystore
    user root
    group root drmrpc readproc
    disabled
    seclabel u:r:recovery:s0

service gatekeeper-1-0 /vendor/bin/hw/android.hardware.gatekeeper@1.0-service
    interface android.hardware.gatekeeper@1.0::IGatekeeper default
    user root
    group root
    setenv LD_LIBRARY_PATH /vendor/lib64:/vendor/lib:/system/lib64:/system/lib:/vendor/lib64/hw:/system/lib64/hw:/sbin
    disabled
    seclabel u:r:recovery:s0

service keymaster-4-1 /vendor/bin/hw/android.hardware.keymaster@4.1-service.trustonic
    interface android.hardware.keymaster@4.0::IKeymasterDevice default
    interface android.hardware.keymaster@4.1::IKeymasterDevice default
    user root
    group root drmrpc
    setenv LD_LIBRARY_PATH /vendor/lib64:/vendor/lib:/system/lib64:/system/lib:/vendor/lib64/hw:/system/lib64/hw:/sbin
    disabled
    seclabel u:r:recovery:s0

service keymaster_attestation-1-1 /vendor/bin/hw/vendor.mediatek.hardware.keymaster_attestation@1.1-service
    interface vendor.mediatek.hardware.keymaster_attestation@1.0::IKeymasterDevice default
    interface vendor.mediatek.hardware.keymaster_attestation@1.1::IKeymasterDevice default
    user root
    group root
    setenv LD_LIBRARY_PATH /vendor/lib64:/vendor/lib:/system/lib64:/system/lib:/vendor/lib64/hw:/system/lib64/hw:/sbin
    disabled
    seclabel u:r:recovery:s0

service tee-1-1 /vendor/bin/hw/vendor.trustonic.tee@1.1-service
    user root
    group root
    setenv LD_LIBRARY_PATH /vendor/lib64:/vendor/lib:/system/lib64:/system/lib:/vendor/lib64/hw:/system/lib64/hw:/sbin
    disabled
    seclabel u:r:recovery:s0

on property:vendor.sys.listener.registered=true && property:vendor.persist.ready=1
    start mobicore
    start tee-1-1
    start keymaster-4-1
    start keymaster_attestation-1-1
    start gatekeeper-1-0

on property:hwservicemanager.ready=true && property:vendor.persist.ready=1
    start mobicore
    start tee-1-1
    start keymaster-4-1
    start keymaster_attestation-1-1
    start gatekeeper-1-0

on property:ro.crypto.state=unsupported
    stop mobicore
    stop keymaster-4-1
    stop keymaster_attestation-1-1
    stop gatekeeper-1-0
    stop tee-1-1

on property:ro.crypto.state=unencrypted
    stop mobicore
    stop keymaster-4-1
    stop keymaster_attestation-1-1
    stop gatekeeper-1-0
    stop tee-1-1

on property:twrp.all.users.decrypted=true
    stop mobicore
    stop keymaster-4-1
    stop keymaster_attestation-1-1
    stop gatekeeper-1-0
    stop tee-1-1
"""
    mt_rc_bytes = mt_rc.encode("utf-8")
    twrp_map["init.recovery.mt6893.rc"] = (len(mt_rc_bytes), 0o100750, mt_rc_bytes)

    # 6. Fix #6: Fix prop.default to match stock 2024-10-05 security_patch and build ID SP1A.210812.016
    print("6. Fixing prop.default with stock security_patch=2024-10-05 and Trustonic Keymaster 4.1 properties...")
    prop = twrp_map["prop.default"][2].decode("utf-8")
    prop = prop.replace("2024-12-31", "2024-10-05")
    prop = prop.replace("SP2A.220405.004", "SP1A.210812.016")
    prop = prop.replace(
        "infinix/twrp_X6710/X6710:12/SP1A.210812.016/runner04101248:eng/test-keys",
        "Infinix/X6710-GL/Infinix-X6710:12/SP1A.210812.016/241029V637:user/release-keys"
    )
    extra_props = [
        "ro.board.first_api_level=30",
        "ro.vendor.mtk_svp_on_mtee_support=1",
        "ro.vendor.mediatek.platform=MT6893",
        "ro.vendor.tran.trans_pay_tee=1",
        "ro.hardware.paytrigger=trustonic",
        "ro.vendor.keymaster_version=4.1",
        "ro.vendor.tran.version.release=X6710U-H931D-S-241029V637",
        "ro.vendor.mediatek.version.release=alps-mp-s0.mp1.rc-V15.240_reallytek.s0mp1rc.k61v1.64.bsp_P36",
    ]
    for ep in extra_props:
        k = ep.split("=")[0] + "="
        if k not in prop:
            prop += "\n" + ep
    prop += "\n"
    prop_bytes = prop.encode("utf-8")
    twrp_map["prop.default"] = (len(prop_bytes), 0o100600, prop_bytes)

    # 7. Verify zero missing DT_NEEDED dependencies across the ENTIRE CPIO archive!
    print("7. Verifying ELF DT_NEEDED closure across all binaries and libraries...")
    have_libs = {k.split("/")[-1]: k for k in twrp_map if k.endswith(".so")}
    def parse_dt_needed(elf):
        if len(elf) < 64 or elf[:4] != b"\x7fELF" or elf[4] != 2:
            return []
        e_shoff = struct.unpack("<Q", elf[40:48])[0]
        e_shentsize, e_shnum, e_shstrndx = struct.unpack("<3H", elf[58:64])
        if e_shoff == 0 or e_shoff + e_shnum * e_shentsize > len(elf):
            return []
        sections = []
        for i in range(e_shnum):
            off = e_shoff + i * e_shentsize
            sh_name, sh_type, sh_flags, sh_addr, sh_offset, sh_size, sh_link = struct.unpack("<IIQQQQI", elf[off:off+44])
            sections.append((sh_type, sh_offset, sh_size, sh_link))
        needed = []
        for sh_type, sh_offset, sh_size, sh_link in sections:
            if sh_type == 6 and sh_link < len(sections):
                strtab_off, strtab_size = sections[sh_link][1], sections[sh_link][2]
                strtab = elf[strtab_off:strtab_off+strtab_size]
                for pos in range(sh_offset, sh_offset + sh_size, 16):
                    d_tag, d_val = struct.unpack("<QQ", elf[pos:pos+16])
                    if d_tag == 1:
                        end = strtab.find(b"\x00", d_val)
                        needed.append(strtab[d_val:end].decode())
                    elif d_tag == 0:
                        break
        return needed

    missing_count = 0
    for k, (s, m, c) in sorted(twrp_map.items()):
        if c[:4] == b"\x7fELF":
            missing = [lib for lib in parse_dt_needed(c) if lib not in have_libs]
            if missing:
                print(f"  ERROR: {k} still missing {missing}")
                missing_count += 1
    print(f"  ELF dependency check: {missing_count} binaries with missing libraries!")
    assert missing_count == 0, "Found missing ELF libraries!"

    # 8. Build new CPIO archive in clean sorted path order (matching mkbootfs)
    print("8. Packing fixed CPIO archive in canonical mkbootfs order...")
    sorted_names = sorted(twrp_map.keys())
    final_entries = [(n, twrp_map[n][0], twrp_map[n][1], twrp_map[n][2]) for n in sorted_names]
    cpio_bytes = build_cpio(final_entries)
    fixed_cpio_path = os.path.join(BASE_DIR, "fixed_twrp.cpio")
    with open(fixed_cpio_path, "wb") as f:
        f.write(cpio_bytes)
    print(f"  Wrote {fixed_cpio_path} ({len(cpio_bytes)} bytes, {len(final_entries)} entries)")

    # 9. Compress with Lz4Legacy.exe
    print("9. Compressing ramdisk with LZ4 Legacy format (0x184C2102)...")
    fixed_lz4_path = os.path.join(BASE_DIR, "fixed_twrp.cpio.lz4")
    subprocess.run([os.path.join(BASE_DIR, "Lz4Legacy.exe"), fixed_cpio_path, fixed_lz4_path], check=True)
    with open(fixed_lz4_path, "rb") as f:
        comp_ramdisk = f.read()

    # Verify round-trip decompression of our LZ4 Legacy ramdisk!
    kind, roundtrip = decompress_ramdisk(comp_ramdisk)
    assert kind == "lz4_legacy" and roundtrip == cpio_bytes, f"LZ4 roundtrip mismatch: {len(roundtrip)} vs {len(cpio_bytes)}"
    print(f"  LZ4 round-trip decompression verified 100% bit-exact ({len(comp_ramdisk)} bytes compressed -> {len(roundtrip)} bytes decompressed)!")

    # 10. Assemble VNDRBOOT v3 image with stock 241029 header, DTB, and updated AVB0 + AVBf footer
    print("10. Assembling 64 MiB VNDRBOOT v3 image with stock 241029 DTB and updated AVB0 hash descriptor / AVBf footer...")
    with open(os.path.join(BASE_DIR, "stock_241029", "vendor_boot.img"), "rb") as f:
        orig_img = f.read()

    def align(x, p=4096):
        return ((x + p - 1) // p) * p

    orig_vramdisk_size = struct.unpack("<I", orig_img[24:28])[0]
    dtb_size = struct.unpack("<I", orig_img[2100:2104])[0]
    orig_dtb_off = 4096 + align(orig_vramdisk_size)
    dtb_bytes = orig_img[orig_dtb_off:orig_dtb_off + dtb_size]
    orig_vbmeta_off = orig_dtb_off + align(dtb_size)
    orig_vbmeta = bytearray(orig_img[orig_vbmeta_off:orig_vbmeta_off + 640])
    orig_footer = bytearray(orig_img[-64:])

    # Build new image up to after_dtb
    hdr = bytearray(orig_img[:4096])
    new_vramdisk_size = len(comp_ramdisk)
    struct.pack_into("<I", hdr, 24, new_vramdisk_size)

    new_img = bytearray(67108864)
    new_img[:4096] = hdr
    new_img[4096:4096 + new_vramdisk_size] = comp_ramdisk
    new_dtb_off = 4096 + align(new_vramdisk_size)
    new_img[new_dtb_off:new_dtb_off + dtb_size] = dtb_bytes
    new_after_dtb = new_dtb_off + align(dtb_size)
    assert new_after_dtb + 4096 <= 67108864 - 64, "Image exceeds 64 MiB partition size!"

    # Update AvbHashDescriptor in orig_vbmeta (640 bytes)
    struct.pack_into("!Q", orig_vbmeta, 272, new_after_dtb)
    plen, slen, dlen, hflags = struct.unpack("!4I", orig_vbmeta[312:328])
    pname_off = 272 + 56 + 60
    salt_off = pname_off + plen
    digest_off = salt_off + slen
    salt = bytes(orig_vbmeta[salt_off:salt_off + slen])
    new_digest = hashlib.sha256(salt + bytes(new_img[:new_after_dtb])).digest()
    orig_vbmeta[digest_off:digest_off + dlen] = new_digest

    new_img[new_after_dtb:new_after_dtb + 640] = orig_vbmeta

    # Update AVBf footer (last 64 bytes)
    struct.pack_into("!3Q", orig_footer, 12, new_after_dtb, new_after_dtb, 640)
    new_img[-64:] = orig_footer

    out_scratch = os.path.join(BASE_DIR, "x6710twrp_fixed.img")
    out_d_drive = r"D:\x6710twrp_fixed.img"
    with open(out_scratch, "wb") as f:
        f.write(new_img)
    with open(out_d_drive, "wb") as f:
        f.write(new_img)

    sha = hashlib.sha256(new_img).hexdigest()
    print(f"SUCCESS! Wrote fixed 64 MiB TWRP image:")
    print(f"  - {out_scratch}")
    print(f"  - {out_d_drive}")
    print(f"  SHA-256: {sha}")
    print(f"  vramdisk_size: {new_vramdisk_size} bytes, dtb_off: 0x{new_dtb_off:x}, vbmeta_off: 0x{new_after_dtb:x}")

if __name__ == "__main__":
    main()
