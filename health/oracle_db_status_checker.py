#!/usr/bin/env python3
"""
Oracle DB Status Check - Checks if database is primary or standby, its status,
and generates an HTML report with the findings.
"""

import os
import sys
import subprocess
import tempfile
import csv
import json
import datetime
from pathlib import Path


class OracleRunner:
    """Execute Oracle SQLPlus commands from Python"""

    def __init__(self, oracle_home=None, oracle_sid=None, use_sysdba=False):
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
                print(f"SQLPlus Error: {result.stderr}")

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
            print(f"SQLPlus Error: {result.stderr}")

        return result.stdout

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


class HTMLReportGenerator:
    """Generate HTML reports for Oracle database status"""

    @staticmethod
    def generate_db_status_report(db_info):
        """
        Generate an HTML report with database status information

        Args:
            db_info (dict): Database information dictionary

        Returns:
            str: HTML report content
        """
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Extract information for the report
        instance_name = db_info.get("instance", {}).get("INSTANCE_NAME", "UNKNOWN")
        db_role = db_info.get("role", {}).get("DATABASE_ROLE", "UNKNOWN")
        db_open_mode = db_info.get("role", {}).get("OPEN_MODE", "UNKNOWN")
        instance_status = db_info.get("instance", {}).get("STATUS", "UNKNOWN")
        db_status = db_info.get("instance", {}).get("DATABASE_STATUS", "UNKNOWN")
        active_connections = db_info.get("connections", {}).get("ACTIVE_CONNECTIONS", "UNKNOWN")
        db_version = db_info.get("version", {}).get("version", "UNKNOWN")

        # Primary/Standby specific information
        is_primary = db_role == "PRIMARY"
        standby_info = ""

        if not is_primary:
            mrp_status = db_info.get("standby_info", {}).get("mrp", {}).get("status", "UNKNOWN")
            mrp_running = db_info.get("standby_info", {}).get("mrp", {}).get("running", False)
            lag_minutes = db_info.get("standby_info", {}).get("lag_minutes", "UNKNOWN")
            last_applied = db_info.get("standby_info", {}).get("last_applied", "UNKNOWN")

            standby_info = f"""
            <div class="card">
                <h3>Standby Status</h3>
                <table>
                    <tr>
                        <th>MRP Status</th>
                        <td class="{HTMLReportGenerator._get_status_class(mrp_running)}">
                            {mrp_status}
                        </td>
                    </tr>
                    <tr>
                        <th>Apply Lag (minutes)</th>
                        <td class="{HTMLReportGenerator._get_lag_class(lag_minutes)}">
                            {lag_minutes}
                        </td>
                    </tr>
                    <tr>
                        <th>Last Applied Time</th>
                        <td>{last_applied}</td>
                    </tr>
                </table>
            </div>
            """

        # Tablespace information
        tablespaces = db_info.get("tablespaces", [])
        tablespace_rows = ""

        for ts in tablespaces:
            tablespace_name = ts.get("TABLESPACE_NAME", "UNKNOWN")
            size_mb = ts.get("SIZE_MB", "0")
            free_mb = ts.get("FREE_MB", "0")
            used_pct = ts.get("USED_PCT", "0")

            # Determine color based on usage percentage
            used_class = HTMLReportGenerator._get_usage_class(used_pct)

            tablespace_rows += f"""
            <tr>
                <td>{tablespace_name}</td>
                <td>{size_mb} MB</td>
                <td>{free_mb} MB</td>
                <td class="{used_class}">{used_pct}%</td>
            </tr>
            """

        tablespace_table = f"""
        <div class="card">
            <h3>Tablespace Status</h3>
            <table>
                <tr>
                    <th>Tablespace Name</th>
                    <th>Size (MB)</th>
                    <th>Free (MB)</th>
                    <th>Used %</th>
                </tr>
                {tablespace_rows}
            </table>
        </div>
        """

        # Build the complete HTML report
        html_report = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Oracle Database Status Report - {instance_name}</title>
    <style>
        body {{
            font-family: Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f5f5f5;
        }}
        header {{
            background-color: #0e3b64;
            color: white;
            padding: 20px;
            margin-bottom: 20px;
            border-radius: 5px;
            box-shadow: 0 2px 5px rgba(0,0,0,0.1);
        }}
        h1, h2, h3 {{
            margin-top: 0;
        }}
        .container {{
            display: flex;
            flex-wrap: wrap;
            gap: 20px;
        }}
        .card {{
            background-color: white;
            border-radius: 5px;
            padding: 20px;
            box-shadow: 0 2px 5px rgba(0,0,0,0.1);
            flex: 1 1 300px;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-bottom: 20px;
        }}
        th, td {{
            padding: 10px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }}
        th {{
            background-color: #f2f2f2;
        }}
        .status-good {{
            color: green;
            font-weight: bold;
        }}
        .status-warn {{
            color: orange;
            font-weight: bold;
        }}
        .status-error {{
            color: red;
            font-weight: bold;
        }}
        .footer {{
            margin-top: 20px;
            text-align: center;
            font-size: 0.8em;
            color: #666;
        }}
    </style>
</head>
<body>
    <header>
        <h1>Oracle Database Status Report</h1>
        <p>Generated on: {timestamp}</p>
    </header>

    <div class="container">
        <div class="card">
            <h3>Database Information</h3>
            <table>
                <tr>
                    <th>Instance Name</th>
                    <td>{instance_name}</td>
                </tr>
                <tr>
                    <th>Database Role</th>
                    <td><strong>{db_role}</strong></td>
                </tr>
                <tr>
                    <th>Database Version</th>
                    <td>{db_version}</td>
                </tr>
                <tr>
                    <th>Open Mode</th>
                    <td class="{HTMLReportGenerator._get_open_mode_class(db_open_mode, is_primary)}">
                        {db_open_mode}
                    </td>
                </tr>
                <tr>
                    <th>Instance Status</th>
                    <td class="{HTMLReportGenerator._get_status_class(instance_status == 'OPEN')}">
                        {instance_status}
                    </td>
                </tr>
                <tr>
                    <th>Database Status</th>
                    <td class="{HTMLReportGenerator._get_status_class(db_status == 'ACTIVE')}">
                        {db_status}
                    </td>
                </tr>
                <tr>
                    <th>Active Connections</th>
                    <td>{active_connections}</td>
                </tr>
            </table>
        </div>

        {standby_info if not is_primary else ""}
    </div>

    {tablespace_table}

    <div class="footer">
        <p>Report generated using Oracle SQLPlus Integration</p>
    </div>
</body>
</html>
"""
        return html_report

    @staticmethod
    def _get_status_class(is_good):
        """Return CSS class based on status"""
        return "status-good" if is_good else "status-error"

    @staticmethod
    def _get_open_mode_class(open_mode, is_primary):
        """Return CSS class based on open mode and database role"""
        if is_primary and open_mode == "READ WRITE":
            return "status-good"
        elif not is_primary and open_mode == "MOUNTED":
            return "status-good"
        elif not is_primary and "READ ONLY" in open_mode:
            return "status-good"
        else:
            return "status-warn"

    @staticmethod
    def _get_lag_class(lag_minutes):
        """Return CSS class based on standby lag minutes"""
        try:
            lag = float(lag_minutes)
            if lag < 10:
                return "status-good"
            elif lag < 30:
                return "status-warn"
            else:
                return "status-error"
        except:
            return "status-warn"

    @staticmethod
    def _get_usage_class(used_pct):
        """Return CSS class based on usage percentage"""
        try:
            usage = float(used_pct)
            if usage < 70:
                return "status-good"
            elif usage < 90:
                return "status-warn"
            else:
                return "status-error"
        except:
            return "status-warn"


def generate_db_status_report(output_file=None):
    """
    Generate a database status report

    Args:
        output_file (str): Optional file path to save the report

    Returns:
        str: Path to the generated report file
    """
    # Get environment variables
    oracle_home = os.environ.get("ORACLE_HOME")
    oracle_sid = os.environ.get("ORACLE_SID")

    try:
        # Create Oracle runner with SYSDBA privileges
        oracle = OracleRunner(oracle_home, oracle_sid, use_sysdba=True)

        # Collect all necessary information
        db_info = {
            "role": oracle.is_primary_or_standby(),
            "instance": oracle.get_instance_status(),
            "connections": oracle.get_database_connections(),
            "version": oracle.get_db_version(),
            "tablespaces": oracle.get_tablespaces_status()
        }

        # Add standby-specific information if applicable
        if db_info["role"].get("DATABASE_ROLE") == "PHYSICAL STANDBY":
            db_info["standby_info"] = oracle.get_standby_apply_lag()

        # Generate HTML report
        report_html = HTMLReportGenerator.generate_db_status_report(db_info)

        # Determine output file path
        if not output_file:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            sid = oracle_sid or "UNKNOWN"
            output_file = f"oracle_status_{sid}_{timestamp}.html"

        # Write report to file
        with open(output_file, 'w') as f:
            f.write(report_html)

        print(f"Report generated successfully: {output_file}")
        return output_file

    except Exception as e:
        print(f"Error generating database status report: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    # Get output file path from command line if provided
    output_file = sys.argv[1] if len(sys.argv) > 1 else None

    # Generate report
    report_file = generate_db_status_report(output_file)

    print(f"Database status report saved to: {report_file}")
    print(f"Open the file in a web browser to view the report.")