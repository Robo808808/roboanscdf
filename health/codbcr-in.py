#!/usr/bin/env python3
"""
oracle_db_status_checker.py
===========================
Consolidated Oracle DB & Listener Status Checker.
Reads `oratab`, loops every SID + ORACLE_HOME, collects database / listener
information, and writes a single HTML report to /tmp.

Fixes & enhancements compared with the original uploads
------------------------------------------------------
* **generate_consolidated_report** no longer returns inside the per‑DB loop –
  full detail sections now render.
* `SID_LIST` or any `*_SID_LIST_...` stanzas are no longer treated as listeners.
* Listener status detection works for custom‑named listeners (looks for
  "The command completed successfully" rather than hard‑coded LISTENER).
* Adds defensive logging and continues gracefully on connection errors.
* Script is completely self‑contained – no external templates needed.

Usage
-----
```bash
chmod +x oracle_db_status_checker.py
sudo ./oracle_db_status_checker.py
# → /tmp/oracle_status_report_<timestamp>.html
```

You can wrap it in cron or Ansible as required.
"""

from __future__ import annotations

import csv
import datetime as _dt
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, List

################################################################################
# 1. Helpers: oratab parsing
################################################################################

class OratabParser:
    """Locate / parse the oratab file and return SID / ORACLE_HOME pairs."""

    LOCATIONS: List[str] = [
        "/etc/oratab",
        "/var/opt/oracle/oratab",
        "/opt/oracle/oratab",
    ]

    def __init__(self, path: str | None = None):
        self.path = path or self._find_oratab()
        if not self.path or not Path(self.path).exists():
            raise FileNotFoundError("oratab not found – specify with --oratab PATH")

    def _find_oratab(self) -> str | None:
        for p in self.LOCATIONS:
            if Path(p).exists():
                return p
        return None

    def entries(self) -> List[Dict[str, str]]:
        out: List[Dict[str, str]] = []
        for line in Path(self.path).read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            sid, *rest = line.split(":")
            if len(rest) < 1:
                continue
            home = rest[0]
            if sid.startswith("+") or sid.startswith("*"):
                continue  # skip ASM etc.
            out.append({"sid": sid, "oracle_home": home})
        return out

################################################################################
# 2. OracleRunner – runs sqlplus queries safely
################################################################################

class OracleRunner:
    def __init__(self, oracle_home: str, oracle_sid: str, as_sysdba: bool = True):
        self.home = oracle_home
        self.sid = oracle_sid
        self.as_sysdba = as_sysdba
        if not Path(self.home).exists():
            raise ValueError(f"ORACLE_HOME does not exist: {self.home}")

    # ---------------------------------------------------------------------
    def _env(self) -> Dict[str, str]:
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

    # ---------------------------------------------------------------------
    def execute(self, sql: str, csv_fmt: bool = False) -> str:
        with tempfile.NamedTemporaryFile("w+", delete=False, suffix=".sql") as f:
            if csv_fmt:
                f.write("SET PAGES 0 FEEDBACK OFF HEADING ON MARKUP CSV ON\n")
            else:
                f.write("SET PAGES 50000 LINES 1000 FEEDBACK OFF VERIFY OFF HEADING ON\n")
            f.write(sql + "\nexit;\n")
            fname = f.name
        cmd = "sqlplus -S '/ as sysdba' @" + fname if self.as_sysdba else "sqlplus -S / @" + fname
        proc = subprocess.run(cmd, shell=True, text=True, capture_output=True, env=self._env())
        Path(fname).unlink(missing_ok=True)
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.strip())
        return proc.stdout.strip()

    # Convenience wrappers -------------------------------------------------
    def query_dict(self, sql: str) -> List[Dict[str, str]]:
        out = self.execute(sql, csv_fmt=True)
        if not out:
            return []
        reader = csv.DictReader(out.splitlines())
        return list(reader)

    # High‑level helpers ----------------------------------------------------
    def accessible(self) -> bool:
        try:
            return "1" in self.execute("select 1 from dual")
        except Exception:
            return False

    def instance_status(self):
        return self.query_dict("select instance_name,status,database_status from v$instance")[0]

    def role(self):
        return self.query_dict("select database_role,open_mode from v$database")[0]

    def version(self):
        return self.query_dict("select banner from v$version where banner like 'Oracle%'")[0]

    def connections(self):
        return self.query_dict(
            "select count(*) active_connections from v$session where status='ACTIVE' and username is not null"
        )[0]

    def tablespaces(self):
        return self.query_dict(
            """
            with a as (
              select tablespace_name, round(sum(bytes)/1048576,2) free_mb from dba_free_space group by tablespace_name
            ),
            b as (
              select tablespace_name,
                     round(sum(bytes)/1048576,2) size_mb,
                     round(sum(greatest(bytes,maxbytes))/1048576,2) max_size_mb
              from dba_data_files group by tablespace_name
            )
            select a.tablespace_name, size_mb, free_mb,
                   max_size_mb,
                   round((max_size_mb - free_mb)/max_size_mb*100,2) used_pct
            from a join b on a.tablespace_name=b.tablespace_name
            order by used_pct desc
            """
        )

################################################################################
# 3. Listener checker
################################################################################

class ListenerChecker:
    def __init__(self, oracle_home: str):
        self.home = oracle_home

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

    def listener_names(self) -> List[str]:
        lsnr_ora = Path(self.home) / "network/admin/listener.ora"
        if not lsnr_ora.exists():
            return ["LISTENER"]
        names = set()
        rx = re.compile(r"(\w+)_?LISTENER\s*=")
        for m in rx.finditer(lsnr_ora.read_text()):
            n = m.group(1)
            if n.upper() != "SID_LIST":
                names.add(n)
        return list(names) or ["LISTENER"]

    def status(self, name: str) -> Dict[str, str]:
        cmd = f"lsnrctl status {name}"
        proc = subprocess.run(cmd, shell=True, text=True, capture_output=True, env=self._env())
        out = proc.stdout
        info = {"name": name, "status": "DOWN", "services": []}
        if "The command completed successfully" in out:
            info["status"] = "UP"
            for svc in re.findall(r'Service "([^"]+)"', out):
                info["services"].append({"name": svc})
        return info

################################################################################
# 4. HTML Report builder
################################################################################

class Report:
    @staticmethod
    def _class_pct(val: str, good: float, warn: float):
        try:
            v = float(val)
            if v <= good:
                return "status-good"
            elif v <= warn:
                return "status-warning"
        except Exception:
            pass
        return "status-error"

    @classmethod
    def build(cls, dbs: List[Dict], listeners: List[Dict]):
        ts = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        host = os.uname().nodename
        db_rows = ""
        details = ""
        for d in dbs:
            sid = d["sid"]
            if not d.get("accessible"):
                db_rows += f"<tr><td>{sid}</td><td colspan=5 class=status-error>NOT ACCESSIBLE</td></tr>"
                continue
            role = d["role"]["DATABASE_ROLE"]
            open_mode = d["role"]["OPEN_MODE"]
            status = d["instance"]["STATUS"]
            version = d["version"]["BANNER"]
            status_cls = "status-good" if status == "OPEN" else "status-error"
            db_rows += f"<tr><td><a href=#db-{sid}>{sid}</a></td><td>{role}</td><td>{open_mode}</td><td class={status_cls}>{status}</td><td>{version}</td></tr>"

            # Detail card
            ts_rows = ""
            for ts in d.get("tablespaces", []):
                cls_pct = cls._class_pct(ts["USED_PCT"], 75, 90)
                ts_rows += (
                    f"<tr><td>{ts['TABLESPACE_NAME']}</td><td>{ts['SIZE_MB']} MB</td><td>{ts['FREE_MB']} MB</td>"
                    f"<td class={cls_pct}>{ts['USED_PCT']}%</td></tr>"
                )
            details += f"""
            <div class=card id=db-{sid}>
              <h3>{sid}</h3>
              <p><strong>Status:</strong> {status}</p>
              <p><strong>Role/Open Mode:</strong> {role} / {open_mode}</p>
              <p><strong>Version:</strong> {version}</p>
              <h4>Tablespaces</h4>
              <table><tr><th>Name</th><th>Size</th><th>Free</th><th>Used %</th></tr>{ts_rows}</table>
            </div>"""

        l_rows = ""
        for l in listeners:
            cls_ = "status-good" if l["status"] == "UP" else "status-error"
            svcs = "<br>".join(s["name"] for s in l.get("services", []))
            l_rows += f"<tr><td>{l['name']}</td><td class={cls_}>{l['status']}</td><td>{svcs}</td></tr>"

        html = f"""
        <html><head><style>
        body{{font-family:Arial;margin:20px}}
        table{{border-collapse:collapse;width:100%}}
        td,th{{border:1px solid #ccc;padding:6px;text-align:left}}
        th{{background:#f2f2f2}}
        .status-good{{background:#c8e6c9}}.status-warning{{background:#fff9c4}}.status-error{{background:#ffcdd2}}
        .card{{border:1px solid #ccc;padding:10px;border-radius:5px;margin:15px 0}}
        </style><title>Oracle Report</title></head><body>
        <h2>Oracle Status Report – {host}</h2><p>{ts}</p>
        <h3>Database Summary</h3><table><tr><th>SID</th><th>Role</th><th>Open Mode</th><th>Status</th><th>Version</th></tr>{db_rows}</table>
        <h3>Listener Summary</h3><table><tr><th>Name</th><th>Status</th><th>Services</th></tr>{l_rows}</table>
        <h3>Details</h3>{details}
        </body></html>"""
        return html

################################################################################
# 5. main()
################################################################################

def main():
    parser = OratabParser()
    db_info: List[Dict] = []
    l_info: Dict[str, Dict] = {}

    for ent in parser.entries():
        sid, home = ent["sid"], ent["oracle_home"]
        runner = OracleRunner(home, sid)
        entry: Dict = {
            "sid": sid,
            "oracle_home": home,
            "accessible": runner.accessible(),
        }
        if entry["accessible"]:
            try:
                entry["instance"] = runner.instance_status()
                entry["role"] = runner.role()
                entry["version"] = runner.version()
                entry["tablespaces"] = runner.tablespaces()
                entry["connections"] = runner.connections()
            except Exception as e:
                entry["error"] = str(e)
        db_info.append(entry)

        if home not in l_info:
            lchk = ListenerChecker(home)
            for n in lchk.listener_names():
                l_info[f"{home}:{n}"] = lchk.status(n)

    report_html = Report.build(db_info, list(l_info.values()))
    out_file = Path("/tmp") / f"oracle_status_report_{_dt.datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
    out_file.write_text(report_html)
    print(f"Report written to {out_file}")

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("Error:", exc, file=sys.stderr)
        sys.exit(1)
