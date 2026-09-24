"""Terminal user interface for the inventory management system."""

from __future__ import annotations

import argparse
from pathlib import Path

from inventory_system import (
    ACTIVE,
    Category,
    InventoryError,
    InventoryStorage,
    Item,
    format_items,
    generate_report,
)


def ask_text(prompt: str, *, default: str | None = None, allow_empty: bool = False) -> str:
    suffix = f" [{default}]" if default is not None else ""
    while True:
        value = input(f"{prompt}{suffix}: ").strip()
        if value:
            return value
        if default is not None:
            return default
        if allow_empty:
            return ""
        print("ข้อมูลห้ามว่าง กรุณาลองใหม่")


def ask_int(
    prompt: str,
    *,
    minimum: int = 0,
    maximum: int = 2**32 - 1,
    default: int | None = None,
) -> int:
    while True:
        suffix = f" [{default}]" if default is not None else ""
        raw = input(f"{prompt}{suffix}: ").strip()
        if not raw and default is not None:
            return default
        try:
            value = int(raw)
        except ValueError:
            print("กรุณากรอกจำนวนเต็ม")
            continue
        if minimum <= value <= maximum:
            return value
        print(f"ค่าต้องอยู่ระหว่าง {minimum} ถึง {maximum}")


def ask_float(prompt: str, *, minimum: float = 0.0, default: float | None = None) -> float:
    while True:
        suffix = f" [{default}]" if default is not None else ""
        raw = input(f"{prompt}{suffix}: ").strip()
        if not raw and default is not None:
            return default
        try:
            value = float(raw)
        except ValueError:
            print("กรุณากรอกตัวเลข")
            continue
        if minimum <= value < float("inf"):
            return value
        print(f"ค่าต้องไม่น้อยกว่า {minimum} และต้องเป็นค่าจำกัด")


def confirm(prompt: str) -> bool:
    while True:
        answer = input(f"{prompt} (y/n): ").strip().lower()
        if answer in {"y", "yes"}:
            return True
        if answer in {"n", "no"}:
            return False
        print("กรุณาตอบ y หรือ n")


class InventoryApp:
    def __init__(self, storage: InventoryStorage, report_path: Path) -> None:
        self.storage = storage
        self.report_path = report_path
        self.operator = ""

    def run(self) -> None:
        print("\nระบบจัดการคลังพัสดุแบบไฟล์ไบนารี")
        self.operator = ask_text("ชื่อผู้ปฏิบัติงาน")
        while True:
            print(
                "\n" + "=" * 54 + "\n"
                "1. Add      - เพิ่มพัสดุ\n"
                "2. Update   - แก้ไขพัสดุ\n"
                "3. Delete   - ลบพัสดุ\n"
                "4. View     - ดูและค้นหาข้อมูล\n"
                "5. Generate Report (.txt)\n"
                "6. Categories - จัดการหมวดหมู่\n"
                "7. Receive  - รับพัสดุเข้า\n"
                "8. Issue    - เบิกพัสดุออก\n"
                "0. Exit\n" + "=" * 54
            )
            choice = ask_int("เลือกเมนู", minimum=0, maximum=8)
            try:
                if choice == 0:
                    self._safe_report()
                    print("บันทึกข้อมูลและปิดโปรแกรมเรียบร้อย")
                    return
                actions = {
                    1: self.add_item,
                    2: self.update_item,
                    3: self.delete_item,
                    4: self.view_menu,
                    5: self.create_report,
                    6: self.category_menu,
                    7: self.receive_item,
                    8: self.issue_item,
                }
                actions[choice]()
            except InventoryError as exc:
                print(f"ผิดพลาด: {exc}")

    def _safe_report(self) -> None:
        try:
            generate_report(self.storage, self.report_path)
            print(f"สร้างรายงานอัตโนมัติ: {self.report_path}")
        except OSError as exc:
            print(f"คำเตือน: สร้างรายงานอัตโนมัติไม่สำเร็จ: {exc}")

    def add_item(self) -> None:
        if not self.storage.categories():
            print("ยังไม่มีหมวดหมู่ กรุณาเพิ่มหมวดหมู่ในเมนู 6 ก่อน")
            return
        self.show_categories()
        item = Item(
            item_id=ask_int("รหัสพัสดุ", minimum=1),
            category_id=ask_int("รหัสหมวดหมู่", minimum=1),
            name=ask_text("ชื่อพัสดุ"),
            unit=ask_text("หน่วยนับ"),
            location=ask_text("ตำแหน่งจัดเก็บ"),
            quantity=ask_int("จำนวนตั้งต้น", minimum=0),
            reorder_level=ask_int("จุดสั่งซื้อขั้นต่ำ", minimum=0),
            unit_price=ask_float("ราคาต่อหน่วย", minimum=0),
        )
        note = ask_text("หมายเหตุ", default="เพิ่มพัสดุ")
        self.storage.add_item(item, operator=self.operator, note=note)
        print("เพิ่มพัสดุเรียบร้อย")

    def update_item(self) -> None:
        item_id = ask_int("รหัสพัสดุที่ต้องการแก้ไข", minimum=1)
        item = self.storage.get_item(item_id)
        print(format_items([item]))
        self.show_categories()
        updated = self.storage.update_item(
            item_id,
            operator=self.operator,
            note=ask_text("หมายเหตุ", default="แก้ไขข้อมูล"),
            category_id=ask_int("รหัสหมวดหมู่", minimum=1, default=item.category_id),
            name=ask_text("ชื่อพัสดุ", default=item.name),
            unit=ask_text("หน่วยนับ", default=item.unit),
            location=ask_text("ตำแหน่งจัดเก็บ", default=item.location),
            quantity=ask_int("จำนวนคงเหลือ", minimum=0, default=item.quantity),
            reorder_level=ask_int("จุดสั่งซื้อขั้นต่ำ", minimum=0, default=item.reorder_level),
            unit_price=ask_float("ราคาต่อหน่วย", minimum=0, default=item.unit_price),
        )
        print("แก้ไขเรียบร้อย\n" + format_items([updated]))

    def delete_item(self) -> None:
        item_id = ask_int("รหัสพัสดุที่ต้องการลบ", minimum=1)
        item = self.storage.get_item(item_id)
        print(format_items([item]))
        if confirm("ยืนยันการลบแบบ Logical Delete"):
            note = ask_text("หมายเหตุ", default="ลบพัสดุ")
            self.storage.delete_item(item_id, operator=self.operator, note=note)
            print("ลบพัสดุเรียบร้อย ช่องระเบียนนี้สามารถนำกลับมาใช้ได้")
        else:
            print("ยกเลิกการลบ")

    def view_menu(self) -> None:
        print(
            "\n1. ดูรายการเดียว\n2. ดู Active ทั้งหมด\n3. ดูทั้งหมดรวม Deleted\n"
            "4. กรองตามหมวดหมู่\n5. ดูพัสดุใกล้หมด\n6. สถิติโดยสรุป\n"
            "7. ประวัติการทำงานล่าสุด\n0. กลับ"
        )
        choice = ask_int("เลือกเมนูย่อย", minimum=0, maximum=7)
        if choice == 0:
            return
        if choice == 1:
            item_id = ask_int("รหัสพัสดุ", minimum=1)
            print(format_items([self.storage.get_item(item_id, include_deleted=True)]))
        elif choice == 2:
            print(format_items(self.storage.items()))
        elif choice == 3:
            print(format_items(self.storage.items(include_deleted=True)))
        elif choice == 4:
            category_id = ask_int("รหัสหมวดหมู่", minimum=1)
            print(format_items(self.storage.filtered_items(category_id=category_id)))
        elif choice == 5:
            print(format_items(self.storage.filtered_items(low_stock_only=True)))
        elif choice == 6:
            stats = self.storage.statistics()
            for key, value in stats.items():
                print(f"{key:<18}: {value:,.2f}" if isinstance(value, float) else f"{key:<18}: {value}")
        elif choice == 7:
            logs = self.storage.logs(limit=10)
            if not logs:
                print("ยังไม่มีประวัติ")
            for log in reversed(logs):
                print(
                    f"#{log.log_seq} op={log.op_code} item={log.item_id} qty={log.quantity} "
                    f"balance={log.balance:.0f} by={log.operator} note={log.note}"
                )

    def create_report(self) -> None:
        path = generate_report(self.storage, self.report_path)
        print(f"สร้างรายงานเรียบร้อย: {path}")

    def show_categories(self, *, include_deleted: bool = False) -> None:
        categories = self.storage.categories(include_deleted=include_deleted)
        if not categories:
            print("ไม่พบข้อมูลหมวดหมู่")
            return
        print(f"{'ID':>8} | {'Name':<24} | {'Description':<40} | Status")
        print("-" * 92)
        for category in categories:
            print(
                f"{category.category_id:>8} | {category.name[:24]:<24} | "
                f"{category.description[:40]:<40} | "
                f"{'Active' if category.status == ACTIVE else 'Deleted'}"
            )

    def category_menu(self) -> None:
        print("\n1. เพิ่มหมวดหมู่\n2. แก้ไขหมวดหมู่\n3. ลบหมวดหมู่\n4. ดูหมวดหมู่\n0. กลับ")
        choice = ask_int("เลือกเมนูหมวดหมู่", minimum=0, maximum=4)
        if choice == 0:
            return
        if choice == 1:
            category = Category(
                ask_int("รหัสหมวดหมู่", minimum=1),
                ask_text("ชื่อหมวดหมู่"),
                ask_text("รายละเอียด", allow_empty=True),
            )
            self.storage.add_category(category)
            print("เพิ่มหมวดหมู่เรียบร้อย")
        elif choice == 2:
            category_id = ask_int("รหัสหมวดหมู่ที่ต้องการแก้ไข", minimum=1)
            category = self.storage.get_category(category_id)
            self.storage.update_category(
                category_id,
                name=ask_text("ชื่อหมวดหมู่", default=category.name),
                description=ask_text("รายละเอียด", default=category.description, allow_empty=True),
            )
            print("แก้ไขหมวดหมู่เรียบร้อย")
        elif choice == 3:
            category_id = ask_int("รหัสหมวดหมู่ที่ต้องการลบ", minimum=1)
            category = self.storage.get_category(category_id)
            print(f"{category.category_id}: {category.name}")
            if confirm("ยืนยันการลบหมวดหมู่"):
                self.storage.delete_category(category_id)
                print("ลบหมวดหมู่เรียบร้อย")
        elif choice == 4:
            self.show_categories(include_deleted=True)

    def receive_item(self) -> None:
        item_id = ask_int("รหัสพัสดุ", minimum=1)
        quantity = ask_int("จำนวนรับเข้า", minimum=1)
        note = ask_text("หมายเหตุ", default="รับเข้า")
        item = self.storage.receive(item_id, quantity, operator=self.operator, note=note)
        print(f"รับเข้าเรียบร้อย คงเหลือ {item.quantity} {item.unit}")

    def issue_item(self) -> None:
        item_id = ask_int("รหัสพัสดุ", minimum=1)
        quantity = ask_int("จำนวนเบิก", minimum=1)
        note = ask_text("หมายเหตุ", default="เบิกจ่าย")
        item = self.storage.issue(item_id, quantity, operator=self.operator, note=note)
        print(f"เบิกเรียบร้อย คงเหลือ {item.quantity} {item.unit}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ระบบคลังพัสดุแบบ fixed-length binary records")
    parser.add_argument("--data-dir", type=Path, default=Path("data"), help="โฟลเดอร์ไฟล์ .dat")
    parser.add_argument(
        "--report", type=Path, default=Path("inventory_report.txt"), help="ตำแหน่งไฟล์รายงาน"
    )
    parser.add_argument(
        "--init-only", action="store_true", help="สร้างไฟล์ข้อมูลและรายงานเริ่มต้นแล้วจบการทำงาน"
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        storage = InventoryStorage(args.data_dir)
        if args.init_only:
            report = generate_report(storage, args.report)
            print(f"เตรียมไฟล์ข้อมูลและรายงานแล้ว: {report}")
            return 0
        app = InventoryApp(storage, args.report)
        try:
            app.run()
        except (EOFError, KeyboardInterrupt):
            print("\nได้รับคำสั่งหยุด กำลังบันทึกและสร้างรายงาน...")
            app._safe_report()
        return 0
    except (InventoryError, OSError) as exc:
        print(f"ไม่สามารถเริ่มระบบได้: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
