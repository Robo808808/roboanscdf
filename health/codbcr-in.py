#!/usr/bin/env python3
"""
Consolidated Oracle DB Status Check - Checks all Oracle databases and listeners
defined in the oratab file and generates a consolidated HTML report.
"""

import os
import sys
import subprocess
import tempfile
import csv
import json
import datetime
import re
from pathlib import Path


class OratabParser:
    """Parse the oratab file to get Oracle SIDs and HOMEs"""

    def __init__(self, oratab_path=None):
        """Initialize with path to oratab file"""
        self.oratab_path = oratab_path or self._find_oratab()

    def _find_oratab(self):
        """Find the oratab file in common locations"""
        common_locations = [
            '/etc/oratab',
            '/var/opt/oracle/oratab',
            '/opt/oracle/oratab'
        ]

        for location in common_locations:
            if os.path.exists(location):
                return location

        return None

    def get_database_entries(self):
        """
        Parse oratab file to get database entries

        Returns:
            list: List of dictionaries with 'sid' and 'oracle_home' keys
        """
        if not self.oratab_path or not os.path.exists(self.oratab_path):
            print(f"Error: Could not find oratab file at {self.oratab_path}")
            return []

        entries = []

        try:
            with open(self.oratab_path, 'r') as file:
                for line in file:
                    # Skip comments and empty lines
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue

                    # Parse SID:ORACLE_HOME:startup_flag format
                    parts = line.split(':')
                    if len(parts) >= 2:
                        sid = parts[0]
                        oracle_home = parts[1]

                        # Skip ASM, APX, and other special entries
                        if sid.startswith('+') or sid.startswith('*'):
                            continue

                        entries.append({
                            'sid': sid,
                            'oracle_home': oracle_home
                        })

            return entries
        except Exception as e:
            print(f"Error reading oratab file: {e}")
            return []


class OracleRunner:
    """Execute Oracle SQLPlus commands from Python"""

    def __init__(self, oracle_home=None, oracle_sid=None, use_sysdba=True):
        """Initialize with Oracle environment details"""
        self.oracle_home = oracle_home or os.environ.get('ORACLE_HOME')
        self.oracle_sid = oracle_sid or os.environ.get('ORACLE_SID')
        self.use_sysdba = use_sysdba

        # Validate Oracle environment
        if not self.oracle_home:
            raise ValueError("ORACLE_HOME not set. Either pass it to the constructor or set it in environment.")

        if not self.oracle_sid:
            raise ValueError("ORACLE_SID not set. Either pass it to the constructor or set it in environment.")

    def execute_query(self, sql_query, formatting="default"):
        """
        Execute an Oracle SQL query via SQLPlus

        Args:
            sql_query (str): SQL query to execute
            formatting (str): Output format ('default', 'csv', 'json')

        Returns:
            str: Query results as formatted text
        """
        # Create temporary SQL file
        with tempfile.NamedTemporaryFile(mode='w+', suffix='.sql', delete=False) as sql_file:
            sql_path = sql_file.name

            # Prepare SQL formatting
            if formatting == "csv":
                sql_file.write("SET PAGESIZE 0\n")
                sql_file.write("SET FEEDBACK OFF\n")
                sql_file.write("SET HEADING ON\n")
                sql_file.write("SET MARKUP CSV ON\n")
            else:
                sql_file.write("SET PAGESIZE 50000\n")
                sql_file.write("SET LINESIZE 1000\n")
                sql_file.write("SET FEEDBACK OFF\n")
                sql_file.write("SET VERIFY OFF\n")
                sql_file.write("SET HEADING ON\n")

            # Add the main query
            sql_file.write(f"{sql_query}\n")
            sql_file.write("EXIT;\n")

        try:
            # Create environment with Oracle settings
            env = os.environ.copy()
            env["ORACLE_HOME"] = self.oracle_home
            env["ORACLE_SID"] = self.oracle_sid
            env["PATH"] = f"{self.oracle_home}/bin:{env.get('PATH', '')}"
            env["LD_LIBRARY_PATH"] = f"{self.oracle_home}/lib:{env.get('LD_LIBRARY_PATH', '')}"

            # Build the SQLPlus command correctly
            if self.use_sysdba:
                cmd = f"sqlplus -S '/ as sysdba' @{sql_path}"
            else:
                cmd = f"sqlplus -S '/' @{sql_path}"

            # Execute SQLPlus with the SQL file
            result = subprocess.run(
                cmd,
                shell=True,
                env=env,
                capture_output=True,
                text=True
            )

            output = result.stdout

            # Print any error for debugging
            if result.returncode != 0:
                print(f"SQLPlus Error for {self.oracle_sid}: {result.stderr}")

            # Convert to JSON if requested
            if formatting == "json" and output.strip():
                # Parse CSV output into JSON
                csv_reader = csv.DictReader(output.strip().split('\n'))
                json_data = [row for row in csv_reader]
                return json.dumps(json_data, indent=2)

            return output

        finally:
            # Clean up temporary SQL file
            if os.path.exists(sql_path):
                os.unlink(sql_path)

    def execute_query_as_dict(self, sql_query):
        """
        Execute a query and return results as a list of dictionaries

        Args:
            sql_query (str): SQL query to execute

        Returns:
            list: List of dictionaries representing rows
        """
        # First execute with CSV formatting
        csv_result = self.execute_query(sql_query, formatting="csv")

        if not csv_result.strip():
            return []

        # Parse CSV to get rows as dictionaries
        lines = csv_result.strip().split('\n')
        if len(lines) < 2:  # Just header or empty
            return []

        reader = csv.DictReader(lines)
        return list(reader)

    def execute_script(self, script_path):
        """
        Execute an Oracle SQL script via SQLPlus

        Args:
            script_path (str): Path to SQL script file

        Returns:
            str: Script execution results
        """
        if not os.path.exists(script_path):
            raise FileNotFoundError(f"SQL script not found: {script_path}")

        # Create environment with Oracle settings
        env = os.environ.copy()
        env["ORACLE_HOME"] = self.oracle_home
        env["ORACLE_SID"] = self.oracle_sid
        env["PATH"] = f"{self.oracle_home}/bin:{env.get('PATH', '')}"
        env["LD_LIBRARY_PATH"] = f"{self.oracle_home}/lib:{env.get('LD_LIBRARY_PATH', '')}"

        # Build the SQLPlus command correctly
        if self.use_sysdba:
            cmd = f"sqlplus -S '/ as sysdba' @{script_path}"
        else:
            cmd = f"sqlplus -S '/' @{script_path}"

        # Execute SQLPlus with the script file
        result = subprocess.run(
            cmd,
            shell=True,
            env=env,
            capture_output=True,
            text=True
        )

        # Print any error for debugging
        if result.returncode != 0:
            print(f"SQLPlus Error for {self.oracle_sid}: {result.stderr}")

        return result.stdout

    def is_database_accessible(self):
        """
        Verify if the database is accessible via SQLPlus

        Returns:
            bool: True if database is accessible, False otherwise
        """
        try:
            query = "SELECT 1 FROM dual;"
            result = self.execute_query(query)
            return "1" in result
        except Exception as e:
            print(f"Error connecting to database {self.oracle_sid}: {e}")
            return False

    def is_primary_or_standby(self):
        """
        Check if the database is primary or standby

        Returns:
            dict: Database role information
        """
        query = "SELECT database_role, open_mode FROM v$database;"
        results = self.execute_query_as_dict(query)

        if not results:
            return {"error": "No results returned"}

        return results[0]

    def get_instance_status(self):
        """
        Get database instance status

        Returns:
            dict: Instance status information
        """
        query = "SELECT instance_name, status, database_status FROM v$instance;"
        results = self.execute_query_as_dict(query)

        if not results:
            return {"error": "No results returned"}

        return results[0]

    def get_standby_apply_lag(self):
        """
        Check the standby apply lag if the database is in standby mode

        Returns:
            dict: Apply lag information
        """
        # First check if MRP is running
        mrp_query = """
        SELECT process, status, sequence# as sequence_number, 
               to_char(client_process) as client_process
        FROM v$managed_standby 
        WHERE process LIKE 'MRP%';
        """
        mrp_results = self.execute_query_as_dict(mrp_query)
        mrp_status = {"running": False, "status": "NOT RUNNING"}

        if mrp_results:
            mrp_status = {
                "running": True,
                "status": mrp_results[0].get("STATUS", "UNKNOWN"),
                "sequence": mrp_results[0].get("SEQUENCE_NUMBER", "UNKNOWN"),
                "client_process": mrp_results[0].get("CLIENT_PROCESS", "UNKNOWN")
            }

        # Get apply lag information
        lag_query = """
        SELECT ROUND((SYSDATE - SCN_TO_TIMESTAMP(CURRENT_SCN))*24*60,1) as lag_minutes
        FROM V$DATABASE;
        """
        lag_results = self.execute_query_as_dict(lag_query)
        lag_minutes = "UNKNOWN"

        if lag_results:
            try:
                lag_minutes = lag_results[0].get("LAG_MINUTES", "UNKNOWN")
            except:
                lag_minutes = "ERROR CALCULATING"

        # Get last applied archive log time
        last_applied_query = """
        SELECT to_char(MAX(COMPLETION_TIME), 'YYYY-MM-DD HH24:MI:SS') as last_applied_time
        FROM V$ARCHIVED_LOG
        WHERE APPLIED = 'YES';
        """
        last_applied_results = self.execute_query_as_dict(last_applied_query)
        last_applied_time = "UNKNOWN"

        if last_applied_results:
            last_applied_time = last_applied_results[0].get("LAST_APPLIED_TIME", "UNKNOWN")

        return {
            "mrp": mrp_status,
            "lag_minutes": lag_minutes,
            "last_applied": last_applied_time
        }

    def get_database_connections(self):
        """
        Get current database connection count

        Returns:
            dict: Connection information
        """
        query = """
        SELECT COUNT(*) as active_connections
        FROM v$session
        WHERE status = 'ACTIVE' AND username IS NOT NULL;
        """
        results = self.execute_query_as_dict(query)

        if not results:
            return {"active_connections": "UNKNOWN"}

        return results[0]

    def get_tablespaces_status(self):
        """
        Get tablespace usage information

        Returns:
            list: Tablespace usage information
        """
        query = """
        SELECT
            tablespace_name,
            size_mb,
            free_mb,
            max_size_mb,
            max_free_mb,
            ROUND((max_size_mb - max_free_mb) / max_size_mb * 100, 2) AS used_pct
        FROM (
            SELECT
                a.tablespace_name,
                b.size_mb,
                a.free_mb,
                b.max_size_mb,
                a.free_mb + (b.max_size_mb - b.size_mb) AS max_free_mb
            FROM
                (SELECT
                    tablespace_name,
                    ROUND(SUM(bytes) / 1048576, 2) AS free_mb
                 FROM dba_free_space
                 GROUP BY tablespace_name) a,
                (SELECT
                    tablespace_name,
                    ROUND(SUM(bytes) / 1048576, 2) AS size_mb,
                    ROUND(SUM(GREATEST(bytes, maxbytes)) / 1048576, 2) AS max_size_mb
                 FROM dba_data_files
                 GROUP BY tablespace_name) b
            WHERE a.tablespace_name = b.tablespace_name
        )
        ORDER BY used_pct DESC;
        """
        return self.execute_query_as_dict(query)

    def get_db_version(self):
        """Get Oracle database version"""
        query = "SELECT * FROM v$version WHERE banner LIKE 'Oracle%';"
        results = self.execute_query_as_dict(query)

        if not results:
            return {"version": "UNKNOWN"}

        return {"version": results[0].get("BANNER", "UNKNOWN")}


class ListenerChecker:
    """Check Oracle Net Listener status and services"""

    def __init__(self, oracle_home=None):
        """Initialize with Oracle environment details"""
        self.oracle_home = oracle_home or os.environ.get('ORACLE_HOME')

        # Validate Oracle environment
        if not self.oracle_home:
            raise ValueError("ORACLE_HOME not set. Either pass it to the constructor or set it in environment.")

    def _run_lsnrctl_command(self, listener_name, command):
        """
        Run lsnrctl command and capture output

        Args:
            listener_name (str): Name of the listener
            command (str): lsnrctl command to run

        Returns:
            str: Command output
        """
        # Create environment with Oracle settings
        env = os.environ.copy()
        env["ORACLE_HOME"] = self.oracle_home
        env["PATH"] = f"{self.oracle_home}/bin:{env.get('PATH', '')}"
        env["LD_LIBRARY_PATH"] = f"{self.oracle_home}/lib:{env.get('LD_LIBRARY_PATH', '')}"

        # Build the lsnrctl command
        if listener_name:
            cmd = f"lsnrctl {command} {listener_name}"
        else:
            cmd = f"lsnrctl {command}"

        # Execute lsnrctl command
        result = subprocess.run(
            cmd,
            shell=True,
            env=env,
            capture_output=True,
            text=True
        )

        return result.stdout

    def get_listeners_from_file(self):
        """
        Parse listener.ora to extract listener names

        Returns:
            list: List of listener names
        """
        listeners = []
        listener_ora_path = f"{self.oracle_home}/network/admin/listener.ora"

        if not os.path.exists(listener_ora_path):
            print(f"Warning: listener.ora not found at {listener_ora_path}")
            return ["LISTENER"]  # Default listener name

        try:
            with open(listener_ora_path, 'r') as file:
                content = file.read()

                # Use regex to find listener names
                # Pattern matches anything before _LISTENER= or just LISTENER=
                listener_patterns = [
                    r'(\w+)_LISTENER\s*=',  # Custom named listeners
                    r'(LISTENER)\s*='  # Default listener
                ]

                for pattern in listener_patterns:
                    matches = re.findall(pattern, content)
                    for m in matches:
                        if m.upper() != "SID_LIST":  # Filter out invalid
                            listeners.append(m)

                # Remove duplicates
                listeners = list(set(listeners))

                if not listeners:
                    listeners = ["LISTENER"]  # Default if none found

            return listeners
        except Exception as e:
            print(f"Error reading listener.ora: {e}")
            return ["LISTENER"]  # Default listener name

    def check_listener_status(self, listener_name):
        """
        Check status of an Oracle listener

        Args:
            listener_name (str): Name of the listener

        Returns:
            dict: Listener status information
        """
        status_output = self._run_lsnrctl_command(listener_name, "status")

        # Parse status output
        listener_info = {
            "name": listener_name,
            "status": "DOWN",
            "version": "Unknown",
            "start_date": "Unknown",
            "uptime": "Unknown",
            "services": [],
            "endpoints": []
        }

        if not status_output or "TNS-12541" in status_output:
            return listener_info

        # Parse version
        version_match = re.search(r'Version\s+([\d\.]+)', status_output)
        if version_match:
            listener_info["version"] = version_match.group(1)

        # Parse start date & uptime
        start_date_match = re.search(r'Start Date\s+(.+)', status_output)
        if start_date_match:
            listener_info["start_date"] = start_date_match.group(1).strip()

            # Calculate uptime if possible
            try:
                start_datetime = datetime.datetime.strptime(
                    listener_info["start_date"],
                    "%d-%b-%Y %H:%M:%S"
                )
                uptime = datetime.datetime.now() - start_datetime
                days = uptime.days
                hours, remainder = divmod(uptime.seconds, 3600)
                minutes, seconds = divmod(remainder, 60)
                listener_info["uptime"] = f"{days}d {hours}h {minutes}m {seconds}s"
            except:
                pass

        # Check if listener is running
        if "The command completed successfully" in status_output and "STATUS" in status_output.upper():
            listener_info["status"] = "UP"

        # Extract registered services
        services_section = re.search(r'Services Summary\.\.\.(.+?)The command completed successfully',
                                     status_output, re.DOTALL)

        if services_section:
            services_text = services_section.group(1)
            service_lines = services_text.strip().split('\n')

            for line in service_lines:
                line = line.strip()
                if "Service" in line and "has" in line:
                    parts = line.split('"')
                    if len(parts) >= 3:
                        service_name = parts[1]
                        instance_info = line.split("has")[1].strip()
                        listener_info["services"].append({
                            "name": service_name,
                            "instances": instance_info
                        })

        # Extract endpoints
        endpoints_section = re.search(r'Listening Endpoints Summary\.\.\.(.+?)Services Summary',
                                      status_output, re.DOTALL)

        if endpoints_section:
            endpoints_text = endpoints_section.group(1)
            endpoint_lines = endpoints_text.strip().split('\n')

            for line in endpoint_lines:
                line = line.strip()
                if line and "UNKNOWN" not in line:
                    listener_info["endpoints"].append(line)

        return listener_info

    def check_all_listeners(self):
        """
        Check status of all listeners defined in listener.ora

        Returns:
            list: List of listener status dictionaries
        """
        listeners = self.get_listeners_from_file()
        return [self.check_listener_status(listener) for listener in listeners]


class ConsolidatedHTMLReportGenerator:
    """Generate consolidated HTML reports for multiple Oracle databases"""

    @staticmethod
    def _get_open_mode_class(open_mode, is_primary):
        """Determine CSS class for open mode based on database role"""
        if is_primary:
            if open_mode in ["READ WRITE", "READ WRITE OPEN"]:
                return "status-good"
            else:
                return "status-error"
        else:
            if open_mode in ["READ ONLY", "READ ONLY WITH APPLY"]:
                return "status-good"
            else:
                return "status-error"

    @staticmethod
    def _get_lag_class(lag_minutes):
        """Determine CSS class for standby lag"""
        try:
            lag = float(lag_minutes)
            if lag <= 5:
                return "status-good"
            elif lag <= 30:
                return "status-warning"
            else:
                return "status-error"
        except (ValueError, TypeError):
            return "status-error"

    @staticmethod
    def _get_usage_class(used_pct):
        """Determine CSS class for tablespace usage percentage"""
        try:
            usage = float(used_pct)
            if usage < 75:
                return "status-good"
            elif usage < 90:
                return "status-warning"
            else:
                return "status-error"
        except (ValueError, TypeError):
            return "status-error"

@staticmethod
def generate_consolidated_report(all_db_info, all_listener_info=None):
    """
    Generate a consolidated HTML report for multiple databases

    Args:
        all_db_info (list): List of database information dictionaries
        all_listener_info (list): Optional list of listener information dictionaries

    Returns:
        str: HTML report content
    """
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    hostname = os.uname().nodename

    # Generate summary table for databases
    db_summary_rows = ""
    db_detail_sections = ""

    for db in all_db_info:
        sid = db.get("sid")
        if db.get("accessible") is False:
            db_summary_rows += f"""
            <tr>
                <td>{sid}</td>
                <td class="status-error">NOT ACCESSIBLE</td>
                <td>N/A</td>
                <td>N/A</td>
                <td>N/A</td>
                <td>N/A</td>
            </tr>
            """
            continue

        instance = db.get("instance", {})
        role = db.get("role", {})
        version = db.get("version", {}).get("version", "UNKNOWN")
        status = instance.get("STATUS", "UNKNOWN")
        open_mode = role.get("OPEN_MODE", "UNKNOWN")
        db_role = role.get("DATABASE_ROLE", "UNKNOWN")
        instance_name = instance.get("INSTANCE_NAME", sid)

        is_primary = db_role == "PRIMARY"
        status_class = "status-good" if status == "OPEN" else "status-error"
        open_mode_class = ConsolidatedHTMLReportGenerator._get_open_mode_class(open_mode, is_primary)

        # Lag display
        lag_display = "N/A"
        if not is_primary:
            lag_minutes = db.get("standby_info", {}).get("lag_minutes", "UNKNOWN")
            lag_class = ConsolidatedHTMLReportGenerator._get_lag_class(lag_minutes)
            lag_display = f'<span class="{lag_class}">{lag_minutes} min</span>'

        db_summary_rows += f"""
        <tr>
            <td><a href="#db-{sid}">{instance_name}</a></td>
            <td>{db_role}</td>
            <td class="{open_mode_class}">{open_mode}</td>
            <td class="{status_class}">{status}</td>
            <td>{lag_display}</td>
            <td>{version}</td>
        </tr>
        """

        # --- Database details section ---
        db_status = instance.get("DATABASE_STATUS", "UNKNOWN")
        db_status_class = "status-good" if db_status == "ACTIVE" else "status-error"

        # Standby info block
        standby_html = ""
        if not is_primary:
            standby_info = db.get("standby_info", {})
            mrp = standby_info.get("mrp", {})
            mrp_status = mrp.get("status", "UNKNOWN")
            mrp_class = "status-good" if mrp.get("running", False) else "status-error"
            lag = standby_info.get("lag_minutes", "UNKNOWN")
            lag_class = ConsolidatedHTMLReportGenerator._get_lag_class(lag)
            last_applied = standby_info.get("last_applied", "UNKNOWN")

            standby_html = f"""
            <div class="card">
                <h3>Standby Status</h3>
                <table>
                    <tr><th>MRP Status</th><td class="{mrp_class}">{mrp_status}</td></tr>
                    <tr><th>Apply Lag</th><td class="{lag_class}">{lag} minutes</td></tr>
                    <tr><th>Last Applied</th><td>{last_applied}</td></tr>
                </table>
            </div>
            """

        # Tablespaces
        tablespace_html = ""
        if "tablespaces" in db:
            rows = ""
            for ts in db["tablespaces"]:
                used_pct = ts.get("USED_PCT", "0")
                used_class = ConsolidatedHTMLReportGenerator._get_usage_class(used_pct)
                rows += f"""
                <tr>
                    <td>{ts.get("TABLESPACE_NAME", "UNKNOWN")}</td>
                    <td>{ts.get("SIZE_MB", "0")} MB</td>
                    <td>{ts.get("FREE_MB", "0")} MB</td>
                    <td class="{used_class}">{used_pct}%</td>
                </tr>
                """
            tablespace_html = f"""
            <div class="card">
                <h3>Tablespace Usage</h3>
                <table>
                    <tr><th>Name</th><th>Size</th><th>Free</th><th>Used %</th></tr>
                    {rows}
                </table>
            </div>
            """

        connections = db.get("connections", {}).get("active_connections", "UNKNOWN")

        db_detail_sections += f"""
        <div class="card full-width" id="db-{sid}">
            <h2>{sid} - Details</h2>
            <p><strong>Instance:</strong> {instance_name}</p>
            <p><strong>Status:</strong> <span class="{status_class}">{status}</span></p>
            <p><strong>Database Status:</strong> <span class="{db_status_class}">{db_status}</span></p>
            <p><strong>Role:</strong> {db_role}</p>
            <p><strong>Open Mode:</strong> {open_mode}</p>
            <p><strong>Version:</strong> {version}</p>
            <p><strong>Active Connections:</strong> {connections}</p>
            {standby_html}
            {tablespace_html}
        </div>
        """

    # --- Listener summary ---
    listener_summary_rows = ""
    if all_listener_info:
        for l in all_listener_info:
            for listener in l.get("listeners", []):
                status_class = "status-good" if listener.get("status") == "UP" else "status-error"
                services = "<br>".join(
                    [s.get("name", "") for s in listener.get("services", [])]
                )
                listener_summary_rows += f"""
                <tr>
                    <td><a href="#listener-{listener['name']}">{listener['name']}</a></td>
                    <td class="{status_class}">{listener['status']}</td>
                    <td>{services}</td>
                    <td>{l['oracle_home']}</td>
                </tr>
                """

    # --- Final HTML ---
    return f"""
    <html>
    <head>
        <title>Oracle Database Status Report</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 20px; }}
            table {{ border-collapse: collapse; width: 100%; }}
            th, td {{ border: 1px solid #ccc; padding: 8px; text-align: left; }}
            th {{ background-color: #f2f2f2; }}
            .status-good {{ background-color: #c8e6c9; }}
            .status-warning {{ background-color: #fff9c4; }}
            .status-error {{ background-color: #ffcdd2; }}
            .card {{ border: 1px solid #ccc; padding: 15px; margin-bottom: 20px; border-radius: 5px; }}
            .full-width {{ width: 100%; }}
        </style>
    </head>
    <body>
        <h1>Oracle Database Status Report</h1>
        <p><strong>Host:</strong> {hostname}</p>
        <p><strong>Generated At:</strong> {timestamp}</p>

        <h2>Database Summary</h2>
        <table>
            <tr>
                <th>SID</th><th>Role</th><th>Open Mode</th><th>Status</th><th>Lag</th><th>Version</th>
            </tr>
            {db_summary_rows}
        </table>

        <h2>Listener Summary</h2>
        <table>
            <tr>
                <th>Listener</th><th>Status</th><th>Services</th><th>ORACLE_HOME</th>
            </tr>
            {listener_summary_rows}
        </table>

        <hr>
        <h2>Database Details</h2>
        {db_detail_sections}
    </body>
    </html>
    """


def main():
    parser = OratabParser()
    db_entries = parser.get_database_entries()

    all_db_info = []
    listener_info_by_home = {}

    for entry in db_entries:
        sid = entry["sid"]
        oracle_home = entry["oracle_home"]
        db_info = {
            "sid": sid,
            "oracle_home": oracle_home
        }

        try:
            oracle = OracleRunner(oracle_home=oracle_home, oracle_sid=sid)
            if not oracle.is_database_accessible():
                db_info["accessible"] = False
                all_db_info.append(db_info)
                continue

            db_info["accessible"] = True
            db_info["instance"] = oracle.get_instance_status()
            db_info["role"] = oracle.is_primary_or_standby()
            db_info["version"] = oracle.get_db_version()
            db_info["connections"] = oracle.get_database_connections()
            db_info["tablespaces"] = oracle.get_tablespaces_status()

            if db_info["role"].get("DATABASE_ROLE") != "PRIMARY":
                db_info["standby_info"] = oracle.get_standby_apply_lag()

        except Exception as e:
            db_info["accessible"] = False
            db_info["error"] = str(e)

        all_db_info.append(db_info)

        # Listener checking (once per ORACLE_HOME)
        if oracle_home not in listener_info_by_home:
            listener_checker = ListenerChecker(oracle_home=oracle_home)
            listeners = listener_checker.check_all_listeners()
            print(f"[DEBUG] Listeners found for {oracle_home}: {[l['name'] for l in listeners]}")
            listener_info_by_home[oracle_home] = {
                "oracle_home": oracle_home,
                "listeners": listeners
            }

    # Generate HTML report
    report = ConsolidatedHTMLReportGenerator.generate_consolidated_report(
        all_db_info,
        list(listener_info_by_home.values())
    )

    # Write to output file
    output_path = f"/tmp/oracle_status_report_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
    with open(output_path, "w") as f:
        f.write(report)

    print(f"Report written to: {output_path}")

if __name__ == "__main__":
    main()
