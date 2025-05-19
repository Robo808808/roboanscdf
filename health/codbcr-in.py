#!/usr/bin/env python3
"""
oracle_db_status_checker.py
===========================
Improved consolidated Oracle DB and Listener status reporter.

🔄 Key features:
- Timeout for sqlplus and lsnrctl commands to avoid hangs.
- Debug mode with --debug to show progress.
- HTML report written to /tmp/oracle_status_report_<timestamp>.html

Usage:
    ./oracle_db_status_checker.py
    ./oracle_db_status_checker.py --timeout 10 --debug
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

def parse_args():
    p = argparse.ArgumentParser(description="Oracle DB/Listener status checker")
    p.add_argument("--oratab", help="Path to oratab (optional)")
    p.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="SQLPlus / lsnrctl timeout (s)")
    p.add_argument("--debug", action="store_true", help="Verbose debug output")
    return p.parse_args()

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

class OracleRunner:
    """
    Wraps sqlplus calls for a specific ORACLE_HOME / ORACLE_SID,
    adding time-outs and convenience helpers that return dicts.
    """

    def __init__(self, home: str, sid: str, timeout: int = DEFAULT_TIMEOUT, debug: bool = False):
        self.home = home
        self.sid = sid
        self.timeout = timeout
        self.debug = debug

        if not Path(self.home).exists():
            raise ValueError(f"ORACLE_HOME does not exist: {self.home}")

    # ------------------------------------------------------------------ #
    # Environment & low-level helpers
    # ------------------------------------------------------------------ #
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
        """Run shell command with timeout and capture output."""
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
            raise RuntimeError(proc.stderr.strip() or f"Command failed: {cmd}")

        return proc.stdout.strip()

    # ------------------------------------------------------------------ #
    # Execute SQL via sqlplus (CSV or plain text)
    # ------------------------------------------------------------------ #
    def execute(self, sql: str, csv_fmt: bool = False) -> str:
        """Return raw output (string)."""
        with tempfile.NamedTemporaryFile("w+", delete=False, suffix=".sql") as tmp:
            if csv_fmt:
                tmp.write("SET PAGES 0 FEEDBACK OFF HEADING ON MARKUP CSV ON\n")
            else:
                tmp.write("SET PAGES 50000 LINES 1000 FEEDBACK OFF VERIFY OFF HEADING ON\n")
            tmp.write(sql + "\nEXIT;\n")
            script_path = tmp.name

        cmd = f"sqlplus -S '/ as sysdba' @{script_path}"
        try:
            return self._run(cmd)
        finally:
            Path(script_path).unlink(missing_ok=True)

    # Convenience wrapper: CSV → list(dict)
    def query_dict(self, sql: str):
        out = self.execute(sql, csv_fmt=True)
        return list(csv.DictReader(out.splitlines())) if out else []

    # ------------------------------------------------------------------ #
    # Public higher-level checks used by the report
    # ------------------------------------------------------------------ #
    def accessible(self) -> bool:
        try:
            return "1" in self.execute("SELECT 1 FROM dual")
        except Exception:
            return False

    def instance(self) -> Dict:
        return (self.query_dict("SELECT instance_name, status, database_status FROM v$instance") or [{}])[0]

    def role(self) -> Dict:
        return (self.query_dict("SELECT database_role, open_mode FROM v$database") or [{}])[0]

    def version(self) -> Dict:
        return (self.query_dict(\"\"\"SELECT banner FROM v$version WHERE banner LIKE 'Oracle%'\"\"\") or [{}])[0]

    def connections(self) -> Dict:
        return (
            self.query_dict(
                \"\"\"SELECT COUNT(*) AS active_connections
                     FROM v$session
                     WHERE status='ACTIVE' AND username IS NOT NULL\"\"\"
            )
            or [{}]
        )[0]

    def tablespaces(self) -> List[Dict]:
        return self.query_dict(
            \"\"\"
            WITH free AS (
              SELECT tablespace_name,
                     ROUND(SUM(bytes)/1048576,2) AS free_mb
              FROM dba_free_space
              GROUP BY tablespace_name
            ), size AS (
              SELECT tablespace_name,
                     ROUND(SUM(bytes)/1048576,2) AS size_mb,
                     ROUND(SUM(GREATEST(bytes,maxbytes))/1048576,2) AS max_size_mb
              FROM dba_data_files
              GROUP BY tablespace_name
            )
            SELECT s.tablespace_name,
                   size_mb,
                   free_mb,
                   max_size_mb,
                   ROUND((max_size_mb-free_mb)/max_size_mb*100,2) AS used_pct
            FROM size s
            JOIN free f ON f.tablespace_name = s.tablespace_name
            ORDER BY used_pct DESC
            \"\"\"
        )

###############################################################################
# 3. ListenerChecker (listener-side checks)
###############################################################################

class ListenerChecker:
    """
    Runs lsnrctl with time-outs and parses listener status.
    """

    def __init__(self, home: str, timeout: int = DEFAULT_TIMEOUT, debug: bool = False):
        self.home = home
        self.timeout = timeout
        self.debug = debug

    # --------------------------- helpers ---------------------------------- #
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
            proc = subprocess.run(
                cmd,
                shell=True,
                text=True,
                capture_output=True,
                env=self._env(),
                timeout=self.timeout,
            )
        except subprocess.TimeoutExpired:
            return "TIMEOUT"

        return proc.stdout

    # --------------------------- discovery -------------------------------- #
    def listener_names(self) -> List[str]:
        """Parse listener.ora to find custom listener names; default to LISTENER."""
        lsnr_ora = Path(self.home) / "network/admin/listener.ora"
        if not lsnr_ora.exists():
            return ["LISTENER"]

        names = set()
        for m in re.finditer(r"(\\w+)_?LISTENER\\s*=", lsnr_ora.read_text()):
            n = m.group(1)
            if n.upper() != "SID_LIST":
                names.add(n)
        return list(names) or ["LISTENER"]

    # --------------------------- status ----------------------------------- #
    def status(self, name: str) -> Dict:
        """
        Return dict with keys: name, status (UP/DOWN/TIMEOUT), services (list of svc names)
        """
        out = self._run(f"lsnrctl status {name}")

        if out == "TIMEOUT":
            return {"name": name, "status": "TIMEOUT", "services": []}

        status = "UP" if "The command completed successfully" in out else "DOWN"
        services = re.findall(r'Service\\s+"([^"]+)"', out)
        return {
            "name": name,
            "status": status,
            "services": [{"name": s} for s in services],
        }

    # --------------------------- convenience ------------------------------ #
    def all_statuses(self) -> List[Dict]:
        return [self.status(n) for n in self.listener_names()]

###############################################################################
# 4. HTML Report builder
###############################################################################

class Report:
    """Static helpers to build a simple colour-coded HTML report."""

    @staticmethod
    def _cls(value: str, good: float, warn: float):
        """Return CSS class for a numeric metric."""
        try:
            v = float(value)
            if v <= good:
                return "status-good"
            if v <= warn:
                return "status-warning"
        except Exception:
            pass
        return "status-error"

    # ------------------------------------------------------------------ #
    @classmethod
    def build(cls, dbs: List[Dict], listeners: List[Dict]) -> str:
        ts = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        host = os.uname().nodename

        # ---------------- Database summary rows ---------------------- #
        db_summary = ""
        detail_blocks = ""
        for d in dbs:
            sid = d["sid"]
            if not d.get("accessible"):
                db_summary += f"<tr><td>{sid}</td><td colspan=5 class='status-error'>NOT ACCESSIBLE</td></tr>"
                continue

            inst, role = d["instance"], d["role"]
            open_mode = role.get("OPEN_MODE", "UNKNOWN")
            db_role = role.get("DATABASE_ROLE", "UNKNOWN")
            status = inst.get("STATUS", "UNKNOWN")
            version = d["version"].get("banner", "UNKNOWN")

            status_cls = "status-good" if status == "OPEN" else "status-error"
            open_cls = "status-good" if (db_role == "PRIMARY" and open_mode == "READ WRITE") \
                or (db_role != "PRIMARY" and open_mode.startswith("READ ONLY")) else "status-error"

            db_summary += (
                f"<tr><td><a href='#db-{sid}'>{sid}</a></td>"
                f"<td>{db_role}</td>"
                f"<td class='{open_cls}'>{open_mode}</td>"
                f"<td class='{status_cls}'>{status}</td>"
                f"<td>{version}</td></tr>"
            )

            # ---------- Detail block per DB ---------- #
            conn = d["connections"].get("active_connections", "UNKNOWN")
            detail_blocks += f"<h2 id='db-{sid}'>{sid}</h2>"
            detail_blocks += (
                f"<p><b>Status:</b> <span class='{status_cls}'>{status}</span><br>"
                f"<b>Role:</b> {db_role}<br>"
                f"<b>Open Mode:</b> {open_mode}<br>"
                f"<b>Version:</b> {version}<br>"
                f"<b>Active Connections:</b> {conn}</p>"
            )

            # Tablespaces
            if d["tablespaces"]:
                detail_blocks += "<table><tr><th>Tablespace</th><th>Size MB</th><th>Free MB</th><th>% Used</th></tr>"
                for ts in d["tablespaces"]:
                    used_cls = cls._cls(ts["used_pct"], 75, 90)
                    detail_blocks += (
                        f"<tr><td>{ts['tablespace_name']}</td>"
                        f"<td>{ts['size_mb']}</td><td>{ts['free_mb']}</td>"
                        f"<td class='{used_cls}'>{ts['used_pct']}</td></tr>"
                    )
                detail_blocks += "</table><br>"

            detail_blocks += "<hr>"

        # ---------------- Listener summary rows --------------------- #
        l_rows = ""
        for group in listeners:
            for l in group["listeners"]:
                stat_cls = "status-good" if l["status"] == "UP" else "status-error"
                svc = ", ".join(s["name"] for s in l["services"]) or "—"
                l_rows += (
                    f"<tr><td>{l['name']}</td>"
                    f"<td class='{stat_cls}'>{l['status']}</td>"
                    f"<td>{svc}</td>"
                    f"<td>{group['oracle_home']}</td></tr>"
                )

        # ---------------- Combine HTML ------------------------------ #
        return f"""
        <html>
        <head>
            <title>Oracle Status Report</title>
            <style>
                body {{font-family: Arial, sans-serif; margin: 20px}}
                table {{border-collapse: collapse; width: 100%}}
                th, td {{border: 1px solid #ccc; padding: 6px; text-align: left}}
                th {{background:#f0f0f0}}
                .status-good {{background:#c8e6c9}}
                .status-warning {{background:#fff9c4}}
                .status-error {{background:#ffcdd2}}
            </style>
        </head>
        <body>
            <h1>Oracle Database & Listener Report</h1>
            <p><b>Host:</b> {host} &nbsp; <b>Generated:</b> {ts}</p>

            <h2>Database Summary</h2>
            <table>
                <tr><th>SID</th><th>Role</th><th>Open Mode</th><th>Status</th><th>Version</th></tr>
                {db_summary}
            </table>

            <h2>Listener Summary</h2>
            <table>
                <tr><th>Name</th><th>Status</th><th>Services</th><th>ORACLE_HOME</th></tr>
                {l_rows}
            </table>

            <hr>
            {detail_blocks}
        </body>
        </html>
        """


###############################################################################
# 5. main() – gather info & write the report
###############################################################################

def main():
    args = parse_args()

    parser = OratabParser(args.oratab)
    dbs: List[Dict] = []
    listener_by_home: Dict[str, Dict] = {}

    # ---------- gather DB info ---------- #
    for entry in parser.entries():
        sid, home = entry["sid"], entry["oracle_home"]
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

        # ---------- listener (per ORACLE_HOME) ---------- #
        if home not in listener_by_home:
            lchk = ListenerChecker(home, args.timeout, args.debug)
            listener_by_home[home] = {
                "oracle_home": home,
                "listeners": lchk.all_statuses(),
            }

    # HTML report
    html = Report.build(dbs, list(listener_by_home.values()))
    out_file = f"/tmp/oracle_status_report_{_dt.datetime.now():%Y%m%d_%H%M%S}.html"
    Path(out_file).write_text(html)
    print(f"Report written → {out_file}")

if __name__ == "__main__":
    main()
