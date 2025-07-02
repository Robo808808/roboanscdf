# Compile and run
javac -cp ojdbc8.jar OracleDbTool.java  
java -cp .:ojdbc8.jar OracleDbTool /path/to/db.properties  
# Example output
=== Execution 1 of 3 ===  
Running: sql1 → SELECT SYSDATE FROM DUAL  
Success (25 ms)  
Running: sql2 → SELECT banner FROM v$version  
Success (67 ms)  

=== Execution 2 of 3 ===  
...  

==== Summary Report ====  
Key        SQL                                      Success    Failure    Avg(ms)  
sql1       SELECT SYSDATE FROM DUAL                3          0          20  
sql2       SELECT banner FROM v$version            3          0          58  
=========================