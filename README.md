# Infinix Note 30 VIP (X6710 / MT6893) - Tam Çalışan TWRP & Device Tree (`241029V827`)

Bu depo, **Infinix Note 30 VIP (`Infinix-X6710`, MediaTek Dimensity 8050 / MT6893)** cihazı için hem **normal Android açılışında parmak izi (`tran_fp.ko` / Goodix) ve ekran kilidini (Trustonic TEE / Keymaster 4.1 / Gatekeeper 1.0) bozmayan** hem de **TWRP içinde FBEv2 (`/data`) şifre çözmeyi çalıştıran** düzeltilmiş TWRP `vendor_boot.img` kaynak ağacını ve hazır imajını içerir.

---

## İndirme (Hazır İmajlar)

Hazır derlenmiş ve 5 aşamalı doğrulamadan geçmiş `x6710twrp_fixed.img` (`64 MiB`) ile orijinal stok `vendor_boot_stock_241029.img` yedek dosyasını [**Releases (Sürümler)**](../../releases) sayfasından doğrudan indirebilirsiniz:

- **`x6710twrp_fixed.img`**
  - **Uyumlu Stok ROM:** `X6710-H931DJ-U-GL-241029V827` (`SP1A.210812.016`, Güvenlik Yaması: `2024-10-05`)
  - **Boyut:** `67.108.864` bayt (`64 MiB`)
  - **SHA-256:** `82d65c87f6657f5220912a3308d3aabf15800bb6729f8b53da78b3cff54d6998`
- **`vendor_boot_stock_241029.img` (Orijinal Stok Yedek)**
  - **Boyut:** `67.108.864` bayt (`64 MiB`)
  - **SHA-256:** `78f83b1afe0ee11514c3d442251b070800bfb07414dd6740c76c6b2aa68c0a42`

---

## Kurulum (Fastboot)

```bash
fastboot flash vendor_boot x6710twrp_fixed.img
```

Orijinal stok `vendor_boot` imajına geri dönmek isterseniz:
```bash
fastboot flash vendor_boot vendor_boot_stock_241029.img
```

---

## Giderilen Kritik Güvenlik ve Parmak İzi Sorunları

1. **Stok `241029V827` Çekirdek Modülleri (`/lib/modules/*` - 225 Dosya) ve `first_stage_ramdisk/*` (25 Dosya) Birebir Korundu:**
   - `VNDRBOOT` v3 mimarisinde `vendor_boot` bölümü hem normal Android açılışında hem de TWRP kurtarma modunda ortak kullanılır.
   - `mcDrvModule.ko` (Trustonic TEE sürücüsü), `tran_fp.ko` (Parmak izi sürücüsü), `tnek.ko`, `transsion_tranlog.ko`, `log_store.ko`, `modules.dep`, `modules.load` ve `modules.load.recovery` dosyaları stok `241029V827` ROM ile %100 bit-bit aynıdır.
2. **Stok `241029V827` DTB (`mediatek,memory-ssmr-features = 0x1c000000`) Kullanıldı:**
   - Trustonic TEE güvenli paylaşımlı bellek bölgelerini (`SSMR`) eksik ayıran eski DTB (`0x10000000`) yerine stok `241029V827` DTB'si (`0x1c000000`) ve `AVB0` üstverisi kullanıldı.
3. **TWRP İçinde Eksik Olan 16 Adet `DT_NEEDED` Şifre Çözme Kütüphanesi Eklendi:**
   - Stok `super.img` (`vendor_a` ve `system_a`) içinden `android.hardware.keymaster@3.0/4.0/4.1.so`, `android.hardware.gatekeeper@1.0.so`, `libgatekeeper.so`, `libkeymaster4.so`, `libkeymaster41.so`, `libkmsetkey.so`, `kmsetkey_ca.trustonic`, `libcppbor_external.so`, `libcppcose_rkp.so`, `libsoft_attestation_cert.so`, `libtranlog.so` ve `vendor.mediatek.hardware.keymaster_attestation@1.0/1.1` dosyaları çıkarılıp hem `/vendor/lib64` hem `/system/lib64` altına eklendi (`0` eksik ELF bağımlılığı).
4. **`recovery.fstab` FBEv2 + `inlinecrypt` + `keydirectory` Düzeltmesi:**
   - `/data` satırına `inlinecrypt` ve `fileencryption=aes-256-xts:aes-256-cts:v2+inlinecrypt_optimized,keydirectory=/metadata/vold/metadata_encryption,fsverity` bayrakları ile `/mnt/vendor/persist` ve `/tranfs` bağlama noktaları eklendi.
5. **`--sfs-reformat` Kaldırıldı & `hwservicemanager` Yarış Durumu (Race Condition) Çözüldü:**
   - `init.recovery.trustonic.rc` içerisindeki `mcDriverDaemon --sfs-reformat` bayrağı kaldırılarak `/mnt/vendor/persist/mcRegistry` içindeki Trustonic güvenli dosya sisteminin sıfırlanması engellendi.
   - `mobicore`, `tee-1-1`, `keymaster-4-1`, `keymaster_attestation-1-1` ve `gatekeeper-1-0` servislerinin yalnızca `/mnt/vendor/persist` ve `/tranfs` bölümleri bağlandıktan (`vendor.persist.ready=1`) sonra başlaması sağlandı.
6. **Güvenlik Yaması Tarihi (`2024-10-05`) Eşitlendi:**
   - `prop.default` ve `BoardConfig.mk` içindeki `ro.build.version.security_patch` ve `ro.vendor.build.security_patch` değerleri stok `241029V827` ROM ile birebir aynı (`2024-10-05`, `SP1A.210812.016`) yapıldı.
