#!/usr/bin/env python3
import sys
import subprocess
import json
import os
import time
from datetime import datetime

# Import oracledb - will be available in the virtual environment
try:
    import oracledb
except ImportError:
    print(json.dumps({
        "status": "ERROR",
        "error": "oracledb module not found. Make sure it's installed in the virtual environment."
    }))
    sys.exit(1)


def get_db_role(sid, oracle_home):
    os.environ["ORACLE_HOME"] = oracle_home
    os.environ["ORACLE_SID"] = sid

    try:
        # Initialize oracle client
        try:
            oracledb.init_oracle_client(lib_dir=oracle_home + "/lib")
        except Exception as init_error:
            # If already initialized or other error, try to continue
            pass

        # Connect as SYSDBA
        conn = oracledb.connect(mode=oracledb.AUTH_MODE_SYSDBA)
        cursor = conn.cursor()

        # Check database role
        cursor.execute("SELECT DATABASE_ROLE FROM V$DATABASE")
        role = cursor.fetchone()[0]

        # Check if database is open
        cursor.execute("SELECT OPEN_MODE FROM V$DATABASE")
        open_mode = cursor.fetchone()[0]

        result = {
            "sid": sid,
            "oracle_home": oracle_home,
            "role": role,
            "open_mode": open_mode,
            "status": "UP",
            "error": None
        }

        # If it's a standby database, check MRP status and lag
        if role == "PHYSICAL STANDBY":
            try:
                # Check if MRP is running
                cursor.execute("SELECT COUNT(*) FROM V$MANAGED_STANDBY WHERE PROCESS LIKE 'MRP%'")
                mrp_count = cursor.fetchone()[0]
                result["mrp_running"] = (mrp_count > 0)

                # Check apply lag
                cursor.execute("""
                    SELECT NVL(ROUND((SYSDATE - MAX(COMPLETION_TIME)) * 24 * 60, 2), -1) AS lag_minutes
                    FROM V$ARCHIVED_LOG WHERE APPLIED = 'YES' AND COMPLETION_TIME IS NOT NULL
                """)
                lag_minutes = cursor.fetchone()[0]
                result["apply_lag_minutes"] = lag_minutes
            except Exception as e:
                result["mrp_error"] = str(e)

        # For primary, check active connections
        elif role == "PRIMARY":
            try:
                cursor.execute("SELECT COUNT(*) FROM V$SESSION WHERE TYPE = 'USER'")
                result["active_connections"] = cursor.fetchone()[0]
            except Exception as e:
                result["connection_error"] = str(e)

        cursor.close()
        conn.close()
        return result

    except oracledb.DatabaseError as e:
        error, = e.args
        return {
            "sid": sid,
            "oracle_home": oracle_home,
            "status": "DOWN",
            "error": str(error)
        }
    except Exception as e:
        return {
            "sid": sid,
            "oracle_home": oracle_home,
            "status": "DOWN",
            "error": str(e)
        }


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: check_oracle_db.py <SID> <ORACLE_HOME>")
        sys.exit(1)

    sid = sys.argv[1]
    oracle_home = sys.argv[2]

    result = get_db_role(sid, oracle_home)
    print(json.dumps(result))