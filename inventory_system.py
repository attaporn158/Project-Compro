"""Core logic for a fixed-length binary inventory management system.

Only modules from the Python standard library are used.  Every record is packed
with an explicit little-endian ``struct.Struct`` format.
"""

from __future__ import annotations

import math
import os
import struct
import time
import unicodedata
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterator, Sequence, TypeVar


# Little-endian, standard sizes, no implicit alignment.
ITEM_STRUCT = struct.Struct("<II32s24s12sIIfB3x")
CATEGORY_STRUCT = struct.Struct("<I64s80sB3x")
LOG_STRUCT = struct.Struct("<QIBIIf32s16sB3x")

ACTIVE = 1
DELETED = 0

OP_ADD = 1
OP_UPDATE = 2
OP_DELETE = 3
OP_RECEIVE = 4
OP_ISSUE = 5

OPERATION_NAMES = {
    OP_ADD: "ADD",
    OP_UPDATE: "UPDATE",
    OP_DELETE: "DELETE",
    OP_RECEIVE: "RECEIVE",
    OP_ISSUE: "ISSUE",
}

UINT32_MAX = 2**32 - 1
UINT64_MAX = 2**64 - 1


class InventoryError(Exception):
    """Base exception shown to the user without a traceback."""


class ValidationError(InventoryError):
    """Raised when input violates the data contract."""


class NotFoundError(InventoryError):
    """Raised when an active record cannot be found."""


class DuplicateError(InventoryError):
    """Raised when a key is already active."""


class StorageCorruptionError(InventoryError):
    """Raised when a binary file is not a whole number of records."""


def encode_fixed(text: str, size: int) -> bytes:
    """Encode UTF-8, truncate on a character boundary, and NUL-pad to size."""
    raw = str(text).encode("utf-8")
    if len(raw) > size:
        raw = raw[:size]
        while raw:
            try:
                raw.decode("utf-8")
                break
            except UnicodeDecodeError:
                raw = raw[:-1]
    return raw.ljust(size, b"\x00")


def decode_fixed(raw: bytes) -> str:
    """Decode a fixed-length NUL-padded UTF-8 field."""
    payload = raw.split(b"\x00", 1)[0]
    try:
        return payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise StorageCorruptionError("พบข้อความ UTF-8 ที่เสียหายในไฟล์ข้อมูล") from exc


def _required_text(value: str, field_name: str) -> str:
    value = value.strip()
    if not value:
        raise ValidationError(f"{field_name} ห้ามว่าง")
    return value


def _uint32(value: int, field_name: str, *, allow_zero: bool = True) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValidationError(f"{field_name} ต้องเป็นจำนวนเต็ม")
    minimum = 0 if allow_zero else 1
    if not minimum <= value <= UINT32_MAX:
        raise ValidationError(f"{field_name} ต้องอยู่ระหว่าง {minimum} ถึง {UINT32_MAX}")
    return value


def _nonnegative_float(value: float, field_name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"{field_name} ต้องเป็นตัวเลข") from exc
    if not math.isfinite(number) or number < 0:
        raise ValidationError(f"{field_name} ต้องเป็นเลขที่ไม่ติดลบและมีค่าจำกัด")
    return number


@dataclass(frozen=True)
class Item:
    item_id: int
    category_id: int
    name: str
    unit: str
    location: str
    quantity: int
    reorder_level: int
    unit_price: float
    status: int = ACTIVE

    def validate(self) -> "Item":
        _uint32(self.item_id, "รหัสพัสดุ", allow_zero=False)
        _uint32(self.category_id, "รหัสหมวดหมู่", allow_zero=False)
        _required_text(self.name, "ชื่อพัสดุ")
        _required_text(self.unit, "หน่วยนับ")
        _required_text(self.location, "ตำแหน่งจัดเก็บ")
        _uint32(self.quantity, "จำนวนคงเหลือ")
        _uint32(self.reorder_level, "จุดสั่งซื้อขั้นต่ำ")
        _nonnegative_float(self.unit_price, "ราคาต่อหน่วย")
        if self.status not in (ACTIVE, DELETED):
            raise ValidationError("สถานะพัสดุต้องเป็น 0 หรือ 1")
        return self

    def pack(self) -> bytes:
        self.validate()
        return ITEM_STRUCT.pack(
            self.item_id,
            self.category_id,
            encode_fixed(self.name, 32),
            encode_fixed(self.unit, 24),
            encode_fixed(self.location, 12),
            self.quantity,
            self.reorder_level,
            self.unit_price,
            self.status,
        )

    @classmethod
    def unpack(cls, raw: bytes) -> "Item":
        values = ITEM_STRUCT.unpack(raw)
        return cls(
            values[0], values[1], decode_fixed(values[2]), decode_fixed(values[3]),
            decode_fixed(values[4]), values[5], values[6], values[7], values[8]
        )


@dataclass(frozen=True)
class Category:
    category_id: int
    name: str
    description: str
    status: int = ACTIVE

    def validate(self) -> "Category":
        _uint32(self.category_id, "รหัสหมวดหมู่", allow_zero=False)
        _required_text(self.name, "ชื่อหมวดหมู่")
        if self.status not in (ACTIVE, DELETED):
            raise ValidationError("สถานะหมวดหมู่ต้องเป็น 0 หรือ 1")
        return self

    def pack(self) -> bytes:
        self.validate()
        return CATEGORY_STRUCT.pack(
            self.category_id,
            encode_fixed(self.name, 64),
            encode_fixed(self.description, 80),
            self.status,
        )

    @classmethod
    def unpack(cls, raw: bytes) -> "Category":
        values = CATEGORY_STRUCT.unpack(raw)
        return cls(values[0], decode_fixed(values[1]), decode_fixed(values[2]), values[3])


@dataclass(frozen=True)
class TransactionLog:
    timestamp: int
    log_seq: int
    op_code: int
    item_id: int
    quantity: int
    balance: float
    operator: str
    note: str
    status_after: int

    def pack(self) -> bytes:
        if not 0 <= self.timestamp <= UINT64_MAX:
            raise ValidationError("timestamp ไม่ถูกต้อง")
        _uint32(self.log_seq, "ลำดับประวัติ", allow_zero=False)
        if self.op_code not in OPERATION_NAMES:
            raise ValidationError("รหัสการทำงานไม่ถูกต้อง")
        _uint32(self.item_id, "รหัสพัสดุ", allow_zero=False)
        _uint32(self.quantity, "จำนวน")
        _nonnegative_float(self.balance, "ยอดคงเหลือ")
        _required_text(self.operator, "ผู้ปฏิบัติงาน")
        if self.status_after not in (ACTIVE, DELETED):
            raise ValidationError("สถานะหลังทำรายการไม่ถูกต้อง")
        return LOG_STRUCT.pack(
            self.timestamp,
            self.log_seq,
            self.op_code,
            self.item_id,
            self.quantity,
            self.balance,
            encode_fixed(self.operator, 32),
            encode_fixed(self.note, 16),
            self.status_after,
        )

    @classmethod
    def unpack(cls, raw: bytes) -> "TransactionLog":
        values = LOG_STRUCT.unpack(raw)
        return cls(
            values[0], values[1], values[2], values[3], values[4], values[5],
            decode_fixed(values[6]), decode_fixed(values[7]), values[8]
        )


T = TypeVar("T")


class FixedRecordFile:
    """Small fixed-record binary file abstraction with fsync on every write."""

    def __init__(
        self,
        path: Path,
        record_struct: struct.Struct,
        unpacker: Callable[[bytes], T],
    ) -> None:
        self.path = path
        self.record_struct = record_struct
        self.unpacker = unpacker
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch(exist_ok=True)
        self.validate_size()

    @property
    def record_count(self) -> int:
        self.validate_size()
        return self.path.stat().st_size // self.record_struct.size

    def validate_size(self) -> None:
        size = self.path.stat().st_size
        if size % self.record_struct.size != 0:
            raise StorageCorruptionError(
                f"ไฟล์ {self.path.name} มีขนาด {size} ไบต์ "
                f"ซึ่งไม่หารด้วยขนาดระเบียน {self.record_struct.size} ลงตัว"
            )

    def records(self) -> Iterator[tuple[int, T]]:
        self.validate_size()
        with self.path.open("rb") as stream:
            index = 0
            while raw := stream.read(self.record_struct.size):
                if len(raw) != self.record_struct.size:
                    raise StorageCorruptionError(f"ระเบียนท้ายไฟล์ {self.path.name} ไม่สมบูรณ์")
                yield index, self.unpacker(raw)
                index += 1

    def write(self, index: int, packed: bytes) -> None:
        if len(packed) != self.record_struct.size:
            raise ValueError("packed record has an invalid size")
        if index < 0 or index >= self.record_count:
            raise IndexError("record index out of range")
        with self.path.open("r+b") as stream:
            stream.seek(index * self.record_struct.size)
            stream.write(packed)
            stream.flush()
            os.fsync(stream.fileno())

    def append(self, packed: bytes) -> int:
        if len(packed) != self.record_struct.size:
            raise ValueError("packed record has an invalid size")
        index = self.record_count
        with self.path.open("ab") as stream:
            stream.write(packed)
            stream.flush()
            os.fsync(stream.fileno())
        return index


class InventoryStorage:
    """CRUD service backed by three binary files."""

    def __init__(self, data_dir: str | Path = "data") -> None:
        self.data_dir = Path(data_dir)
        self.items_file = FixedRecordFile(self.data_dir / "items.dat", ITEM_STRUCT, Item.unpack)
        self.categories_file = FixedRecordFile(
            self.data_dir / "categories.dat", CATEGORY_STRUCT, Category.unpack
        )
        self.logs_file = FixedRecordFile(
            self.data_dir / "transactions.dat", LOG_STRUCT, TransactionLog.unpack
        )

    def _find_item_entry(self, item_id: int, *, include_deleted: bool = False) -> tuple[int, Item]:
        _uint32(item_id, "รหัสพัสดุ", allow_zero=False)
        for index, item in self.items_file.records():
            if item.item_id == item_id and (include_deleted or item.status == ACTIVE):
                return index, item
        raise NotFoundError(f"ไม่พบพัสดุรหัส {item_id}")

    def _find_category_entry(
        self, category_id: int, *, include_deleted: bool = False
    ) -> tuple[int, Category]:
        _uint32(category_id, "รหัสหมวดหมู่", allow_zero=False)
        for index, category in self.categories_file.records():
            if category.category_id == category_id and (include_deleted or category.status == ACTIVE):
                return index, category
        raise NotFoundError(f"ไม่พบหมวดหมู่รหัส {category_id}")

    @staticmethod
    def _first_deleted(records: Iterator[tuple[int, T]]) -> int | None:
        for index, record in records:
            if getattr(record, "status", ACTIVE) == DELETED:
                return index
        return None

    def categories(self, *, include_deleted: bool = False) -> list[Category]:
        return [
            category
            for _, category in self.categories_file.records()
            if include_deleted or category.status == ACTIVE
        ]

    def get_category(self, category_id: int, *, include_deleted: bool = False) -> Category:
        return self._find_category_entry(category_id, include_deleted=include_deleted)[1]

    def add_category(self, category: Category) -> None:
        category = replace(category, status=ACTIVE)
        category.validate()
        same_deleted_index: int | None = None
        free_index: int | None = None
        for index, existing in self.categories_file.records():
            if existing.category_id == category.category_id:
                if existing.status == ACTIVE:
                    raise DuplicateError(f"มีหมวดหมู่รหัส {category.category_id} อยู่แล้ว")
                same_deleted_index = index
            if free_index is None and existing.status == DELETED:
                free_index = index
        target = same_deleted_index if same_deleted_index is not None else free_index
        if target is None:
            self.categories_file.append(category.pack())
        else:
            self.categories_file.write(target, category.pack())

    def update_category(self, category_id: int, *, name: str, description: str) -> Category:
        index, current = self._find_category_entry(category_id)
        updated = replace(current, name=name, description=description).validate()
        self.categories_file.write(index, updated.pack())
        return updated

    def delete_category(self, category_id: int) -> None:
        index, category = self._find_category_entry(category_id)
        if any(item.category_id == category_id for item in self.items()):
            raise ValidationError("ลบหมวดหมู่นี้ไม่ได้ เพราะยังมีพัสดุที่ใช้งานอยู่ในหมวดหมู่")
        self.categories_file.write(index, replace(category, status=DELETED).pack())

    def items(self, *, include_deleted: bool = False) -> list[Item]:
        return [
            item
            for _, item in self.items_file.records()
            if include_deleted or item.status == ACTIVE
        ]

    def get_item(self, item_id: int, *, include_deleted: bool = False) -> Item:
        return self._find_item_entry(item_id, include_deleted=include_deleted)[1]

    def add_item(self, item: Item, *, operator: str, note: str = "เพิ่มพัสดุ") -> None:
        item = replace(item, status=ACTIVE)
        item.validate()
        self.get_category(item.category_id)
        same_deleted_index: int | None = None
        free_index: int | None = None
        for index, existing in self.items_file.records():
            if existing.item_id == item.item_id:
                if existing.status == ACTIVE:
                    raise DuplicateError(f"มีพัสดุรหัส {item.item_id} อยู่แล้ว")
                same_deleted_index = index
            if free_index is None and existing.status == DELETED:
                free_index = index
        target = same_deleted_index if same_deleted_index is not None else free_index
        if target is None:
            self.items_file.append(item.pack())
        else:
            self.items_file.write(target, item.pack())
        self._append_log(OP_ADD, item, item.quantity, operator, note)

    def update_item(self, item_id: int, *, operator: str, note: str = "แก้ไข", **changes: object) -> Item:
        index, current = self._find_item_entry(item_id)
        allowed = {"category_id", "name", "unit", "location", "quantity", "reorder_level", "unit_price"}
        unexpected = set(changes) - allowed
        if unexpected:
            raise ValidationError(f"ไม่อนุญาตให้แก้ไขฟิลด์: {', '.join(sorted(unexpected))}")
        updated = replace(current, **changes).validate()
        self.get_category(updated.category_id)
        changed_quantity = abs(updated.quantity - current.quantity)
        self.items_file.write(index, updated.pack())
        self._append_log(OP_UPDATE, updated, changed_quantity, operator, note)
        return updated

    def delete_item(self, item_id: int, *, operator: str, note: str = "ลบพัสดุ") -> None:
        index, item = self._find_item_entry(item_id)
        deleted = replace(item, status=DELETED)
        self.items_file.write(index, deleted.pack())
        self._append_log(OP_DELETE, deleted, 0, operator, note)

    def receive(self, item_id: int, quantity: int, *, operator: str, note: str = "รับเข้า") -> Item:
        _uint32(quantity, "จำนวนรับเข้า", allow_zero=False)
        index, item = self._find_item_entry(item_id)
        if item.quantity + quantity > UINT32_MAX:
            raise ValidationError("จำนวนคงเหลือเกินขอบเขตที่ไฟล์รองรับ")
        updated = replace(item, quantity=item.quantity + quantity)
        self.items_file.write(index, updated.pack())
        self._append_log(OP_RECEIVE, updated, quantity, operator, note)
        return updated

    def issue(self, item_id: int, quantity: int, *, operator: str, note: str = "เบิกจ่าย") -> Item:
        _uint32(quantity, "จำนวนเบิก", allow_zero=False)
        index, item = self._find_item_entry(item_id)
        if quantity > item.quantity:
            raise ValidationError(f"เบิกไม่ได้: คงเหลือ {item.quantity} แต่ขอเบิก {quantity}")
        updated = replace(item, quantity=item.quantity - quantity)
        self.items_file.write(index, updated.pack())
        self._append_log(OP_ISSUE, updated, quantity, operator, note)
        return updated

    def _next_log_seq(self) -> int:
        maximum = 0
        for _, log in self.logs_file.records():
            maximum = max(maximum, log.log_seq)
        if maximum >= UINT32_MAX:
            raise ValidationError("ลำดับประวัติเต็มแล้ว")
        return maximum + 1

    def _append_log(
        self, op_code: int, item: Item, quantity: int, operator: str, note: str
    ) -> TransactionLog:
        log = TransactionLog(
            timestamp=int(time.time()),
            log_seq=self._next_log_seq(),
            op_code=op_code,
            item_id=item.item_id,
            quantity=quantity,
            balance=float(item.quantity),
            operator=operator,
            note=note,
            status_after=item.status,
        )
        self.logs_file.append(log.pack())
        return log

    def logs(self, *, limit: int | None = None) -> list[TransactionLog]:
        records = [log for _, log in self.logs_file.records()]
        if limit is not None:
            return records[-max(0, limit):]
        return records

    def filtered_items(
        self,
        *,
        category_id: int | None = None,
        low_stock_only: bool = False,
        include_deleted: bool = False,
    ) -> list[Item]:
        result = self.items(include_deleted=include_deleted)
        if category_id is not None:
            result = [item for item in result if item.category_id == category_id]
        if low_stock_only:
            result = [item for item in result if item.status == ACTIVE and item.quantity <= item.reorder_level]
        return result

    def statistics(self) -> dict[str, float | int]:
        all_items = self.items(include_deleted=True)
        active = [item for item in all_items if item.status == ACTIVE]
        deleted = [item for item in all_items if item.status == DELETED]
        total_quantity = sum(item.quantity for item in active)
        total_value = sum(item.quantity * item.unit_price for item in active)
        return {
            "total_records": len(all_items),
            "active_records": len(active),
            "deleted_records": len(deleted),
            "free_slots": len(deleted),
            "total_quantity": total_quantity,
            "low_stock": sum(item.quantity <= item.reorder_level for item in active),
            "total_value": total_value,
            "min_price": min((item.unit_price for item in active), default=0.0),
            "max_price": max((item.unit_price for item in active), default=0.0),
            "avg_price": sum((item.unit_price for item in active), 0.0) / len(active) if active else 0.0,
        }


def display_width(value: object) -> int:
    """Return the number of terminal columns used by Unicode text.

    Thai tone marks and combining vowels occupy the same terminal cell as the
    preceding character, so using ``len()`` directly makes table columns lean
    to the left.  Full-width East Asian characters count as two columns.
    """
    width = 0
    for char in str(value):
        if unicodedata.category(char) in {"Mn", "Me", "Cf"}:
            continue
        width += 2 if unicodedata.east_asian_width(char) in {"W", "F"} else 1
    return width


def _truncate_display(value: object, width: int) -> str:
    text = str(value)
    if display_width(text) <= width:
        return text
    if width <= 0:
        return ""
    target = max(0, width - 1)
    result: list[str] = []
    used = 0
    for char in text:
        char_width = 0 if unicodedata.category(char) in {"Mn", "Me", "Cf"} else (
            2 if unicodedata.east_asian_width(char) in {"W", "F"} else 1
        )
        if used + char_width > target:
            break
        result.append(char)
        used += char_width
    return "".join(result).rstrip() + "…"


def _fit_cell(value: object, width: int, alignment: str = "left") -> str:
    text = _truncate_display(value, width)
    padding = " " * max(0, width - display_width(text))
    if alignment == "right":
        return padding + text
    if alignment == "center":
        left = len(padding) // 2
        return padding[:left] + text + padding[left:]
    return text + padding


def render_table(
    headers: Sequence[object],
    rows: Sequence[Sequence[object]],
    widths: Sequence[int],
    alignments: Sequence[str] | None = None,
) -> str:
    """Render a Unicode table whose rows have equal terminal display width."""
    if not (len(headers) == len(widths)):
        raise ValueError("headers and widths must have the same length")
    if any(len(row) != len(headers) for row in rows):
        raise ValueError("every row must contain one value per header")
    alignments = alignments or ["left"] * len(headers)
    if len(alignments) != len(headers):
        raise ValueError("alignments and headers must have the same length")

    top = "┌" + "┬".join("─" * (width + 2) for width in widths) + "┐"
    middle = "├" + "┼".join("─" * (width + 2) for width in widths) + "┤"
    bottom = "└" + "┴".join("─" * (width + 2) for width in widths) + "┘"

    def make_row(values: Sequence[object], row_alignments: Sequence[str]) -> str:
        cells = [
            f" {_fit_cell(value, width, alignment)} "
            for value, width, alignment in zip(values, widths, row_alignments)
        ]
        return "│" + "│".join(cells) + "│"

    output = [top, make_row(headers, ["center"] * len(headers)), middle]
    output.extend(make_row(row, alignments) for row in rows)
    output.append(bottom)
    return "\n".join(output)


def format_items(items: Sequence[Item]) -> str:
    if not items:
        return "ไม่พบข้อมูลพัสดุ"
    rows = [
        (
            item.item_id,
            item.category_id,
            item.name,
            item.unit,
            item.location,
            f"{item.quantity:,}",
            f"{item.unit_price:,.2f}",
            "Active" if item.status == ACTIVE else "Deleted",
        )
        for item in items
    ]
    return render_table(
        ("ItemID", "Category", "Name", "Unit", "Location", "Quantity", "Unit Price", "Status"),
        rows,
        (8, 8, 24, 10, 12, 10, 14, 9),
        ("right", "right", "left", "left", "left", "right", "right", "center"),
    )


def generate_report(storage: InventoryStorage, output_path: str | Path) -> Path:
    """Generate the required plain-text report and fsync it."""
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    items = storage.items(include_deleted=True)
    active_items = [item for item in items if item.status == ACTIVE]
    categories = {category.category_id: category for category in storage.categories(include_deleted=True)}
    stats = storage.statistics()
    now = datetime.now().astimezone()

    information_table = render_table(
        ("System Information", "Value"),
        (
            ("Generated At", now.isoformat(timespec="seconds")),
            ("App Version", "1.0"),
            ("Endianness", "Little-Endian (<)"),
            ("Encoding", "UTF-8 fixed-length binary records"),
            (
                "Record Size",
                f"items={ITEM_STRUCT.size}, categories={CATEGORY_STRUCT.size}, "
                f"transactions={LOG_STRUCT.size} bytes",
            ),
        ),
        (20, 64),
        ("left", "left"),
    )

    summary_table = render_table(
        ("Summary", "Value", "Unit"),
        (
            ("Total Items (Records)", stats["total_records"], "records"),
            ("Active Items", stats["active_records"], "records"),
            ("Deleted Items", stats["deleted_records"], "records"),
            ("Free Slots", stats["free_slots"], "slots"),
            ("Total Quantity", f"{stats['total_quantity']:,}", "units"),
            ("Low-Stock Items", stats["low_stock"], "records"),
            ("Total Inventory Value", f"{stats['total_value']:,.2f}", "THB"),
        ),
        (28, 18, 10),
        ("left", "right", "left"),
    )

    price_table = render_table(
        ("Price Statistics", "Value", "Unit"),
        (
            ("Minimum", f"{stats['min_price']:,.2f}", "THB"),
            ("Maximum", f"{stats['max_price']:,.2f}", "THB"),
            ("Average", f"{stats['avg_price']:,.2f}", "THB"),
        ),
        (28, 18, 10),
        ("left", "right", "left"),
    )

    category_counts: dict[int, int] = {}
    for item in active_items:
        category_counts[item.category_id] = category_counts.get(item.category_id, 0) + 1
    category_rows: list[tuple[object, ...]] = []
    for category_id, count in sorted(category_counts.items()):
        category = categories.get(category_id)
        category_rows.append((category_id, category.name if category else "Unknown", count))
    category_table = render_table(
        ("Category ID", "Category Name", "Active Items"),
        category_rows or (("-", "ไม่มีข้อมูล", 0),),
        (12, 32, 14),
        ("right", "left", "right"),
    )

    recent = storage.logs(limit=10)
    history_rows: list[tuple[object, ...]] = []
    if recent:
        for log in reversed(recent):
            stamp = datetime.fromtimestamp(log.timestamp).astimezone().strftime("%Y-%m-%d %H:%M:%S")
            history_rows.append(
                (
                    f"#{log.log_seq:06d}",
                    stamp,
                    OPERATION_NAMES.get(log.op_code, "?"),
                    log.item_id,
                    log.quantity,
                    f"{log.balance:,.0f}",
                    log.operator,
                    log.note,
                )
            )
    else:
        history_rows.append(("-", "-", "-", "-", "-", "-", "ไม่มีประวัติ", "-"))
    history_table = render_table(
        ("Seq", "Date / Time", "Operation", "ItemID", "Qty", "Balance", "Operator", "Note"),
        history_rows,
        (8, 19, 9, 8, 8, 10, 14, 14),
        ("right", "left", "center", "right", "right", "right", "left", "left"),
    )

    lines = [
        "=" * 90,
        "INVENTORY MANAGEMENT SYSTEM - SUMMARY REPORT".center(90),
        "=" * 90,
        "",
        information_table,
        "",
        "INVENTORY RECORDS",
        format_items(items),
        "",
        "SUMMARY",
        summary_table,
        "",
        "PRICE STATISTICS (ACTIVE ONLY)",
        price_table,
        "",
        "ITEMS BY CATEGORY (ACTIVE ONLY)",
        category_table,
        "",
        "RECENT OPERATIONS (LATEST 10)",
        history_table,
    ]

    with output.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write("\n".join(lines) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    return output
