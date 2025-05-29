import sys
import subprocess
import importlib.util
import os
import re
from pathlib import Path
from typing import List, Optional
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox, QFileDialog, QProgressBar, QTableWidget, QTableWidgetItem, QMessageBox, QHeaderView, QGroupBox, QSizePolicy, QFrame, QSpacerItem
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QIcon, QFont
import mysql.connector
from dotenv import load_dotenv

# --- Always ensure requirements are installed ---
REQUIRED = [
    ('PySide6', 'PySide6'),
    ('mysql', 'mysql-connector-python'),
    ('dotenv', 'python-dotenv'),
]
for module, package in REQUIRED:
    if importlib.util.find_spec(module) is None:
        print(f"[Auto-Installer] Installing missing package: {package}")
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', package])

# --- Frameworks and Patterns ---
FRAMEWORKS = {
    'qbcore': ['qbcore', 'qb'],
    'qbx': ['qbx'],
    'ox': ['ox', 'oxcore'],
    'esx': ['esx'],
    'other': []  # fallback: run all .sql files
}

# --- Advanced detection patterns for each framework ---
FRAMEWORK_PATTERNS = {
    'esx': [
        r'\besx_', r'\busers\b', r'\bowned_vehicles\b', r'\baddon_account_data\b', r'\bdatastore_data\b', r'\bjobs\b', r'\bjob_grades\b',
        r'INSERT INTO `users`', r'INSERT INTO `owned_vehicles`', r'INSERT INTO `addon_account_data`', r'INSERT INTO `datastore_data`',
        r'CREATE TABLE IF NOT EXISTS `users`', r'CREATE TABLE IF NOT EXISTS `owned_vehicles`',
        r'-- ESX', r'\besx_[a-z0-9_]+',
        r'INSERT IGNORE [`\"]?items[`\"]?', r'CREATE TABLE IF NOT EXISTS [`\"]?items[`\"]?', r'ALTER TABLE [`\"]?items[`\"]?',
        r'--.*esx', r'--.*item limit', r'--.*item weight', r'--.*es_extended',
        r'\bdatastore_data\b', r'\baddon_inventory_items\b', r'\baddon_account_data\b',
        r'\bowned_properties\b', r'\buser_licenses\b', r'\buser_vehicles\b',
        r'\buser_inventory\b', r'\buser_accounts\b', r'\buser_.*',
        r'\bproperty\b', r'\bphone_users_contacts\b',
    ],
    'qbcore': [
        r'\bqbcore_', r'\bqb_', r'\bplayers\b', r'\bplayer_vehicles\b', r'INSERT INTO `players`', r'INSERT INTO `player_vehicles`',
        r'CREATE TABLE IF NOT EXISTS `players`', r'CREATE TABLE IF NOT EXISTS `player_vehicles`',
        r'JSON_', r'qbcore framework', r'-- QBCore',
        r'\bmetadata\b', r'\binventory\b', r'\bplayer_outfits\b',
        r'\bplayer_houses\b', r'\bplayer_motels\b', r'\bplayer_gangs\b',
        r'\bplayer_contacts\b', r'\bplayer_.*',
        r'\btrunkitems\b', r'\bgloveboxitems\b',
    ],
    'ox': [
        r'\box_', r'\boxcore_', r'\box_inventory\b', r'\box_doorlock\b', r'INSERT INTO `ox_inventory`', r'INSERT INTO `ox_doorlock`',
        r'CREATE TABLE IF NOT EXISTS `ox_inventory`', r'CREATE TABLE IF NOT EXISTS `ox_doorlock`',
        r'-- OX', r'\box_[a-z0-9_]+',
        r'\bowned_keys\b', r'\bowned_doors\b',
        r'\bdoorlock\b', r'\binventory\b',
    ],
    'qbx': [
        r'\bqbx_', r'\bqbx\b', r'-- QBX', r'QBX',
        r'ox_inventory', r'ox_doorlock', r'qbcore', r'qb_',
    ],
}

BLACKLISTED_FILES = [
    os.path.normpath('ox_doorlock/sql/default.sql'),
    os.path.normpath('ox_doorlock/sql/community_mrpd.sql'),
]
WHITELISTED_FILES = [
    os.path.normpath('ox_doorlock/sql/ox_doorlock.sql'),
]

# --- DB Connection Extraction ---
def extract_mysql_url_from_cfg(cfg_path: Path) -> Optional[str]:
    with cfg_path.open(encoding='utf-8', errors='ignore') as f:
        for line in f:
            match = re.search(r'set\s+mysql_connection_string\s+(["\'])(.+?)\1', line)
            if match:
                url = match.group(2).strip()
                return url
            match2 = re.search(r'set\s+mysql_connection_string\s+([^\s#]+)', line)
            if match2:
                url = match2.group(1).strip()
                return url
    return None

def parse_mysql_url(url: str):
    from urllib.parse import urlparse, parse_qs
    print(f"[DEBUG] Parsing DB URL: {url}")
    parsed = urlparse(url)
    print(f"[DEBUG] Parsed scheme: {parsed.scheme}")
    if parsed.scheme == 'mysql':
        user = parsed.username or 'root'
        password = parsed.password or ''
        host = parsed.hostname or 'localhost'
        port = parsed.port or 3306
        database = parsed.path.lstrip('/')
        params = parse_qs(parsed.query)
        charset = params.get('charset', ['utf8mb4'])[0]
        return dict(user=user, password=password, host=host, port=port, database=database, charset=charset)
    if ';' in url and '=' in url:
        parts = [p.strip() for p in url.split(';') if p.strip()]
        kv = dict()
        for part in parts:
            if '=' in part:
                k, v = part.split('=', 1)
                kv[k.strip().lower()] = v.strip()
        user = kv.get('user', 'root')
        password = kv.get('password', '')
        host = kv.get('host', 'localhost')
        port = int(kv.get('port', 3306))
        database = kv.get('database', '')
        charset = kv.get('charset', 'utf8mb4')
        if not database:
            raise ValueError(f"Database name missing in connection string: {url}")
        return dict(user=user, password=password, host=host, port=port, database=database, charset=charset)
    raise ValueError(f"Unsupported DB connection string format. Must be mysql://... or user=...;host=...;port=...;database=...; (got: {url})")

def find_files(pattern: str, base: Path) -> List[Path]:
    return list(base.rglob(pattern))

def find_server_cfg_files(root: Path, max_levels_up: int = 2) -> List[Path]:
    found = set()
    current = root.resolve()
    for _ in range(max_levels_up + 1):
        found.update(find_files('server.cfg', current))
        if current.parent == current:
            break
        current = current.parent
    return list(found)

def get_db_url(root: Path) -> Optional[str]:
    load_dotenv()
    env_url = os.getenv('DATABASE_URL')
    if env_url:
        return env_url
    cfg_files = find_server_cfg_files(root)
    for cfg in cfg_files:
        url = extract_mysql_url_from_cfg(cfg)
        if url:
            return url
    return None

# --- Framework Detection ---
def detect_framework_for_file(sql_path: Path) -> Optional[str]:
    name = sql_path.name.lower()
    try:
        with sql_path.open(encoding='utf-8', errors='ignore') as f:
            content = f.read()
            if re.search(r'only for esx|esx where|esx only|es_extended', content, re.IGNORECASE):
                return 'esx'
            if re.search(r'insert\s+(ignore\s+)?[`\"]?items[`\"]?', content, re.IGNORECASE):
                return 'esx'
            if re.search(r'create table if not exists [`\"]?items[`\"]?', content, re.IGNORECASE):
                return 'esx'
            if (name in ['items_limit.sql', 'items_weight.sql']) and ('esx' in content.lower()):
                return 'esx'
            for pat in FRAMEWORK_PATTERNS['esx']:
                if re.search(pat, content, re.IGNORECASE):
                    return 'esx'
            for line in content.splitlines():
                if 'database.items' in line.lower():
                    return 'esx'
    except Exception:
        pass
    if 'qbx' in name:
        return 'qbx'
    try:
        with sql_path.open(encoding='utf-8', errors='ignore') as f:
            content = f.read()
            for pat in FRAMEWORK_PATTERNS['qbx']:
                if re.search(pat, content, re.IGNORECASE):
                    return 'qbx'
    except Exception:
        pass
    try:
        with sql_path.open(encoding='utf-8', errors='ignore') as f:
            content = f.read()
            qbcore_match = any(re.search(pat, content, re.IGNORECASE) for pat in FRAMEWORK_PATTERNS['qbcore'])
            ox_match = any(re.search(pat, content, re.IGNORECASE) for pat in FRAMEWORK_PATTERNS['ox'])
            if qbcore_match and ox_match:
                return 'qbx'
    except Exception:
        pass
    for fw, keywords in FRAMEWORKS.items():
        if fw in ('other', 'qbx'):
            continue
        if any(kw in name for kw in keywords):
            return fw
    try:
        with sql_path.open(encoding='utf-8', errors='ignore') as f:
            content = f.read(4096)
            for fw, patterns in FRAMEWORK_PATTERNS.items():
                if fw == 'qbx':
                    continue
                for pat in patterns:
                    if re.search(pat, content, re.IGNORECASE):
                        return fw
    except Exception:
        pass
    return None

# --- SQL Filtering ---
def filter_sql_files(sql_files: List[Path], framework: str) -> List[Path]:
    if framework == 'other':
        filtered = sql_files
    else:
        my_keywords = FRAMEWORKS[framework]
        other_keywords = [kw for fw, kws in FRAMEWORKS.items() if fw != framework and fw != 'other' for kw in kws]
        filtered = []
        for f in sql_files:
            name = f.name.lower()
            rel_path = os.path.normpath(str(f.relative_to(f.parents[len(f.parts)-2]))) if len(f.parts) > 1 else f.name
            detected_fw = detect_framework_for_file(f)
            if detected_fw == 'esx' and framework != 'esx':
                continue
            if detected_fw is None:
                try:
                    with f.open(encoding='utf-8', errors='ignore') as file_check:
                        for line in file_check:
                            if 'database.items' in line.lower() and framework != 'esx':
                                print(f"[DEBUG] Filter: Skipping {f} (contains database.items, not ESX)")
                                raise StopIteration
                except StopIteration:
                    continue
                except Exception:
                    pass
            if detected_fw and detected_fw != framework:
                continue
            if any(kw in name for kw in other_keywords):
                continue
            if (
                any(kw in name for kw in my_keywords)
                or not any(kw in name for kw in sum(FRAMEWORKS.values(), []))
                or detected_fw == framework
                or detected_fw is None
            ):
                filtered.append(f)
    filtered = [f for f in filtered if os.path.normpath(str(f.as_posix().lower())).replace('\\','/') not in [b.lower().replace('\\','/') for b in BLACKLISTED_FILES]]
    whitelist_paths = [os.path.normpath(w.lower().replace('\\','/')) for w in WHITELISTED_FILES]
    filtered_paths = set(os.path.normpath(str(f.as_posix().lower())).replace('\\','/') for f in filtered)
    for f in sql_files:
        rel_path = os.path.normpath(str(f.as_posix().lower())).replace('\\','/')
        if rel_path in whitelist_paths and rel_path not in filtered_paths:
            filtered.append(f)
    return filtered

# --- SQL Execution ---
def run_sql_file(sql_path: Path, conn) -> Optional[str]:
    try:
        with sql_path.open(encoding='utf-8', errors='ignore') as f:
            sql = f.read()
        cursor = conn.cursor()
        for statement in filter(None, map(str.strip, sql.split(';'))):
            if statement:
                cursor.execute(statement)
        conn.commit()
        cursor.close()
        return None
    except Exception as e:
        return str(e)

# --- Worker Thread for DB Execution ---
class SQLRunnerThread(QThread):
    progress = Signal(int)
    result = Signal(list)
    error = Signal(str)

    def __init__(self, root: Path, framework: str):
        super().__init__()
        self.root = root
        self.framework = framework

    def run(self):
        try:
            db_url = get_db_url(self.root)
            if not db_url:
                self.error.emit("Could not find a MySQL connection string in .env or any server.cfg.")
                return
            db_cfg = parse_mysql_url(db_url)
            sql_files = find_files('*.sql', self.root)
            sql_files = filter_sql_files(sql_files, self.framework)
            if not sql_files:
                self.error.emit("No relevant .sql files found for the selected framework.")
                return
            try:
                conn = mysql.connector.connect(
                    user=db_cfg['user'],
                    password=db_cfg['password'],
                    host=db_cfg['host'],
                    port=db_cfg['port'],
                    database=db_cfg['database'],
                    charset=db_cfg['charset'],
                    autocommit=False
                )
            except Exception as e:
                self.error.emit(f"Database connection failed: {e}")
                return
            results = []
            for i, sql_path in enumerate(sql_files):
                error = run_sql_file(sql_path, conn)
                results.append((str(sql_path.relative_to(self.root)), error is None, error or ""))
                self.progress.emit(int((i+1)/len(sql_files)*100))
            conn.close()
            self.result.emit(results)
        except Exception as e:
            self.error.emit(str(e))

# --- Main Window ---
class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Fivem Database Setup")
        self.setMinimumWidth(950)
        self.setWindowIcon(QIcon())
        main_layout = QVBoxLayout()
        main_layout.setSpacing(28)
        main_layout.setContentsMargins(56, 36, 56, 36)

        # --- Section: Framework Selection ---
        fw_group = QGroupBox("1. Select Your FiveM Framework")
        fw_group.setStyleSheet("QGroupBox { background: #202c24; border: 1.5px solid #3a4d3c; border-radius: 22px; margin-top: 22px; font-weight: bold; font-size: 18px; padding: 18px 28px; }")
        fw_layout = QHBoxLayout()
        fw_label = QLabel("Framework:")
        fw_label.setMinimumWidth(120)
        fw_label.setMaximumWidth(140)
        fw_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        fw_label.setStyleSheet("font-size: 15px; font-weight: 600; background: #232323; border-radius: 12px; padding: 8px 16px; margin-right: 10px; color: #b2ffcc;")
        self.fw_combo = QComboBox()
        self.fw_combo.addItem("QBCore", 'qbcore')
        self.fw_combo.addItem("QBX (QBCore fork for OX)", 'qbx')
        self.fw_combo.addItem("OX", 'ox')
        self.fw_combo.addItem("ESX", 'esx')
        self.fw_combo.addItem("Other (run all)", 'other')
        self.fw_combo.setToolTip("Choose your server's framework. Only relevant SQL files will be run.")
        self.fw_combo.setStyleSheet("font-size: 16px; padding: 8px 24px; border-radius: 16px; background: #232323; color: #e0e0e0; min-width: 220px; max-width: 320px; border: 1.5px solid #3a4d3c;")
        fw_layout.addWidget(fw_label)
        fw_layout.addWidget(self.fw_combo)
        fw_group.setLayout(fw_layout)
        main_layout.addWidget(fw_group)

        # --- Section: Directory Picker ---
        dir_group = QGroupBox("2. Select Root Directory to Scan")
        dir_group.setStyleSheet("QGroupBox { background: #202c24; border: 1.5px solid #3a4d3c; border-radius: 22px; margin-top: 22px; font-weight: bold; font-size: 18px; padding: 18px 28px; }")
        dir_layout = QHBoxLayout()
        self.dir_label = QLabel("No directory selected.")
        self.dir_label.setMinimumWidth(400)
        self.dir_label.setStyleSheet("font-size: 15px; color: #b2b2b2; background: #232323; border-radius: 16px; padding: 8px 18px; border: 1.5px solid #3a4d3c;")
        self.dir_btn = QPushButton("Browse...")
        self.dir_btn.setToolTip("Pick the root folder where your server.cfg and SQL files are located.")
        self.dir_btn.setStyleSheet("font-size: 16px; padding: 8px 32px; border-radius: 14px; background: #263b2e; color: #b2ffcc;")
        self.dir_btn.clicked.connect(self.pick_dir)
        dir_layout.addWidget(self.dir_label)
        dir_layout.addWidget(self.dir_btn)
        dir_group.setLayout(dir_layout)
        main_layout.addWidget(dir_group)

        # --- Section: Run Button ---
        self.run_btn = QPushButton("Run SQL Files")
        self.run_btn.setEnabled(False)
        self.run_btn.setStyleSheet("font-weight: bold; font-size: 22px; padding: 16px 60px; border-radius: 18px; background-color: #6fcf97; color: #181818; border: 2px solid #3a4d3c; margin-top: 18px;")
        self.run_btn.setToolTip("Scan and execute all relevant SQL files for your selected framework.")
        self.run_btn.clicked.connect(self.run_sqls)
        run_btn_layout = QHBoxLayout()
        run_btn_layout.addStretch(1)
        run_btn_layout.addWidget(self.run_btn)
        run_btn_layout.addStretch(1)
        main_layout.addLayout(run_btn_layout)

        # --- Section: Progress Bar ---
        self.progress = QProgressBar()
        self.progress.setValue(0)
        self.progress.setVisible(False)
        self.progress.setFixedHeight(34)
        self.progress.setStyleSheet("QProgressBar { background: #222; color: #fff; border-radius: 14px; font-size: 16px; } QProgressBar::chunk { background: #6fcf97; border-radius: 14px; }")
        main_layout.addWidget(self.progress)

        # --- Section: Results Table ---
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["File", "Framework", "Status", "Error"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setVisible(False)
        self.table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.table.setStyleSheet("QTableWidget { background: #181818; color: #fff; font-size: 16px; border-radius: 18px; } QHeaderView::section { background: #202c24; color: #6fcf97; font-weight: bold; font-size: 16px; border-radius: 18px; } QTableWidget::item { border-radius: 12px; }")
        main_layout.addWidget(self.table)

        # --- Section: Spacer for bottom padding ---
        main_layout.addSpacerItem(QSpacerItem(20, 50, QSizePolicy.Minimum, QSizePolicy.Expanding))

        # --- Footer: Made by Mr.Green ---
        footer = QLabel("<span style='color:#6fcf97; font-size:24px; font-weight:bold;'>Made by Mr.Green</span>")
        footer.setAlignment(Qt.AlignCenter)
        footer.setStyleSheet("margin-top: 24px; margin-bottom: 0px;")
        main_layout.addWidget(footer)

        # --- Set dark theme for the app ---
        self.setStyleSheet("""
            QWidget { background: #181818; color: #e0e0e0; font-family: 'Segoe UI', 'Arial', sans-serif; font-size: 17px; }
            QGroupBox { border: 1.5px solid #3a4d3c; border-radius: 22px; margin-top: 22px; font-weight: bold; font-size: 18px; padding: 18px 28px; }
            QGroupBox:title { subcontrol-origin: margin; left: 10px; padding: 0 3px 0 3px; }
            QLabel { font-size: 17px; }
            QPushButton { font-size: 17px; }
        """)

        self.setLayout(main_layout)
        self.root_path = None
        self.runner_thread = None

    def pick_dir(self):
        dir_path = QFileDialog.getExistingDirectory(self, "Select Root Directory")
        if dir_path:
            self.root_path = Path(dir_path)
            self.dir_label.setText(f"Selected: {dir_path}")
            self.run_btn.setEnabled(True)
        else:
            self.dir_label.setText("No directory selected.")
            self.run_btn.setEnabled(False)

    def run_sqls(self):
        framework = self.fw_combo.currentData()
        if not self.root_path or not framework:
            QMessageBox.warning(self, "Missing Info", "Please select a root directory and framework.")
            return
        self.progress.setValue(0)
        self.progress.setVisible(True)
        self.table.setRowCount(0)
        self.table.setVisible(False)
        self.run_btn.setEnabled(False)
        self.runner_thread = SQLRunnerThread(self.root_path, framework)
        self.runner_thread.progress.connect(self.progress.setValue)
        self.runner_thread.result.connect(self.show_results)
        self.runner_thread.error.connect(self.show_error)
        self.runner_thread.start()

    def show_results(self, results):
        self.progress.setVisible(False)
        self.table.setRowCount(len(results))
        for i, (file, ok, err) in enumerate(results):
            file_path = self.root_path / file
            detected_fw = detect_framework_for_file(file_path)
            self.table.setItem(i, 0, QTableWidgetItem(file))
            self.table.setItem(i, 1, QTableWidgetItem(detected_fw if detected_fw else "Generic"))
            self.table.setItem(i, 2, QTableWidgetItem("Success" if ok else "Failed"))
            self.table.setItem(i, 3, QTableWidgetItem(err))
        self.table.setVisible(True)
        self.run_btn.setEnabled(True)
        n_fail = sum(1 for _, ok, _ in results if not ok)
        if n_fail:
            QMessageBox.warning(self, "SQL Runner", f"{n_fail} file(s) failed. See table for details.")
        else:
            QMessageBox.information(self, "SQL Runner", "All SQL files executed successfully!")

    def show_error(self, msg):
        self.progress.setVisible(False)
        self.run_btn.setEnabled(True)
        QMessageBox.critical(self, "Error", msg)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec()) 