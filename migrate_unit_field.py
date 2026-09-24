"""One-time migration of items.dat from a 16-byte to 24-byte unit field."""

from __future__ import annotations

import os
import shutil
import struct
from pathlib import Path

from inventory_system import ITEM_STRUCT, decode_fixed, encode_fixed


OLD_ITEM_STRUCT = struct.Struct("<II32s16s12sIIfB3x")
DATA_PATH = Path("data/items.dat")
BACKUP_PATH = Path("data/items.dat.v1-16-byte-unit.bak")
TEMP_PATH = Path("data/items.dat.migrating")


def main() -> int:
    if not DATA_PATH.exists():
        print("ไม่พบ data/items.dat")
        return 1

    size = DATA_PATH.stat().st_size
    if size == 0:
        print("items.dat ว่าง ไม่ต้องแปลงข้อมูล")
        return 0
    if size % ITEM_STRUCT.size == 0 and size % OLD_ITEM_STRUCT.size != 0:
        print("items.dat ใช้ unit ขนาด 24 ไบต์อยู่แล้ว")
        return 0
    if size % OLD_ITEM_STRUCT.size != 0:
        print("ยกเลิก: ขนาด items.dat ไม่ตรงกับโครงสร้างเดิม")
        return 1

    if BACKUP_PATH.exists():
        print(f"ยกเลิก: มีไฟล์สำรองอยู่แล้วที่ {BACKUP_PATH}")
        return 1

    shutil.copy2(DATA_PATH, BACKUP_PATH)
    try:
        with DATA_PATH.open("rb") as source, TEMP_PATH.open("wb") as target:
            while raw := source.read(OLD_ITEM_STRUCT.size):
                values = OLD_ITEM_STRUCT.unpack(raw)
                unit = decode_fixed(values[3])
                # The old 16-byte UTF-8 field cut this common unit after 15 bytes.
                if unit == "เครื่":
                    unit = "เครื่อง"
                target.write(
                    ITEM_STRUCT.pack(
                        values[0],
                        values[1],
                        values[2],
                        encode_fixed(unit, 24),
                        values[4],
                        values[5],
                        values[6],
                        values[7],
                        values[8],
                    )
                )
            target.flush()
            os.fsync(target.fileno())
        os.replace(TEMP_PATH, DATA_PATH)
    except Exception:
        if TEMP_PATH.exists():
            TEMP_PATH.unlink()
        raise

    print(f"แปลงสำเร็จ: {size // OLD_ITEM_STRUCT.size} ระเบียน")
    print(f"ไฟล์สำรอง: {BACKUP_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
