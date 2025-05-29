# FDS
FDS is a super easy tool for FiveM servers that finds and runs the right SQL files for your framework (QBCore, ESX, OX, QBX, or generic). Includes a modern GUI and simple CLI. Made by Mr.Green (Discord: mrgreen_2630)
# Fivem Database Setup

A tool to scan your FiveM server for `.sql` files and run them on your database. Works with both a modern GUI and a simple command-line (CLI) version.

---

## Quick Start (English)

### 1. Install
```bash
pip install -r requirements.txt
```

### 2. Run the GUI (Recommended)
```bash
python FDS_gui.py
```
- Pick your framework (QBCore, QBX, OX, ESX, Other)
- Pick your server folder (where server.cfg is)
- Click "Run SQL Files"

### 3. Run the CLI (Terminal)
```bash
python FDS_cli.py
```
- Follow the prompts for framework and folder

### 4. What it does
- Finds your `server.cfg` (searches up if needed)
- Uses the folder with `server.cfg` as the root
- Runs only the SQL files for your framework (auto-detects ESX, QBCore, OX, QBX, or generic)
- Skips blacklisted files, always runs whitelisted files
- Shows a summary at the end

### 5. Troubleshooting
- Make sure your MySQL connection string is in `.env` or `server.cfg` (see example below)
- Supported formats:
  - `mysql://user:password@host/database?charset=utf8mb4`
  - `user=...;host=...;port=...;database=...`
- If nothing is found, check your folder and try again

---

## Example MySQL connection string
```
set mysql_connection_string "mysql://root:password@localhost/database?charset=utf8mb4"
```

---

## Dansk vejledning (Danish guide)

### 1. Installer
```bash
pip install -r requirements.txt
```

### 2. Kør GUI (anbefalet)
```bash
python FDS_gui.py
```
- Vælg dit framework (QBCore, QBX, OX, ESX, Andet)
- Vælg din servermappe (hvor server.cfg ligger)
- Klik "Run SQL Files"

### 3. Kør CLI (terminal)
```bash
python FDS_cli.py
```
- Følg instruktionerne for framework og mappe

### 4. Hvad gør den?
- Finder din `server.cfg` (søger opad hvis nødvendigt)
- Bruger mappen med `server.cfg` som rod
- Kører kun SQL-filer til dit framework (finder selv ESX, QBCore, OX, QBX eller generiske)
- Springer blacklistede filer over, kører altid whitelists
- Viser et overblik til sidst

### 5. Fejlfinding
- Sørg for at din MySQL connection string er i `.env` eller `server.cfg` (se eksempel ovenfor)
- Hvis intet findes, tjek din mappe og prøv igen

---

**Made by Mr.Green** 

## Contact
If you need help or have questions, contact Mr.Green on Discord: **mrgreen_2630** 
