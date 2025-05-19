#!/usr/bin/env python3
"""
oracle_db_status_checker.py
===========================
Consolidated Oracle DB & Listener status report.

Features
--------
* Reads oratab to discover every SID / ORACLE_HOME.
* Runs sqlplus checks with a timeout (default 30 s) to avoid hangs.
* Runs lsnrctl status with the same timeout.
* Generates colour-coded HTML in /tmp/oracle_status_report_<timestamp>.html.
* Optional --debug flag prints progress.
"""

from __future__ import annotations

import argparse
import csv
import datetime as _dt
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

DEFAULT_TIMEOUT = 30  # seconds

###############################################################################
# 1. CLI args
###############################################################################
def parse_args():
    p = argparse.ArgumentParser(description="Oracle DB & Listener status checker")
    p.add_argument("--oratab", help="Path to oratab (optional)")
    p.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="sqlplus / lsnrctl timeout (s)")
    p.add_argument("--debug", action="store_true", help="Verbose debug output")
    return p.parse_args()

###############################################################################
# 2. Oratab parser
###############################################################################
class OratabParser:
    LOCATIONS = ["/etc/oratab", "/var/opt/oracle/oratab", "/opt/oracle/oratab"]

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
            if sid.startswith(("+", "*")):
                continue
            yield {"sid": sid, "oracle_home": home}

###############################################################################
# 3. OracleRunner (DB checks)
###############################################################################
class OracleRunner:
    def __init__(self, home: str, sid: str, timeout: int, debug: bool = False):
        self.home, self.sid, self.timeout, self.debug = home, sid, timeout, debug
        if not Path(self.home).exists():
            raise ValueError(f"ORACLE_HOME does not exist: {self.home}")

    # ----- helpers -------------------------------------------------------
    def _env(self):
        env = os.environ.copy()
        env.update(
            {
                "ORACLE_HOME": self.home,
                "ORACLE_SID": self.sid,
                "PATH": f"{self.home}/bin:" + env.get("PATH", ""),
                "LD_LIBRARY_PATH": f"{self.home}/lib:" + env.get("LD_LIBRARY_PATH", ""),
            }
        )
        return env

    def _run(self, cmd: str):
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
            raise TimeoutError(f"Timeout ({self.timeout}s) on {cmd}")
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.strip() or f"Command failed: {cmd}")
        return proc.stdout.strip()

    # ----- sqlplus wrapper ----------------------------------------------
    def execute(self, sql: str, csv_fmt: bool = False) -> str:
        with tempfile.NamedTemporaryFile("w+", delete=False, suffix=".sql") as tmp:
            if csv_fmt:
                tmp.write("SET PAGES 0 FEEDBACK OFF HEADING ON MARKUP CSV ON\n")
            else:
                tmp.write("SET PAGES 50000 LINES 1000 FEEDBACK OFF VERIFY OFF HEADING ON\n")
            tmp.write(sql + "\nEXIT;\n")
            script = tmp.name
        try:
            return self._run(f"sqlplus -S '/ as sysdba' @{script}")
        finally:
            Path(script).unlink(missing_ok=True)

    def query_dict(self, sql: str):
        out = self.execute(sql, csv_fmt=True)
        return list(csv.DictReader(out.splitlines())) if out else []

    # ----- high-level DB info -------------------------------------------
    def accessible(self) -> bool:
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
        return (
            self.query_dict("select count(*) active_connections from v$session where status='ACTIVE' and username is not null") or [{}]
        )[0]

    def tablespaces(self):
        return self.query_dict(
            """
            with free as (
              select tablespace_name, round(sum(bytes)/1048576,2) free_mb
              from dba_free_space group by tablespace_name
            ), size as (
              select tablespace_name,
                     round(sum(bytes)/1048576,2) size_mb,
                     round(sum(greatest(bytes,maxbytes))/1048576,2) max_size_mb
              from dba_data_files group by tablespace_name
            )
            select s.tablespace_name,
                   size_mb,
                   free_mb,
                   max_size_mb,
                   round((max_size_mb-free_mb)/max_size_mb*100,2) used_pct
            from size s join free f on f.tablespace_name=s.tablespace_name
            order by used_pct desc
            """
        )

###############################################################################
# 4. ListenerChecker
###############################################################################
class ListenerChecker:
    def __init__(self, home: str, timeout: int, debug: bool = False):
        self.home, self.timeout, self.debug = home, timeout, debug

    def _env(self):
        env = os.environ.copy()
        env.update(
            {
                "ORACLE_HOME": self.home,
                "PATH": f"{self.home}/bin:" + env.get("PATH", ""),
                "LD_LIBRARY_PATH": f"{self.home}/lib:" + env.get("LD_LIBRARY_PATH", ""),
            }
        )
        return env

    def _run(self, cmd: str) -> str:
        if self.debug:
            print("[DEBUG]", cmd)
        try:
            proc = subprocess.run(cmd, shell=True, text=True, capture_output=True, timeout=self.timeout, env=self._env())
        except subprocess.TimeoutExpired:
            return "TIMEOUT"
        return proc.stdout

    # ----- discover listener names --------------------------------------
    def listener_names(self) -> List[str]:
        lsnr_ora = Path(self.home) / "network/admin/listener.ora"
        if not lsnr_ora.exists():
            return ["LISTENER"]
        names = set()
        for m in re.finditer(r"(\w+)_?LISTENER\s*=", lsnr_ora.read_text()):
            n = m.group(1)
            if n.upper() != "SID_LIST":
                names.add(n)
        return list(names) or ["LISTENER"]

    # ----- status --------------------------------------------------------
    def status(self, name: str) -> Dict:
        out = self._run(f"lsnrctl status {name}")
        if out == "TIMEOUT":
            return {"name": name, "status": "TIMEOUT", "services": []}
        status = "UP" if "The command completed successfully" in out else "DOWN"
        services = re.findall(r'Service\s+"([^"]+)"', out)
        return {"name": name, "status": status, "services": [{"name": s} for s in services]}

    # convenience
    def all_statuses(self):
        return [self.status(n) for n in self.listener_names()]

###############################################################################
# 5. HTML report builder
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
    def build(cls, dbs: List[Dict], listeners: List[Dict]) -> str:
        ts = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        host = os.uname().nodename

        # ---- DB summary ----
        db_rows = ""
        db_details = ""
        for d in dbs:
            sid = d["sid"]
            if not d.get("accessible"):
                db_rows += f"<tr><td>{sid}</td><td colspan=4 class='status-error'>NOT ACCESSIBLE</td></tr>"
                continue

            inst, role = d["instance"], d["role"]
            status = inst.get("STATUS", "UNKNOWN")
            open_mode = role.get("OPEN_MODE", "UNKNOWN")
            db_role = role.get("DATABASE_ROLE", "UNKNOWN")
            version = d["version"].get("banner", "UNKNOWN")

            status_cls = "status-good" if status == "OPEN" else "status-error"
            if db_role == "PRIMARY":
                open_cls = "status-good" if open_mode == "READ WRITE" else "status-error"
            else:
                open_cls = "status-good" if open_mode.startswith("READ ONLY") else "status-error"

            db_rows += (
                f"<tr><td><a href='#db-{sid}'>{sid}</a></td>"
                f"<td>{db_role}</td>"
                f"<td class='{open_cls}'>{open_mode}</td>"
                f"<td class='{status_cls}'>{status}</td>"
                f"<td>{version}</td></tr>"
            )

            # --- details block ---
            conn = d["connections"].get("active_connections", "UNKNOWN")
            db_details += f"<h2 id='db-{sid}'>{sid}</h2>"
            db_details += (
                f"<p><b>Status:</b> <span class='{status_cls}'>{status}</span><br>"
                f"<b>Role:</b> {db_role}<br>"
                f"<b>Open Mode:</b> {open_mode}<br>"
                f"<b>Version:</b> {version}<br>"
                f"<b>Active Connections:</b> {conn}</p>"
            )

            if d["tablespaces"]:
                db_details += "<table><tr><th>Tablespace</th><th>Size MB</th><th>Free MB</th><th>% Used</th></tr>"
                for t in d["tablespaces"]:
                    used_cls = cls._cls(t["used_pct"], 75, 90)
                    db_details += (
                        f"<tr><td>{t['tablespace_name']}</td>"
                        f"<td>{t['size_mb']}</td><td>{t['free_mb']}</td>"
                        f"<td class='{used_cls}'>{t['used_pct']}</td></tr>"
                    )
                db_details += "</table><br>"
            db_details += "<hr>"

        # ---- Listener summary ----
        l_rows = ""
        for g in listeners:
            for l in g["listeners"]:
                stat_cls = "status-good" if l["status"] == "UP" else "status-error"
                services = ", ".join(s["name"] for s in l["services"]) or "—"
                l_rows += (
                    f"<tr><td>{l['name']}</td>"
                    f"<td class='{stat_cls}'>{l['status']}</td>"
                    f"<td>{services}</td>"
                    f"<td>{g['oracle_home']}</td></tr>"
                )

        # ---- HTML ----
        return f"""
        <html>
        <head>
            <title>Oracle Status Report</title>
            <style>
                body{{font-family:Arial,sans-serif;margin:20px}}
                table{{border-collapse:collapse;width:100%}}
                th,td{{border:1px solid #ccc;padding:6px;text-align:left}}
                th{{background:#f0f0f0}}
                .status-good{{background:#c8e6c9}}
                .status-warning{{background:#fff9c4}}
                .status-error{{background:#ffcdd2}}
            </style>
        </head>
        <body>
            <h1>Oracle Database & Listener Report</h1>
            <p><b>Host:</b> {host} &nbsp;&nbsp; <b>Generated:</b> {ts}</p>

            <h2>Database Summary</h2>
            <table>
                <tr><th>SID</th><th>Role</th><th>Open Mode</th><th>Status</th><th>Version</th></tr>
                {db_rows}
            </table>

            <h2>Listener Summary</h2>
            <table>
                <tr><th>Name</th><th>Status</th><th>Services</th><th>ORACLE_HOME</th></tr>
                {l_rows}
            </table>

            <hr>
            {db_details}
        </body>
        </html>
        """

###############################################################################
# 6. Main
###############################################################################
def main():
    args = parse_args()
    parser = OratabParser(args.oratab)

    dbs: List[Dict] = []
    listeners_by_home: Dict[str, Dict] = {}

    for e in parser.entries():
        sid, home = e["sid"], e["oracle_home"]
        orc = OracleRunner(home, sid, args.timeout, args.debug)
        info = {"sid": sid, "oracle_home": home}

        if not orc.accessible():
            info["accessible"] = False
            dbs.append(info)
            continue

        info["accessible"] = True
        info["instance"] = orc.instance()
        info["role"] = orc.role()
        info["version"] = orc.version()
        info["connections"] = orc.connections()
        info["tablespaces"] = orc.tablespaces()
        dbs.append(info)

        if home not in listeners_by_home:
            lchk = ListenerChecker(home, args.timeout, args.debug)
            listeners_by_home[home] = {
                "oracle_home": home,
                "listeners": lchk.all_statuses(),
            }

    html = Report.build(dbs, list(listeners_by_home.values()))
    out = f"/tmp/oracle_status_report_{_dt.datetime.now():%Y%m%d_%H%M%S}.html"
    Path(out).write_text(html)
    print(f"Report written → {out}")

if __name__ == "__main__":
    main()
