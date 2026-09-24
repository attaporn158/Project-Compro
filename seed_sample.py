"""Insert the 10 sample inventory records shown in the assignment screenshot.

The script is deliberately safe: it only seeds an empty data directory and
never overwrites existing records.
"""

from pathlib import Path

from inventory_system import Category, InventoryStorage, Item, generate_report


DATA_DIR = Path("data")
REPORT_PATH = Path("report.txt")
OPERATOR = "SAMPLE_ADMIN"


CATEGORIES = [
    Category(1, "เครื่องเขียน", "ปากกา ดินสอ และอุปกรณ์เครื่องเขียน"),
    Category(2, "อุปกรณ์สำนักงาน", "กระดาษ แฟ้ม และของใช้สำนักงาน"),
    Category(3, "อุปกรณ์อิเล็กทรอนิกส์", "เครื่องคิดเลขและเครื่องพิมพ์"),
    Category(4, "อุปกรณ์คอมพิวเตอร์", "อุปกรณ์ต่อพ่วงคอมพิวเตอร์"),
    Category(5, "เฟอร์นิเจอร์", "โต๊ะ เก้าอี้ และเฟอร์นิเจอร์สำนักงาน"),
]


ITEMS = [
    Item(1001, 1, "ปากกาลูกลื่น", "ด้าม", "A-01-R01", 120, 20, 15.00),
    Item(1002, 1, "ดินสอ", "แท่ง", "A-01-R02", 80, 15, 8.00),
    Item(1003, 2, "กระดาษ A4", "รีม", "A-02-R01", 35, 10, 125.00),
    Item(1004, 2, "แฟ้มเอกสาร", "เล่ม", "A-02-R02", 20, 5, 45.00),
    Item(1005, 3, "เครื่องคิดเลข", "เครื่อง", "B-01-R01", 12, 3, 350.00),
    Item(1006, 3, "เครื่องพิมพ์", "เครื่อง", "B-01-R02", 5, 2, 4500.00),
    Item(1007, 4, "สาย USB", "เส้น", "B-02-R01", 0, 5, 120.00),
    Item(1008, 4, "เมาส์", "ตัว", "B-02-R02", 18, 5, 250.00),
    Item(1009, 5, "เก้าอี้สำนักงาน", "ตัว", "C-01-R01", 6, 2, 1800.00),
    Item(1010, 5, "โต๊ะทำงาน", "ตัว", "C-01-R02", 0, 1, 3500.00),
]


def main() -> int:
    storage = InventoryStorage(DATA_DIR)
    if storage.items(include_deleted=True) or storage.categories(include_deleted=True) or storage.logs():
        print("ยกเลิก: ไฟล์ข้อมูลมีระเบียนอยู่แล้ว สคริปต์จะไม่เขียนทับข้อมูลเดิม")
        return 1

    for category in CATEGORIES:
        storage.add_category(category)

    for item in ITEMS:
        storage.add_item(item, operator=OPERATOR, note="ข้อมูลตัวอย่าง")

    # The screenshot specifies item 1010 as Deleted.  Use the normal CRUD path
    # so that the deletion is also present in the transaction history.
    storage.delete_item(1010, operator=OPERATOR, note="ตัวอย่าง Deleted")

    report = generate_report(storage, REPORT_PATH)
    print(f"เพิ่มข้อมูลตัวอย่าง {len(ITEMS)} รายการแล้ว")
    print(f"สร้างรายงานแล้ว: {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
