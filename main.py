import os
import glob
import PIL.Image
from config import SOURCE_FOLDER, AI_KEY, SETTINGS, DB_CONFIG
from brain import Brain
from keyboard_bot import type_to_erp

def main():
    # Ініціалізуємо Brain з ключем та конфігом БД
    brain = Brain(AI_KEY, db_config=DB_CONFIG)
    
    files = glob.glob(os.path.join(SOURCE_FOLDER, "*.jpg")) + \
            glob.glob(os.path.join(SOURCE_FOLDER, "*.png"))

    if not files:
        print("❌ У папці немає файлів для аналізу!")
        return

    print(f"🤖 Аналізую пакет із {len(files)} сторінок...")
    images = [PIL.Image.open(f) for f in files]

    # Отримуємо дані від ШІ (тут всередині пошук в БД, і навчання)
    data = brain.analyze_invoice(images)
    items = data.get('items', [])

    if not items:
        print("❌ Не вдалося розпізнати товари.")
        return

    # ===   ЛОГІКА ЗВІРКИ  ===
    total_paper = round(float(data.get('grand_total_on_paper', 0)), 2)
    total_calc = round(sum(float(itm.get('row_total_with_vat', 0)) for itm in items), 2)

    print("\n" + "="*50)
    print(f"📊 ПАКЕТНИЙ ЗВІТ ({len(items)} товарів):")
    print(f"   ∟ Розрахована сума: {total_calc}")
    print(f"   ∟ Сума на папері:   {total_paper}")
    print("="*50)

    if abs(total_calc - total_paper) > 0.05:
        print(f"⚠️ УВАГА! Розбіжність: {round(total_calc - total_paper, 2)} грн!")

    # Тільки після звірки сум бот питає про початок введення
    ans = input("\n❓ Почати введення ВСІХ товарів в ERP? (y/n): ").lower()
    if ans == 'y':
        type_to_erp(items) # Вводить Коди ЦБД, знайдені в БД
        print("\n✅ ВСІ СТОРІНКИ ВНЕСЕНО!")

if __name__ == "__main__":
    main()
