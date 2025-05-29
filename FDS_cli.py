import sys
import subprocess
import importlib.util
import os
import re
from pathlib import Path
from typing import List, Optional
from dotenv import load_dotenv
import mysql.connector

REQUIRED = [
    ('mysql', 'mysql-connector-python'),
    ('dotenv', 'python-dotenv'),
]
for module, package in REQUIRED:
    if importlib.util.find_spec(module) is None:
        print(f"[Auto-Installer] Installing missing package: {package}")
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', package])

FRAMEWORKS = {
    'qbcore': ['qbcore', 'qb'],
    'qbx': ['qbx'],
    'ox': ['ox', 'oxcore'],
    'esx': ['esx'],
    'other': []
}

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
    parsed = urlparse(url)
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

def find_server_cfg_files_upward(start_dir: Path, max_levels: int = 10) -> list:
    """Search upward from start_dir for server.cfg, up to max_levels directories above."""
    current = start_dir.resolve()
    checked = set()
    for _ in range(max_levels + 1):
        if current in checked:
            break
        checked.add(current)
        found = list(current.rglob('server.cfg'))
        if found:
            return found
        if current.parent == current:
            break
        print(f"[INFO] No server.cfg found in {current}. Going up to {current.parent}...")
        current = current.parent
    return []

def get_db_url_and_cfg_dir(root: Path) -> (Optional[str], Optional[Path]):
    load_dotenv()
    env_url = os.getenv('DATABASE_URL')
    if env_url:
        return env_url, None
    cfg_files = find_server_cfg_files_upward(root)
    for cfg in cfg_files:
        url = extract_mysql_url_from_cfg(cfg)
        if url:
            return url, cfg.parent
    return None, None

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

def main():
    print(r'''
 /$$      /$$            /$$$$$$                                         
| $$$    /$$$           /$$__  $$                                        
| $$$$  /$$$$  /$$$$$$ | $$  \__/  /$$$$$$   /$$$$$$   /$$$$$$  /$$$$$$$ 
| $$ $$/$$ $$ /$$__  $$| $$ /$$$$ /$$__  $$ /$$__  $$ /$$__  $$| $$__  $$
| $$  $$$| $$| $$  \__/| $$|_  $$| $$  \__/| $$$$$$$$| $$$$$$$$| $$  \ $$
| $$\  $ | $$| $$      | $$  \ $$| $$      | $$_____/| $$_____/| $$  | $$
| $$ \/  | $$| $$      |  $$$$$$/| $$      |  $$$$$$$|  $$$$$$$| $$  | $$
|__/     |__/|__/       \______/ |__/       \_______/ \_______/|__/  |__/
                                                                         
                                                                         
                                                                         
''')
    print("Made by Mr. Green\n")
    print("=== Fivem Database Setup ===\n")
    print("Select your FiveM framework:")
    fw_options = list(FRAMEWORKS.keys())
    for i, fw in enumerate(fw_options, 1):
        print(f"  {i}. {fw.capitalize()}")
    while True:
        try:
            fw_choice = int(input("Enter the number for your framework: ").strip())
            if 1 <= fw_choice <= len(fw_options):
                framework = fw_options[fw_choice-1]
                break
        except Exception:
            pass
        print("Invalid choice. Please enter a valid number.")
    root = None
    while not root:
        root_input = input("Enter the root directory to scan for server.cfg (or leave blank for current directory): ").strip()
        root = Path(root_input) if root_input else Path('.')
        if not root.exists() or not root.is_dir():
            print("Invalid directory. Please try again.")
            root = None
    db_url, cfg_dir = get_db_url_and_cfg_dir(root)
    if not db_url:
        print("[ERROR] Could not find a MySQL connection string in .env or any server.cfg.")
        sys.exit(1)
    try:
        db_cfg = parse_mysql_url(db_url)
    except Exception as e:
        print(f"[ERROR] Error parsing DB URL: {e}")
        sys.exit(1)
    # Use the directory where server.cfg was found (or user root if .env was used)
    scan_root = cfg_dir if cfg_dir else root
    print(f"\n[INFO] Using framework: {framework.capitalize()} | Scanning for .sql files in: {scan_root.resolve()}")
    sql_files = find_files('*.sql', scan_root)
    sql_files = filter_sql_files(sql_files, framework)
    if not sql_files:
        print("[INFO] No relevant .sql files found for the selected framework.")
        sys.exit(0)
    print(f"[INFO] Found {len(sql_files)} .sql files to execute.")
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
        print(f"[ERROR] Database connection failed: {e}")
        sys.exit(1)
    results = []
    for i, sql_path in enumerate(sql_files, 1):
        print(f"[{i}/{len(sql_files)}] Executing: {sql_path.relative_to(scan_root)} ...", end=' ')
        error = run_sql_file(sql_path, conn)
        if error:
            print(f"FAILED: {error}")
            results.append((str(sql_path.relative_to(scan_root)), False, error))
        else:
            print("Success")
            results.append((str(sql_path.relative_to(scan_root)), True, None))
    conn.close()
    print("\n=== SQL Execution Summary ===")
    for file, ok, err in results:
        status = "Success" if ok else f"FAILED: {err}"
        print(f"- {file}: {status}")
    n_ok = sum(1 for _, ok, _ in results if ok)
    n_fail = len(results) - n_ok
    if n_fail:
        print(f"\n[ERROR] {n_fail} file(s) failed.")
        sys.exit(2)
    else:
        print(f"\n[INFO] All SQL files executed successfully!")

if __name__ == "__main__":
    main() 
