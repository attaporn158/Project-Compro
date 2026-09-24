"""One-time migration of categories.dat from a 24-byte to 64-byte name field."""

from __future__ import annotations

import os
import shutil
import struct
from pathlib import Path

from inventory_system import CATEGORY_STRUCT, encode_fixed


OLD_CATEGORY_STRUCT = struct.Struct("<I24s80sB3x")
DATA_PATH = Path("data/categories.dat")
BACKUP_PATH = Path("data/categories.dat.v1-24-byte-name.bak")
TEMP_PATH = Path("data/categories.dat.migrating")

# The original 24-byte field cannot contain the complete UTF-8 names.  These
# are the full names from the sample dataset, keyed by their stable IDs.
SAMPLE_CATEGORY_NAMES = {
    1: "เครื่องเขียน",
    2: "อุปกรณ์สำนักงาน",
    3: "อุปกรณ์อิเล็กทรอนิกส์",
    4: "อุปกรณ์คอมพิวเตอร์",
    5: "เฟอร์นิเจอร์",
}


def main() -> int:
    if not DATA_PATH.exists():
        print("ไม่พบ data/categories.dat")
        return 1

    size = DATA_PATH.stat().st_size
    if size == 0:
        print("categories.dat ว่าง ไม่ต้องแปลงข้อมูล")
        return 0
    if size % CATEGORY_STRUCT.size == 0 and size % OLD_CATEGORY_STRUCT.size != 0:
        print("categories.dat ใช้ชื่อหมวดหมู่ขนาด 64 ไบต์อยู่แล้ว")
        return 0
    if size % OLD_CATEGORY_STRUCT.size != 0:
        print("ยกเลิก: ขนาด categories.dat ไม่ตรงกับโครงสร้างเดิม")
        return 1
    if BACKUP_PATH.exists():
        print(f"ยกเลิก: มีไฟล์สำรองอยู่แล้วที่ {BACKUP_PATH}")
        return 1

    shutil.copy2(DATA_PATH, BACKUP_PATH)
    try:
        with DATA_PATH.open("rb") as source, TEMP_PATH.open("wb") as target:
            while raw := source.read(OLD_CATEGORY_STRUCT.size):
                category_id, old_name, description, status = OLD_CATEGORY_STRUCT.unpack(raw)
                full_name = SAMPLE_CATEGORY_NAMES.get(category_id)
                if full_name is None:
                    # Preserve unknown user-created records byte-for-byte in the
                    # larger field; no information can be reconstructed safely.
                    full_name_bytes = old_name.rstrip(b"\x00").ljust(64, b"\x00")
                else:
                    full_name_bytes = encode_fixed(full_name, 64)
                target.write(
                    CATEGORY_STRUCT.pack(category_id, full_name_bytes, description, status)
                )
            target.flush()
            os.fsync(target.fileno())
        os.replace(TEMP_PATH, DATA_PATH)
    except Exception:
        if TEMP_PATH.exists():
            TEMP_PATH.unlink()
        raise

    print(f"แปลงสำเร็จ: {size // OLD_CATEGORY_STRUCT.size} ระเบียน")
    print(f"ไฟล์สำรอง: {BACKUP_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
