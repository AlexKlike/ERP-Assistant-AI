import pyautogui, time, winsound
from config import SETTINGS, ANCHOR_PATH, ERP_COORDS
import logging

def type_to_erp(items):
    print(f"🚀 ЗАПУСК! У вас є {SETTINGS['start_delay']} сек!")
    logging.info(f"СТАРТ ДРУКУ. Агреговано позицій для введення: {len(items)}")
    time.sleep(SETTINGS['start_delay'])
    
    i = 0
    while i < len(items):
        item = items[i]
        db_code = item.get('db_code')
        db_name = item.get('db_name', item.get('name', '...'))

        if not db_code:
            print(f"⚠️ ПРОПУСК (Код не знайдено): {db_name}"); i += 1; continue

        code = str(db_code)
        qty = str(item.get('qty', '1')).replace('.', ',')
        total = str(item.get('row_total_with_vat', '0')).replace('.', ',')

        print(f"✅ Вводжу Код ЦБД: {code} ({db_name[:30]})")
        pyautogui.write(code, interval=SETTINGS['typing_speed'])
        pyautogui.press('enter')
        time.sleep(SETTINGS['search_pause'])
        pyautogui.press('enter')
        
        # ПЕРЕВІРКА ВІКНА (Anchor)
        found = False
        for _ in range(15): 
            try:
                if pyautogui.locateOnScreen(ANCHOR_PATH, confidence=0.7):
                    found = True; break
            except: pass
            time.sleep(0.2)
            
        if not found:
            logging.warning(f"ЯКІР НЕ ЗНАЙДЕНО для коду: {code}")
            winsound.Beep(1000, 800)
            print(f"⚠️ Вікно для {code} не відкрилося!")
            if input("Повторити спробу? (y/n): ").lower() == 'y': continue 
            else: i += 1; continue

        # ВВЕДЕННЯ КІЛЬКОСТІ ТА СУМИ З НАКЛАДНОЇ
        time.sleep(SETTINGS['select_pause'])
        pyautogui.write(qty); time.sleep(0.2)
        x, y = ERP_COORDS["sum_field"]
        pyautogui.click(x, y, clicks=3); time.sleep(0.2)
        pyautogui.press('backspace'); pyautogui.write(total)
        
        time.sleep(1.2); pyautogui.hotkey('ctrl', 'enter'); time.sleep(2.0)
        i += 1
    logging.info("Цикл друку завершено.")


