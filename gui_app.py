import sys, os, glob, time, json, importlib.util, shutil, telebot
from datetime import datetime
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QTableWidget, QTableWidgetItem, 
                             QLabel, QHeaderView, QMessageBox, QListWidget, QSplitter, 
                             QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, QDialog)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSize
from PyQt6.QtGui import QFont, QPixmap, QWheelEvent, QKeyEvent, QAction
from PIL import Image

# 1. ЗАВАНТАЖЕННЯ КОНФІГУ
def load_cfg():
    path = os.path.join(os.getcwd(), "config.py")
    if os.path.exists(path):
        spec = importlib.util.spec_from_file_location("config", path)
        cfg = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cfg)
        return cfg
    sys.exit("❌ config.py не знайдено!")

c = load_cfg()
from brain import Brain
from keyboard_bot import type_to_erp

# --- ВІДЖЕТ ЗУМУ ---
class ZoomView(QGraphicsView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        self.pixmap_item = QGraphicsPixmapItem()
        self.scene.addItem(self.pixmap_item)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)

    def set_image(self, pixmap):
        self.pixmap_item.setPixmap(pixmap)
        self.setSceneRect(self.pixmap_item.boundingRect())
        self.fitInView(self.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def wheelEvent(self, event: QWheelEvent):
        factor = 1.25 if event.angleDelta().y() > 0 else 0.8
        self.scale(factor, factor)

# --- ПОВНОЕКРАННЕ ВІКНО ---
class FullScreenPopup(QDialog):
    def __init__(self, pixmap, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        self.showMaximized()
        self.setStyleSheet("background-color: black;")
        layout = QVBoxLayout(self)
        self.view = ZoomView()
        self.view.set_image(pixmap)
        layout.addWidget(self.view)
        btn = QPushButton("❌ ЗАКРИТИ (ESC)")
        btn.setFixedWidth(200)
        btn.setStyleSheet("background: #e74c3c; color: white; padding: 10px; font-weight: bold;")
        btn.clicked.connect(self.close)
        layout.addWidget(btn, alignment=Qt.AlignmentFlag.AlignCenter)

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Escape: self.close()

# --- ПОТОКИ ---
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
                fn = groups.get(gid) if gid else datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                if gid and gid not in groups: groups[gid] = fn
                path = os.path.join(c.SOURCE_FOLDER, fn)
                if not os.path.exists(path): os.makedirs(path)
                f_info = bot.get_file(message.photo[-1].file_id)
                down_f = bot.download_file(f_info.file_path)
                with open(os.path.join(path, f"img_{int(time.time()*1000)}.jpg"), 'wb') as f: f.write(down_f)
                self.new_photo_signal.emit()
            bot.polling(none_stop=True)
        except: pass

class AnalysisWorker(QThread):
    finished = pyqtSignal(dict)
    def __init__(self, brain, images):
        super().__init__()
        self.brain, self.images = brain, images
    def run(self):
        data = self.brain.analyze_invoice(self.images)
        self.finished.emit(data)

class TypingWorker(QThread):
    done = pyqtSignal()
    def __init__(self, items):
        super().__init__()
        self.items = items
    def run(self):
        time.sleep(7)
        type_to_erp(self.items)
        self.done.emit()

# --- ГОЛОВНЕ ВІКНО ---
class InvoiceApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.brain = Brain(c.AI_KEY, db_config=c.DB_CONFIG)
        self.current_folder = None
        self.analyzing_folder_name = None
        self.initUI()
        self.refresh_folders()
        self.tg_thread = TelegramWorker()
        self.tg_thread.new_photo_signal.connect(self.refresh_folders)
        self.tg_thread.start()

    def initUI(self):
        self.setWindowTitle('ERP Assistant v2.0 — Око Орла')
        self.setGeometry(50, 50, 1500, 900)
        
        main_splitter = QSplitter(Qt.Orientation.Horizontal)

        # ЛІВА ПАНЕЛЬ
        left = QWidget(); l_lay = QVBoxLayout(left)
        l_lay.addWidget(QLabel("📂 ЧЕРГА:"))
        self.folder_list = QListWidget()
        self.folder_list.itemClicked.connect(self.select_folder)
        l_lay.addWidget(self.folder_list)
        main_splitter.addWidget(left)

        # ЦЕНТРАЛЬНА ПАНЕЛЬ
        center = QWidget(); c_lay = QVBoxLayout(center)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(['Код ЦБД', 'Штрихкод', 'Назва', 'К-сть', 'Сума', 'Статус'])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        c_lay.addWidget(self.table)
        self.stats_label = QLabel("Оберіть накладну...")
        c_lay.addWidget(self.stats_label)
        btns = QHBoxLayout()
        self.btn_analyze = QPushButton("🔍 1. АНАЛІЗУВАТИ")
        self.btn_analyze.clicked.connect(self.run_analysis)
        self.btn_type = QPushButton("🚀 2. ДРУКУЮ")
        self.btn_type.clicked.connect(self.run_typing)
        btns.addWidget(self.btn_analyze); btns.addWidget(self.btn_type)
        c_lay.addLayout(btns)
        main_splitter.addWidget(center)

        # ПРАВА ПАНЕЛЬ (Фото)
        right = QWidget(); r_lay = QVBoxLayout(right)
        r_lay.addWidget(QLabel("📸 ПЕРЕГЛЯД (Mouse Wheel = Zoom):"))
        self.zoom_viewer = ZoomView()
        r_lay.addWidget(self.zoom_viewer)
        self.btn_fullscreen = QPushButton("🖥️ На весь екран")
        self.btn_fullscreen.clicked.connect(self.open_fullscreen)
        r_lay.addWidget(self.btn_fullscreen)
        main_splitter.addWidget(right)

        main_splitter.setStretchFactor(0, 1)
        main_splitter.setStretchFactor(1, 3)
        main_splitter.setStretchFactor(2, 2)
        self.setCentralWidget(main_splitter)

    def refresh_folders(self):
        selected = self.folder_list.currentItem().text()[2:] if self.folder_list.currentItem() else None
        self.folder_list.clear()
        if not os.path.exists(c.SOURCE_FOLDER): os.makedirs(c.SOURCE_FOLDER)
        folders = [d for d in os.listdir(c.SOURCE_FOLDER) if os.path.isdir(os.path.join(c.SOURCE_FOLDER, d)) and d != "archive"]
        for f in sorted(folders, reverse=True):
            status = "⌛ " if f == self.analyzing_folder_name else "✅ " if os.path.exists(os.path.join(c.SOURCE_FOLDER, f, "result.json")) else "📥 "
            self.folder_list.addItem(status + f)
            if selected and f == selected: self.folder_list.setCurrentRow(self.folder_list.count()-1)

    def select_folder(self, item):
        clean_name = item.text()[2:]
        self.current_folder = os.path.join(c.SOURCE_FOLDER, clean_name)
        
        # Завантаження фото в перегляд
        photos = glob.glob(os.path.join(self.current_folder, "*.jpg"))
        if photos: self.zoom_viewer.set_image(QPixmap(photos[0]))

        cache_path = os.path.join(self.current_folder, "result.json")
        self.table.setRowCount(0)
        if os.path.exists(cache_path):
            with open(cache_path, 'r', encoding='utf-8') as f: self.display_results(json.load(f))
        else: self.stats_label.setText(f"Очікує аналізу: {clean_name}")

    def open_fullscreen(self):
        if self.zoom_viewer.pixmap_item.pixmap():
            popup = FullScreenPopup(self.zoom_viewer.pixmap_item.pixmap(), self)
            popup.exec()

    def run_analysis(self):
        if not self.current_folder: return
        self.analyzing_folder_name = os.path.basename(self.current_folder)
        self.refresh_folders()
        files = glob.glob(os.path.join(self.current_folder, "*.jpg"))
        self.btn_analyze.setText("⌛ АНАЛІЗУЮ..."); self.btn_analyze.setEnabled(False)
        images = []
        for f in files:
            with Image.open(f) as img: images.append(img.copy())
        self.worker = AnalysisWorker(self.brain, images)
        self.worker.finished.connect(self.on_finished); self.worker.start()

    def on_finished(self, data):
        with open(os.path.join(self.current_folder, "result.json"), 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        self.analyzing_folder_name = None
        self.display_results(data)
        self.btn_analyze.setText("🔍 1. АНАЛІЗУВАТИ"); self.btn_analyze.setEnabled(True)
        self.refresh_folders()

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
            self.brain._save_kb(self.brain.clean_text(self.table.item(r, 2).text()), code)
            qty = float(self.table.item(r, 3).text().replace(',','.'))
            total = float(self.table.item(r, 4).text().replace(',','.'))
            if code in aggregated:
                aggregated[code]['qty'] += qty; aggregated[code]['row_total_with_vat'] += total
            else: aggregated[code] = {'db_code': code, 'qty': qty, 'row_total_with_vat': total, 'db_name': self.table.item(r, 2).text()}
        
        self.btn_type.setText("⌨️ ДРУКУЮ..."); self.btn_type.setEnabled(False)
        self.typer = TypingWorker(list(aggregated.values()))
        self.typer.done.connect(self.on_typing_done); self.typer.start()

    def on_typing_done(self):
        self.btn_type.setText("🚀 2. ДРУКУЮ"); self.btn_type.setEnabled(True)
        arch_dir = os.path.join(c.SOURCE_FOLDER, "archive")
        if not os.path.exists(arch_dir): os.makedirs(arch_dir)
        try:
            shutil.move(self.current_folder, os.path.join(arch_dir, os.path.basename(self.current_folder)))
            self.refresh_folders(); QMessageBox.information(self, "Успіх", "Введено!")
        except: pass

if __name__ == '__main__':
    app = QApplication(sys.argv); ex = InvoiceApp(); ex.show(); sys.exit(app.exec())


