# STARTUP NOMOUNT to allow querying v$database
sqlplus -s / as sysdba <<EOF
STARTUP NOMOUNT;
EXIT;
EOF

if [ $? -ne 0 ]; then
  echo "[$ORACLE_SID] Failed to STARTUP NOMOUNT"
  exit 1
fi

# Query DB role
db_role=$(sqlplus -s / as sysdba <<EOF
set heading off feedback off pagesize 0 verify off
WHENEVER SQLERROR EXIT SQL.SQLCODE
SELECT database_role FROM v\\$database;
EXIT;
EOF
)

db_role=$(echo "$db_role" | tr -d '[:space:]' | tr '[:upper:]' '[:lower:]')

if [ "$db_role" == "physicalstandby" ]; then
  echo "[$ORACLE_SID] PHYSICAL STANDBY: issuing MOUNT only"
  sqlplus -s / as sysdba <<EOF
ALTER DATABASE MOUNT;
EXIT;
EOF
else
  echo "[$ORACLE_SID] PRIMARY or other role: full OPEN"
  sqlplus -s / as sysdba <<EOF
ALTER DATABASE MOUNT;
ALTER DATABASE OPEN;
EXIT;
EOF
fi
