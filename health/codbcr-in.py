#!/usr/bin/env python3
"""
oracle_db_status_checker.py
===========================
Improved consolidated Oracle DB and Listener status reporter.

🔄 **Key changes in this version**
---------------------------------
* **Timeout‑proof** – all `subprocess.run()` calls have a 30‑second default
  timeout so the script never hangs if `sqlplus` or `lsnrctl` stalls.
* Adds a `--timeout N` CLI option (seconds) to override the default.
* Graceful handling of `subprocess.TimeoutExpired` – marks DB or listener as
  `TIMEOUT` instead of hanging.
* Extra debug output with `--debug` (prints every SID / listener as processed).
* Entire script remains a single, self‑contained file – just drop it on the
  server, `chmod +x`, and run.

Usage
-----
```bash
# run with defaults (30‑second timeouts)
./oracle_db_status_checker.py

# custom timeout and verbose debug output
./oracle_db_status_checker.py --timeout 10 --debug
```
The report is written to `/tmp/oracle_status_report_<timestamp>.html`.
"""
from __future__ import annotations

import argparse
import csv
import datetime as _dt
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

DEFAULT_TIMEOUT = 30  # seconds

###############################################################################
# 1. Command‑line args & helpers
###############################################################################

def parse_args():
    p = argparse.ArgumentParser(description="Oracle DB/Listener status checker")
    p.add_argument("--oratab", help="Path to oratab (optional)")
    p.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="SQLPlus / lsnrctl timeout (s)")
    p.add_argument("--debug", action="store_true", help="Verbose debug output")
    return p.parse_args()

###############################################################################
# 2. Oratab parser
###############################################################################

class OratabParser:
    LOCATIONS = [
        "/etc/oratab",
        "/var/opt/oracle/oratab",
        "/opt/oracle/oratab",
    ]

    def __init__(self, path: Optional[str] = None):
        self.path = path or self._auto_locate()
        if not self.path or not Path(self.path).exists():
            raise FileNotFoundError("oratab not found – supply with --oratab")

    def _auto_locate(self) -> Optional[str]:
        for p in self.LOCATIONS:
            if Path(p).exists():
                return p
        return None

    def entries(self):
        for line in Path(self.path).read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            sid, *rest = line.split(":")
            if len(rest) < 1:
                continue
            home = rest[0]
            if sid.startswith("+") or sid.startswith("*"):
                continue
            yield {"sid": sid, "oracle_home": home}

###############################################################################
# 3. OracleRunner with timeout
###############################################################################

class OracleRunner:
    def __init__(self, home: str, sid: str, timeout: int, debug: bool = False):
        self.home, self.sid, self.timeout, self.debug = home, sid, timeout, debug
        if not Path(self.home).exists():
            raise ValueError(f"ORACLE_HOME missing: {self.home}")

    def _env(self):
        e = os.environ.copy()
        e.update(
            {
                "ORACLE_HOME": self.home,
                "ORACLE_SID": self.sid,
                "PATH": f"{self.home}/bin:" + e.get("PATH", ""),
                "LD_LIBRARY_PATH": f"{self.home}/lib:" + e.get("LD_LIBRARY_PATH", ""),
            }
        )
        return e

    # ------------------------------------------------------------------
    def _run(self, cmd: str, stdin_file: Optional[str] = None):
        if self.debug:
            print("[DEBUG]", cmd)
        try:
            proc = subprocess.run(
                cmd,
                shell=True,
                text=True,
                capture_output=True,
                timeout=self.timeout,
                env=self._env(),
            )
        except subprocess.TimeoutExpired:
            raise TimeoutError(f"Command timed out after {self.timeout}s: {cmd}")
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.strip())
        return proc.stdout.strip()

    # ------------------------------------------------------------------
    def execute(self, sql: str, csv_fmt: bool = False):
        with tempfile.NamedTemporaryFile("w+", delete=False, suffix=".sql") as f:
            if csv_fmt:
                f.write("SET PAGES 0 FEEDBACK OFF HEADING ON MARKUP CSV ON\n")
            else:
                f.write("SET PAGES 50000 LINES 1000 FEEDBACK OFF VERIFY OFF HEADING ON\n")
            f.write(sql + "\nEXIT;\n")
            tmp = f.name
        cmd = f"sqlplus -S '/ as sysdba' @{tmp}"
        try:
            return self._run(cmd)
        finally:
            Path(tmp).unlink(missing_ok=True)

    # Convenience wrappers ---------------------------------------------
    def query_dict(self, sql: str):
        out = self.execute(sql, csv_fmt=True)
        return list(csv.DictReader(out.splitlines())) if out else []

    # Public high‑level helpers ----------------------------------------
    def accessible(self):
        try:
            return "1" in self.execute("select 1 from dual")
        except Exception:
            return False

    def instance(self):
        return (self.query_dict("select instance_name,status,database_status from v$instance") or [{}])[0]

    def role(self):
        return (self.query_dict("select database_role,open_mode from v$database") or [{}])[0]

    def version(self):
        return (self.query_dict("select banner from v$version where banner like 'Oracle%'") or [{}])[0]

    def connections(self):
        return (self.query_dict("select count(*) active from v$session where status='ACTIVE' and username is not null") or [{}])[0]

    def tablespaces(self):
        return self.query_dict(
            """
            with a as (
              select tablespace_name, round(sum(bytes)/1048576,2) free_mb from dba_free_space group by tablespace_name
            ), b as (
              select tablespace_name, round(sum(bytes)/1048576,2) size_mb,
                     round(sum(greatest(bytes,maxbytes))/1048576,2) max_size_mb
              from dba_data_files group by tablespace_name)
            select a.tablespace_name, size_mb, free_mb,
                   max_size_mb,
                   round((max_size_mb-free_mb)/max_size_mb*100,2) used_pct
            from a join b using (tablespace_name) order by used_pct desc
            """
        )

###############################################################################
# 4. ListenerChecker with timeout
###############################################################################

class ListenerChecker:
    def __init__(self, home: str, timeout: int, debug: bool = False):
        self.home, self.timeout, self.debug = home, timeout, debug

    def _env(self):
        e = os.environ.copy()
        e.update(
            {
                "ORACLE_HOME": self.home,
                "PATH": f"{self.home}/bin:" + e.get("PATH", ""),
                "LD_LIBRARY_PATH": f"{self.home}/lib:" + e.get("LD_LIBRARY_PATH", ""),
            }
        )
        return e

    def _run(self, cmd: str):
        if self.debug:
            print("[DEBUG]", cmd)
        try:
            proc = subprocess.run(cmd, shell=True, text=True, capture_output=True, timeout=self.timeout, env=self._env())
        except subprocess.TimeoutExpired:
            return "TIMEOUT"
        return proc.stdout

    def listener_names(self):
        lsnr_ora = Path(self.home) / "network/admin/listener.ora"
        if not lsnr_ora.exists():
            return ["LISTENER"]
        names = set()
        for m in re.finditer(r"(\w+)_?LISTENER\s*=", lsnr_ora.read_text()):
            n = m.group(1)
            if n.upper() != "SID_LIST":
                names.add(n)
        return list(names) or ["LISTENER"]

    def status(self, name: str):
        out = self._run(f"lsnrctl status {name}")
        if out == "TIMEOUT":
            return {"name": name, "status": "TIMEOUT", "services": []}
        status = "UP" if "The command completed successfully" in out else "DOWN"
        svcs = re.findall(r'Service "([^"]+)"', out)
        return {"name": name, "status": status, "services": [{"name": s} for s in svcs]}

###############################################################################
# 5. HTML report builder (unchanged from previous concise version)
###############################################################################

class Report:
    @staticmethod
    def _cls(val: str, good: float, warn: float):
        try:
            v = float(val)
            if v <= good:
                return "status-good"
            if v <= warn:
                return "status-warning"
        except Exception:
            pass
        return "status-error"

    @classmethod
    def build(cls, dbs: List[Dict], listeners: List[Dict]):
        ts = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        host = os.uname().nodename
        db_rows, detail = "", ""
        for d in dbs:
            sid = d["sid"]
            if not d.get("accessible"):
                db_rows += f"<tr><td>{sid}</td><td colspan=4 class=status-error>NOT ACCESSIBLE</td></tr>"
                continue
            inst, role = d["instance"], d["role"]
            status = inst.get("STATUS", "UNKNOWN")
            status_cls = "status-good" if status == "OPEN" else "status-error"
            db_rows += (
                f"<tr><td><a href=#db-{sid}>{sid}</a></td><td>{role.get('DATABASE_ROLE')}
