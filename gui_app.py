import sys, os, glob, time, json, importlib.util, shutil
import telebot
from datetime import datetime
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QTableWidget, QTableWidgetItem, 
                             QLabel, QHeaderView, QMessageBox, QListWidget, QSplitter)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont
from PIL import Image

# 1. ЗАВАНТАЖЕННЯ КОНФІГУ
def load_cfg():
    path = os.path.join(os.getcwd(), "config.py")
    if os.path.exists(path):
        spec = importlib.util.spec_from_file_location("config", path)
        cfg = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cfg)
        return cfg
    sys.exit("❌ config.py не знайдено поруч з EXE!")

c = load_cfg()
from brain import Brain
from keyboard_bot import type_to_erp

# 2. ПОТІК TELEGRAM
class TelegramWorker(QThread):
    new_photo_signal = pyqtSignal()
    def run(self):
        try:
            bot = telebot.TeleBot(c.TELEGRAM_TOKEN)
            groups = {}
            @bot.message_handler(content_types=['photo'])
            def handle_photo(message):
                if str(message.chat.id) != str(c.ADMIN_CHAT_ID): return
                gid = message.media_group_id
                folder_name = groups.get(gid) if gid else datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                if gid and gid not in groups: groups[gid] = folder_name
                path = os.path.join(c.SOURCE_FOLDER, folder_name)
                if not os.path.exists(path): os.makedirs(path)
                f_info = bot.get_file(message.photo[-1].file_id)
                down_f = bot.download_file(f_info.file_path)
                with open(os.path.join(path, f"img_{int(time.time()*1000)}.jpg"), 'wb') as f: f.write(down_f)
                self.new_photo_signal.emit()
            bot.polling(none_stop=True)
        except: pass

# 3. ПОТІК АНАЛІЗУ
class AnalysisWorker(QThread):
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)
    def __init__(self, brain, images):
        super().__init__()
        self.brain, self.images = brain, images
    def run(self):
        try:
            data = self.brain.analyze_invoice(self.images)
            self.finished.emit(data)
        except Exception as e: self.error.emit(str(e))

# 4. ПОТІК ДРУКУ
class TypingWorker(QThread):
    done = pyqtSignal()
    def __init__(self, items):
        super().__init__()
        self.items = items
    def run(self):
        time.sleep(7) # Затримка 7 секунд
        type_to_erp(self.items)
        self.done.emit()

class InvoiceApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.brain = Brain(c.AI_KEY, db_config=c.DB_CONFIG)
        self.current_folder = None
        self.analyzing_folder_name = None # Для значка ⌛
        self.initUI()
        self.refresh_folders()
        self.tg_thread = TelegramWorker()
        self.tg_thread.new_photo_signal.connect(self.refresh_folders)
        self.tg_thread.start()

    def initUI(self):
        self.setWindowTitle('ERP Assistant v1.9.4 — Диспетчер Конвеєра')
        self.setGeometry(100, 100, 1300, 800)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        left = QWidget(); l_lay = QVBoxLayout(left)
        l_lay.addWidget(QLabel("📂 ЧЕРГА (Telegram):"))
        self.folder_list = QListWidget()
        self.folder_list.itemClicked.connect(self.select_folder)
        l_lay.addWidget(self.folder_list)
        right = QWidget(); r_lay = QVBoxLayout(right)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(['Код ЦБД', 'Штрихкод', 'Назва', 'К-сть', 'Сума', 'Статус'])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        r_lay.addWidget(self.table)
        self.stats_label = QLabel("Оберіть накладну...")
        r_lay.addWidget(self.stats_label)
        btns = QHBoxLayout()
        self.btn_analyze = QPushButton("🔍 1. АНАЛІЗУВАТИ")
        self.btn_analyze.clicked.connect(self.run_analysis)
        self.btn_type = QPushButton("🚀 2. ВВЕСТИ В ERP")
        self.btn_type.clicked.connect(self.run_typing)
        btns.addWidget(self.btn_analyze); btns.addWidget(self.btn_type)
        r_lay.addLayout(btns)
        splitter.addWidget(left); splitter.addWidget(right); splitter.setStretchFactor(1, 4)
        self.setCentralWidget(splitter)

    def refresh_folders(self):
        # Отримуємо чисту назву поточної папки без іконок
        selected = self.folder_list.currentItem().text()[2:] if self.folder_list.currentItem() else None
        self.folder_list.clear()
        if not os.path.exists(c.SOURCE_FOLDER): os.makedirs(c.SOURCE_FOLDER)
        folders = [d for d in os.listdir(c.SOURCE_FOLDER) if os.path.isdir(os.path.join(c.SOURCE_FOLDER, d)) and d != "archive"]
        for f in sorted(folders, reverse=True):
            # Визначаємо іконку
            if f == self.analyzing_folder_name:
                status = "⌛ " # В процесі
            elif os.path.exists(os.path.join(c.SOURCE_FOLDER, f, "result.json")):
                status = "✅ " # Готово
            else:
                status = "📥 " # Нова
            self.folder_list.addItem(status + f)
            if selected and f == selected: self.folder_list.setCurrentRow(self.folder_list.count()-1)

    def select_folder(self, item):
        clean_name = item.text()[2:]
        self.current_folder = os.path.join(c.SOURCE_FOLDER, clean_name)
        cache_path = os.path.join(self.current_folder, "result.json")
        self.table.setRowCount(0)
        if os.path.exists(cache_path):
            with open(cache_path, 'r', encoding='utf-8') as f: self.display_results(json.load(f))
        else: self.stats_label.setText(f"Очікує аналізу: {clean_name}")

    def run_analysis(self):
        if not self.current_folder: return
        self.analyzing_folder_name = os.path.basename(self.current_folder)
        self.refresh_folders() # Міняємо іконку на ⌛
        
        files = glob.glob(os.path.join(self.current_folder, "*.jpg")) + glob.glob(os.path.join(self.current_folder, "*.png"))
        self.btn_analyze.setText("⌛ АНАЛІЗУЮ..."); self.btn_analyze.setEnabled(False)
        images = []
        for f in files:
            with Image.open(f) as img: images.append(img.copy())
        self.worker = AnalysisWorker(self.brain, images)
        self.worker.finished.connect(self.on_finished)
        self.worker.error.connect(lambda e: QMessageBox.critical(self, "Помилка", e))
        self.worker.start()

    def on_finished(self, data):
        with open(os.path.join(self.current_folder, "result.json"), 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        self.analyzing_folder_name = None # Скидаємо статус аналізу
        self.display_results(data)
        self.btn_analyze.setText("🔍 1. АНАЛІЗУВАТИ"); self.btn_analyze.setEnabled(True)
        self.refresh_folders() # Міняємо іконку на ✅

    def display_results(self, data):
        items = data.get('items', [])
        self.table.setRowCount(len(items))
        for r, itm in enumerate(items):
            self.table.setItem(r, 0, QTableWidgetItem(str(itm.get('db_code', ''))))
            self.table.setItem(r, 1, QTableWidgetItem(str(itm.get('barcode', ''))))
            self.table.setItem(r, 2, QTableWidgetItem(str(itm.get('name', ''))))
            self.table.setItem(r, 3, QTableWidgetItem(str(itm.get('qty', '0'))))
            self.table.setItem(r, 4, QTableWidgetItem(str(itm.get('row_total_with_vat', '0'))))
            st = itm.get('db_status')
            self.table.setItem(r, 5, QTableWidgetItem("✅" if st==1 else "🚫" if st==0 else "❓"))
        
        calc = sum(float(str(i.get('row_total_with_vat',0)).replace(',','.')) for i in items)
        paper = float(str(data.get('grand_total_on_paper',0)).replace(',','.'))
        self.stats_label.setText(f"РАЗОМ: {calc:.2f} | ПАПІР: {paper:.2f} | РІЗНИЦЯ: {round(calc-paper, 2)}")

    def run_typing(self):
        aggregated = {}
        for r in range(self.table.rowCount()):
            code = self.table.item(r, 0).text().strip()
            if not code or code == "None": continue
            # Навчання (KB)
            self.brain._save_kb(self.brain.clean_text(self.table.item(r, 2).text()), code)
            qty = float(self.table.item(r, 3).text().replace(',','.'))
            total = float(self.table.item(r, 4).text().replace(',','.'))
            if code in aggregated:
                aggregated[code]['qty'] += qty
                aggregated[code]['row_total_with_vat'] += total
            else: aggregated[code] = {'db_code': code, 'qty': qty, 'row_total_with_vat': total, 'db_name': self.table.item(r, 2).text()}
        
        self.btn_type.setText("⌨️ ДРУКУЮ..."); self.btn_type.setEnabled(False)
        self.typer = TypingWorker(list(aggregated.values()))
        self.typer.done.connect(self.on_typing_done); self.typer.start()

    def on_typing_done(self):
        self.btn_type.setText("🚀 2. ВВЕСТИ В ERP"); self.btn_type.setEnabled(True)
        arch_dir = os.path.join(c.SOURCE_FOLDER, "archive")
        if not os.path.exists(arch_dir): os.makedirs(arch_dir)
        try:
            shutil.move(self.current_folder, os.path.join(arch_dir, os.path.basename(self.current_folder)))
            self.refresh_folders(); QMessageBox.information(self, "Успіх", "Введено та архівовано!")
        except: pass

if __name__ == '__main__':
    app = QApplication(sys.argv); ex = InvoiceApp(); ex.show(); sys.exit(app.exec())
