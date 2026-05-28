import sys
import json
import urllib.request
import subprocess

try:
    from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                                QHBoxLayout, QLabel, QComboBox, QTextEdit, 
                                QPushButton, QTabWidget, QTreeWidget, QTreeWidgetItem, QMessageBox)
    from PyQt6.QtCore import Qt, QThread, pyqtSignal
except ImportError:
    print("PyQt6 not found. Installing...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "PyQt6"])
    from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                                QHBoxLayout, QLabel, QComboBox, QTextEdit, 
                                QPushButton, QTabWidget, QTreeWidget, QTreeWidgetItem, QMessageBox)
    from PyQt6.QtCore import Qt, QThread, pyqtSignal

BASE_URL = "http://127.0.0.1:3001"

class ProjectFetcher(QThread):
    projects_fetched = pyqtSignal(list)
    
    def run(self):
        try:
            req = urllib.request.Request(f"{BASE_URL}/api/projects_list")
            with urllib.request.urlopen(req, timeout=2) as response:
                if response.status == 200:
                    data = json.loads(response.read().decode())
                    self.projects_fetched.emit(data)
        except Exception as e:
            print(f"Fetch projects error: {e}")

class QueuePoller(QThread):
    queue_fetched = pyqtSignal(dict)
    
    def run(self):
        while True:
            try:
                req = urllib.request.Request(f"{BASE_URL}/api/queue")
                with urllib.request.urlopen(req, timeout=2) as response:
                    if response.status == 200:
                        data = json.loads(response.read().decode())
                        self.queue_fetched.emit(data)
            except Exception:
                pass
            self.msleep(2000)

class PostTaskThread(QThread):
    success = pyqtSignal()
    error = pyqtSignal(str)
    
    def __init__(self, payload):
        super().__init__()
        self.payload = payload
        
    def run(self):
        try:
            req = urllib.request.Request(f"{BASE_URL}/api/queue", data=self.payload, headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(req, timeout=2) as response:
                if response.status == 200:
                    self.success.emit()
                else:
                    self.error.emit(f"HTTP Error {response.status}")
        except Exception as e:
            self.error.emit(str(e))

class ClineXGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Cline-X Control")
        self.resize(500, 450)
        
        # Set flags to remove maximize button and keep on top
        flags = (
            Qt.WindowType.Window |
            Qt.WindowType.WindowTitleHint |
            Qt.WindowType.WindowCloseButtonHint |
            Qt.WindowType.WindowStaysOnTopHint
        )
        self.setWindowFlags(flags)
        
        self.projects = []
        
        self.init_ui()
        self.start_workers()

    def init_ui(self):
        # Modern Dark QSS
        self.setStyleSheet("""
            QMainWindow { background-color: #0A0A0A; }
            QWidget { font-family: 'Segoe UI', Arial, sans-serif; }
            QLabel { color: #E5E5E5; font-weight: bold; font-size: 12px; }
            
            QTabWidget::pane { 
                border: 1px solid #2d2d2d; 
                border-radius: 12px; 
                background: #111111; 
                margin-top: -1px;
            }
            QTabBar::tab { 
                background: #0A0A0A; 
                color: #666; 
                padding: 10px 20px; 
                border: 1px solid transparent;
                border-top-left-radius: 8px; 
                border-top-right-radius: 8px; 
                font-weight: bold;
            }
            QTabBar::tab:selected { 
                background: #111111; 
                color: #3b82f6; 
                border: 1px solid #2d2d2d; 
                border-bottom: 1px solid #111111;
            }
            QTabBar::tab:hover:!selected { color: #aaa; }
            
            QComboBox { 
                background: #1A1A1A; 
                color: #fff; 
                border: 1px solid #333; 
                border-radius: 8px; 
                padding: 8px; 
            }
            QComboBox::drop-down { border: none; }
            QComboBox QAbstractItemView {
                background: #1A1A1A;
                color: #fff;
                selection-background-color: #2d2d2d;
                border: 1px solid #333;
                border-radius: 8px;
            }
            
            QTextEdit { 
                background: #1A1A1A; 
                color: #fff; 
                border: 1px solid #333; 
                border-radius: 8px; 
                padding: 12px; 
                font-size: 13px;
            }
            QTextEdit:focus { border: 1px solid #3b82f6; }
            
            QPushButton { 
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2563eb, stop:1 #7c3aed); 
                color: white; 
                border: none; 
                border-radius: 8px; 
                padding: 12px; 
                font-weight: bold; 
                font-size: 13px;
            }
            QPushButton:hover { 
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #3b82f6, stop:1 #8b5cf6); 
            }
            QPushButton:pressed { background: #1d4ed8; }
            
            QTreeWidget { 
                background: #1A1A1A; 
                color: #eee; 
                border: 1px solid #333; 
                border-radius: 8px; 
                outline: none;
                padding: 5px;
            }
            QTreeWidget::item { padding: 8px; border-bottom: 1px solid #222; }
            QTreeWidget::item:selected { background: #2d2d2d; color: #3b82f6; }
            QHeaderView::section { 
                background: #1A1A1A; 
                color: #888; 
                border: none; 
                border-bottom: 1px solid #333;
                padding: 8px; 
                font-weight: bold;
            }
        """)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(15, 15, 15, 15)

        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)

        # CHAT TAB
        self.chat_tab = QWidget()
        chat_layout = QVBoxLayout(self.chat_tab)
        chat_layout.setContentsMargins(20, 20, 20, 20)
        chat_layout.setSpacing(12)

        proj_label = QLabel("TARGET WORKSPACE")
        self.project_combo = QComboBox()
        
        msg_label = QLabel("TASK INSTRUCTIONS")
        self.message_input = QTextEdit()
        self.message_input.setPlaceholderText("Describe the task for the agent...")
        
        self.send_btn = QPushButton("Add to Queue")
        self.send_btn.clicked.connect(self.add_task)

        chat_layout.addWidget(proj_label)
        chat_layout.addWidget(self.project_combo)
        chat_layout.addWidget(msg_label)
        chat_layout.addWidget(self.message_input)
        chat_layout.addWidget(self.send_btn)

        # QUEUE TAB
        self.queue_tab = QWidget()
        queue_layout = QVBoxLayout(self.queue_tab)
        queue_layout.setContentsMargins(20, 20, 20, 20)
        queue_layout.setSpacing(12)

        self.current_lbl = QLabel("STATUS: IDLE")
        self.current_lbl.setStyleSheet("color: #10b981; font-size: 11px; letter-spacing: 1px;")
        
        self.queue_tree = QTreeWidget()
        self.queue_tree.setColumnCount(2)
        self.queue_tree.setHeaderLabels(["Project", "Message"])
        self.queue_tree.setColumnWidth(0, 150)

        queue_layout.addWidget(self.current_lbl)
        queue_layout.addWidget(self.queue_tree)

        self.tabs.addTab(self.chat_tab, "Chat")
        self.tabs.addTab(self.queue_tab, "Queue")

    def start_workers(self):
        self.proj_fetcher = ProjectFetcher()
        self.proj_fetcher.projects_fetched.connect(self.populate_projects)
        self.proj_fetcher.start()

        self.queue_poller = QueuePoller()
        self.queue_poller.queue_fetched.connect(self.update_queue)
        self.queue_poller.start()

    def populate_projects(self, data):
        self.projects = data
        self.project_combo.clear()
        for p in data:
            self.project_combo.addItem(p['name'])

    def add_task(self):
        idx = self.project_combo.currentIndex()
        if idx < 0:
            QMessageBox.warning(self, "Warning", "Please wait for projects to load.")
            return
            
        proj = self.projects[idx]
        msg = self.message_input.toPlainText().strip()
        
        if not msg:
            QMessageBox.warning(self, "Warning", "Please enter a message.")
            return

        payload = json.dumps({
            "project_path": proj['path'],
            "project_name": proj['name'],
            "message": msg
        }).encode('utf-8')
        
        self.send_btn.setEnabled(False)
        self.send_btn.setText("Sending...")
        
        self.post_thread = PostTaskThread(payload)
        self.post_thread.success.connect(self.on_post_success)
        self.post_thread.error.connect(self.on_post_error)
        self.post_thread.start()

    def on_post_success(self):
        self.send_btn.setEnabled(True)
        self.send_btn.setText("Add to Queue")
        self.message_input.clear()
        self.tabs.setCurrentIndex(1) # Switch to queue tab

    def on_post_error(self, err_msg):
        self.send_btn.setEnabled(True)
        self.send_btn.setText("Add to Queue")
        QMessageBox.critical(self, "Error", f"Failed to add to queue:\n{err_msg}")

    def update_queue(self, data):
        current = data.get('current')
        queue = data.get('queue', [])

        if current:
            self.current_lbl.setText(f"RUNNING: {current['project_name'].upper()}")
            self.current_lbl.setStyleSheet("color: #8b5cf6; font-size: 11px; letter-spacing: 1px;")
        else:
            self.current_lbl.setText("STATUS: IDLE")
            self.current_lbl.setStyleSheet("color: #10b981; font-size: 11px; letter-spacing: 1px;")

        self.queue_tree.clear()
        for q in queue:
            msg_preview = q['message'].replace('\n', ' ')
            if len(msg_preview) > 60:
                msg_preview = msg_preview[:57] + '...'
            
            item = QTreeWidgetItem([q['project_name'], msg_preview])
            self.queue_tree.addTopLevelItem(item)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setStyle("Fusion") # Base style to build QSS on top of
    window = ClineXGUI()
    window.show()
    sys.exit(app.exec())