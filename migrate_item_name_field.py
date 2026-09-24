"""One-time migration of items.dat from a 32-byte to 64-byte name field."""

from __future__ import annotations

import os
import shutil
import struct
from pathlib import Path

from inventory_system import ITEM_STRUCT, encode_fixed


OLD_ITEM_STRUCT = struct.Struct("<II32s24s12sIIfB3x")
DATA_PATH = Path("data/items.dat")
BACKUP_PATH = Path("data/items.dat.v2-32-byte-name.bak")
TEMP_PATH = Path("data/items.dat.migrating-name")

# Complete names from the sample dataset.  The old field already discarded
# bytes beyond byte 32, so the missing suffixes must be recovered by item ID.
SAMPLE_ITEM_NAMES = {
    1001: "ปากกาลูกลื่น",
    1002: "ดินสอ",
    1003: "กระดาษ A4",
    1004: "แฟ้มเอกสาร",
    1005: "เครื่องคิดเลข",
    1006: "เครื่องพิมพ์",
    1007: "สาย USB",
    1008: "เมาส์",
    1009: "เก้าอี้สำนักงาน",
    1010: "โต๊ะทำงาน",
}


def main() -> int:
    if not DATA_PATH.exists():
        print("ไม่พบ data/items.dat")
        return 1

    size = DATA_PATH.stat().st_size
    if size == 0:
        print("items.dat ว่าง ไม่ต้องแปลงข้อมูล")
        return 0
    if size % ITEM_STRUCT.size == 0 and size % OLD_ITEM_STRUCT.size != 0:
        print("items.dat ใช้ชื่อพัสดุขนาด 64 ไบต์อยู่แล้ว")
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
                item_id = values[0]
                full_name = SAMPLE_ITEM_NAMES.get(item_id)
                if full_name is None:
                    name_bytes = values[2].rstrip(b"\x00").ljust(64, b"\x00")
                else:
                    name_bytes = encode_fixed(full_name, 64)
                target.write(
                    ITEM_STRUCT.pack(
                        values[0],
                        values[1],
                        name_bytes,
                        values[3],
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
