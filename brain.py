import google.generativeai as genai
import json, fdb, os, re

class Brain:
    def __init__(self, api_key, db_config=None):
        genai.configure(api_key=api_key.strip())
        self.ai_model = genai.GenerativeModel('gemini-flash-latest')
        self.db_config = db_config
        self.kb_path = "knowledge_base.json"
        self.kb = self._load_kb()
        
        dll_path = os.path.join(os.path.dirname(__file__), "fbclient64.dll")
        if os.path.exists(dll_path):
            fdb.load_api(dll_path)

    def _load_kb(self):
        if os.path.exists(self.kb_path):
            try:
                with open(self.kb_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except: return {}
        return {}

    def _save_kb(self, clean_name, code):
        # Зберігаємо нормальну назву (до 100 символів)
        self.kb[clean_name[:100]] = code
        with open(self.kb_path, 'w', encoding='utf-8') as f:
            json.dump(self.kb, f, ensure_ascii=False, indent=4)

    def clean_text(self, text):
        if not text: return ""
        # Залишаємо літери, цифри та ПРОБІЛИ
        clean = re.sub(r'[^a-zA-Zа-яА-ЯёЁіІїЇєЄґҐ0-9\s]', '', str(text))
        return " ".join(clean.split()).upper()

    def analyze_invoice(self, images):
        prompt = """   
        Дій як бухгалтер. Твоє завдання — підготувати дані для ERP. ПДВ 20%.

        1. ПРАВИЛО ЯЩИКІВ (КІЛОГРАМИ):
           - Якщо у назві вказано вагу в КІЛОГРАМАХ (наприклад: '4,7кг', '5кг', '1.44кг'):
           - Ти ПОВИНЕН ігнорувати кількість 1 ящик і записати цю вагу (4.7 або 5) у поле 'qty'.
           - ЦІНУ (price_with_vat) в такому разі ПЕРЕРАХУЙ: Сума рядка / Ця вага.

        2. ПРАВИЛО ПАЧОК (ГРАМИ):
           - Якщо в назві вказано грами (230г, 400г, 290г) і одиниця виміру 'шт':
           - Перевір: Кількість * Ціна = Сума? Якщо збігається — ПИШИ Кількість ЯК Є (наприклад, 4 шт).
           - НІКОЛИ не множ на грами (0.23), якщо математика штук уже збігається.

        3. ЛОГІКА АКЦІЙ ТА УПАКОВОК:
           - Дужки (7+2) -> Qty = 9.
           - Код упаковки (/42шт) -> Множ Кількість на 42, якщо сума не збігається.

        Поверни ТІЛЬКИ JSON:
        {"items": [{"barcode": "str", "name": "str", "qty": number, "price_with_vat": number, "row_total_with_vat": number}], "grand_total_on_paper": number}
        """

        try:
            response = self.ai_model.generate_content([prompt] + images)
            text = response.text.strip().replace('```json', '').replace('```', '')
            data = json.loads(text)
            if self.db_config and data.get('items'):
                data['items'] = self.process_with_learning(data['items'])
            return data
        except Exception as e:
            print(f"Помилка ШІ: {e}"); return {"items": [], "grand_total_on_paper": 0}

    def process_with_learning(self, items):
        # Функція для "голого" порівняння без пробілів
        def total_strip(t): return re.sub(r'[^a-zA-Zа-яА-Я0-9]', '', str(t)).upper()
        
        try:
            conn = fdb.connect(**self.db_config)
            verified_items = []
            clean_kb = {total_strip(k): v for k, v in self.kb.items()}

            for item in items:
                ai_name_raw = item.get('name', '').strip()
                ai_clean = self.clean_text(ai_name_raw)
                ai_stripped = total_strip(ai_name_raw)
                barcode = "".join(filter(str.isdigit, str(item.get('barcode', ''))))
                db_row, cur = None, conn.cursor()

                # ШУКАЄМО: спочатку в оригінальній пам'яті, потім у "голій" без пробілів
                selected_code = self.kb.get(ai_clean) or clean_kb.get(ai_stripped)
                
                if selected_code:
                    cur.execute("SELECT NOMEN_CODE, IS_ACTIVE, NOMEN_NAME FROM NOMEN WHERE NOMEN_CODE = ?", (selected_code,))
                    db_row = cur.fetchone()

                if not db_row and barcode:
                    cur.execute("SELECT NOMEN_CODE, IS_ACTIVE, NOMEN_NAME FROM NOMEN n JOIN NOM_BAR b ON b.NOMEN_ID=n.NOMEN_ID WHERE b.CODE_INT=? ORDER BY n.IS_ACTIVE DESC", (barcode,))
                    db_row = cur.fetchone()

                if db_row:
                    item['db_code'], item['db_status'], item['db_name'] = db_row[0], db_row[1], db_row[2]
                else:
                    item['db_status'] = -1
                verified_items.append(item)
            conn.close(); return verified_items
        except Exception as e:
            print(f"Помилка SQL: {e}"); return items

