$(call inherit-product, $(SRC_TARGET_DIR)/product/core_64_bit.mk)
$(call inherit-product, $(SRC_TARGET_DIR)/product/full_base_telephony.mk)
$(call inherit-product, $(SRC_TARGET_DIR)/product/languages_full.mk)

# Inherit TWRP common configuration
$(call inherit-product, vendor/twrp/config/common.mk)

# Inherit device configuration
$(call inherit-product, device/infinix/X6710/device.mk)

PRODUCT_DEVICE := X6710
PRODUCT_NAME := twrp_X6710
PRODUCT_BRAND := Infinix
PRODUCT_MODEL := Infinix Note 30 VIP
PRODUCT_MANUFACTURER := INFINIX
PRODUCT_RELEASE_NAME := Infinix Note 30 VIP

PRODUCT_BUILD_PROP_OVERRIDES += \
    TARGET_DEVICE=Infinix-X6710 \
    PRODUCT_NAME=X6710-GL \
    PRIVATE_BUILD_DESC="full_h931-user 12 SP1A.210812.016 241029V637 release-keys"

BUILD_FINGERPRINT := Infinix/X6710-GL/Infinix-X6710:12/SP1A.210812.016/241029V637:user/release-keys
