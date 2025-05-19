#!/usr/bin/env python3
"""
Oracle Utilities - SQLPlus wrapper for Python

This module provides a Python interface to Oracle via SQLPlus command-line.
It doesn't require cx_Oracle or oracledb packages, just standard Python and SQLPlus.
"""

import os
import subprocess
import tempfile
import csv
import json


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

    def get_table_structure(self, table_name, schema=None):
        """
        Get table structure details

        Args:
            table_name (str): Name of the table
            schema (str): Optional schema name

        Returns:
            str: Table structure as text
        """
        full_table = f"{schema}.{table_name}" if schema else table_name
        query = f"DESCRIBE {full_table};"
        return self.execute_query(query)

    def get_tablespaces(self):
        """Get tablespace usage information"""
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
        return self.execute_query(query)

    def get_db_version(self):
        """Get Oracle database version"""
        return self.execute_query("SELECT * FROM v$version;")


if __name__ == "__main__":
    # Example usage
    import sys

    # Get environment variables from command line if provided
    oracle_home = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("ORACLE_HOME")
    oracle_sid = sys.argv[2] if len(sys.argv) > 2 else os.environ.get("ORACLE_SID")

    try:
        # Create the Oracle runner with SYSDBA privileges
        oracle = OracleRunner(oracle_home, oracle_sid, use_sysdba=True)

        # Run a simple test query
        print("Database Version:")
        print(oracle.get_db_version())

        print("\nTablespace Usage:")
        print(oracle.get_tablespaces())

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)