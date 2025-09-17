from playwright.sync_api import sync_playwright, TimeoutError
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import os
from openpyxl import Workbook

def initial_shop_name(source_file: str) -> list[str]:
    """อ่านชื่อร้านจากไฟล์ (ละเว้นบรรทัดว่าง)"""
    with open(source_file, "r", encoding="utf-8") as file:
        return [shop_name.strip() for shop_name in file if shop_name.strip()]


def initial_shop_line_url(base_url: str, shop_names: list[str]) -> dict[str, str]:
    """สร้าง mapping {shop_name: shop_url}"""
    return {shop_name: urljoin(base_url, f"@{shop_name}") for shop_name in shop_names}


def save_list_to_file(base_dir: str, shop_name: str, filename: str, data: list[str]):
    """บันทึก list ของ string ลงไฟล์ ถ้า list ว่างจะไม่เขียนไฟล์"""
    if not data:
        return
    os.makedirs(base_dir, exist_ok=True)
    shop_dir = os.path.join(base_dir, f"{shop_name}_fda")
    os.makedirs(shop_dir, exist_ok=True)
    file_path = os.path.join(shop_dir, f"{shop_name}_{filename}.txt")
    with open(file_path, "w", encoding="utf-8") as f:
        f.write("\n".join(data))

def save_list_to_excel(base_dir: str, shop_name: str, filename: str, data: list[str]):
    """บันทึก list ของ string ลงไฟล์ Excel (.xlsx) ถ้า list ว่างจะไม่เขียนไฟล์"""
    if not data:
        return
    os.makedirs(base_dir, exist_ok=True)
    shop_dir = os.path.join(base_dir, f"{shop_name}_fda")
    os.makedirs(shop_dir, exist_ok=True)
    file_path = os.path.join(shop_dir, f"{shop_name}_{filename}.xlsx")

    wb = Workbook()
    ws = wb.active
    ws.title = "Log"

    # ใส่ header
    ws.append(["Product URL / Log"])

    # ใส่ข้อมูลแต่ละบรรทัด
    for item in data:
        ws.append([item])

    wb.save(file_path)

def scroll_to_load_all(page, scroll_pause=1500, max_scroll=50):
    """เลื่อนหน้าจอเพื่อโหลดสินค้าทั้งหมด (lazy load)"""
    last_height = page.evaluate("document.body.scrollHeight")
    for _ in range(max_scroll):
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(scroll_pause)
        new_height = page.evaluate("document.body.scrollHeight")
        if new_height == last_height:
            break
        last_height = new_height


def process_shop(shop_name: str, shop_url: str, base_url: str):
    """เก็บข้อมูล FDA ของสินค้าจากร้านค้า"""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.goto(shop_url, timeout=60000)
        page.wait_for_selector("a")

        # โหลดสินค้าทั้งหมด
        scroll_to_load_all(page)
        page.wait_for_timeout(3000)

        # ดึงลิสต์สินค้า
        markup = page.content()
        soup = BeautifulSoup(markup, "html.parser")
        shop_products = soup.select("ul.grid a")
        list_product_url = [urljoin(base_url, a["href"]) for a in shop_products if a.get("href")]

        print(f"\n🛒 {shop_name} → พบ {len(list_product_url)} สินค้า")

        fda_list = []
        fda_log = []

        for product_url in list_product_url:
            try:
                page.goto(product_url, timeout=60000)
                page.wait_for_selector("div")

                # พยายามกดปุ่ม Product license info
                try:
                    locator = page.get_by_text("Product license info", exact=False)
                    locator.scroll_into_view_if_needed()
                    locator.click(timeout=5000)
                    page.wait_for_timeout(2000)
                except TimeoutError:
                    print(f"⚠️ ไม่มีปุ่ม license info → {product_url}")
                    fda_log.append(product_url)
                    continue

                # ดึงเลข FDA
                fda_numbers = page.locator("div.text-sm.text-gray-500").all_text_contents()
                if fda_numbers:
                    for fda_number in fda_numbers:
                        clean_number = fda_number.strip()
                        print(f"✅ {clean_number} ← {product_url}")
                        fda_list.append(clean_number)
                else:
                    print(f"⚠️ ไม่มีเลข FDA → {product_url}")
                    fda_log.append(product_url)

            except Exception as e:
                print(f"❌ Error {e} → {product_url}")
                fda_log.append(product_url)

        # บันทึกผลลัพธ์
        save_list_to_file("fda_output", shop_name, "fda_list", fda_list)
        save_list_to_file("fda_output", shop_name, "fda_log", fda_log)
        save_list_to_excel("fda_output", shop_name, "fda_log", fda_log)

        print(f"🎉 {shop_name} เสร็จสิ้น! (FDA {len(fda_list)} รายการ, Log {len(fda_log)} รายการ)")
        browser.close()


if __name__ == "__main__":
    base_url = "https://shop.line.me"
    shop_names = initial_shop_name("shop_name.txt")
    shop_urls = initial_shop_line_url(base_url, shop_names)

    for shop_name, shop_url in shop_urls.items():
        process_shop(shop_name, shop_url, base_url)
