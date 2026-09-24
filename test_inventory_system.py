import struct
import tempfile
import unittest
from pathlib import Path

from inventory_system import (
    CATEGORY_STRUCT,
    ITEM_STRUCT,
    LOG_STRUCT,
    Category,
    DuplicateError,
    InventoryStorage,
    Item,
    StorageCorruptionError,
    ValidationError,
    decode_fixed,
    display_width,
    encode_fixed,
    generate_report,
    render_table,
)


class InventorySystemTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = InventoryStorage(self.root / "data")
        self.store.add_category(Category(1, "เครื่องเขียน", "ของใช้สำนักงาน"))

    def tearDown(self):
        self.temp.cleanup()

    @staticmethod
    def sample_item(item_id=1001, quantity=10):
        return Item(item_id, 1, "ปากกาลูกลื่น", "ด้าม", "A-01", quantity, 3, 15.5)

    def test_struct_sizes_are_fixed_and_little_endian(self):
        self.assertEqual(ITEM_STRUCT.size, 92)
        self.assertEqual(CATEGORY_STRUCT.size, 152)
        self.assertEqual(LOG_STRUCT.size, 77)
        self.assertEqual(struct.pack("<I", 1), b"\x01\x00\x00\x00")

    def test_utf8_truncation_keeps_valid_characters_and_exact_size(self):
        packed = encode_fixed("ก" * 20, 32)
        self.assertEqual(len(packed), 32)
        self.assertEqual(decode_fixed(packed), "ก" * 10)

    def test_crud_and_transaction_history(self):
        self.store.add_item(self.sample_item(), operator="admin")
        self.assertEqual(self.store.get_item(1001).quantity, 10)
        self.store.update_item(1001, operator="admin", name="ปากกาน้ำเงิน")
        self.store.receive(1001, 5, operator="admin")
        self.store.issue(1001, 4, operator="admin")
        self.assertEqual(self.store.get_item(1001).quantity, 11)
        self.store.delete_item(1001, operator="admin")
        self.assertEqual(self.store.get_item(1001, include_deleted=True).status, 0)
        self.assertEqual([log.op_code for log in self.store.logs()], [1, 2, 4, 5, 3])

    def test_deleted_slot_is_reused(self):
        self.store.add_item(self.sample_item(), operator="admin")
        before = self.store.items_file.path.stat().st_size
        self.store.delete_item(1001, operator="admin")
        self.store.add_item(self.sample_item(item_id=1002), operator="admin")
        self.assertEqual(self.store.items_file.path.stat().st_size, before)
        self.assertEqual(self.store.get_item(1002).status, 1)

    def test_validation_rejects_duplicate_and_over_issue(self):
        self.store.add_item(self.sample_item(), operator="admin")
        with self.assertRaises(DuplicateError):
            self.store.add_item(self.sample_item(), operator="admin")
        with self.assertRaises(ValidationError):
            self.store.issue(1001, 11, operator="admin")

    def test_category_with_active_items_cannot_be_deleted(self):
        self.store.add_item(self.sample_item(), operator="admin")
        with self.assertRaises(ValidationError):
            self.store.delete_category(1)

    def test_corrupt_file_is_detected(self):
        item_path = self.store.items_file.path
        item_path.write_bytes(b"broken")
        with self.assertRaises(StorageCorruptionError):
            InventoryStorage(self.root / "data")

    def test_report_contains_summary_and_recent_operations(self):
        self.store.add_item(self.sample_item(), operator="admin")
        report = generate_report(self.store, self.root / "inventory_report.txt")
        text = report.read_text(encoding="utf-8")
        self.assertIn("Active Items", text)
        self.assertIn("RECENT OPERATIONS", text)
        self.assertIn("ADD", text)

    def test_unicode_table_rows_have_equal_display_width(self):
        table = render_table(
            ("ID", "ชื่อพัสดุ", "จำนวน"),
            ((1001, "ปากกาลูกลื่น", 120), (1002, "ดินสอ", 80)),
            (6, 20, 8),
            ("right", "left", "right"),
        )
        widths = {display_width(line) for line in table.splitlines()}
        self.assertEqual(len(widths), 1)


if __name__ == "__main__":
    unittest.main()
