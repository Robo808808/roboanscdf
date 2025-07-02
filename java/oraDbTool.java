import java.io.*;
import java.sql.*;
import java.util.*;

public class OracleDbTool {

    private static class SqlStats {
        int successCount = 0;
        int failureCount = 0;
        long totalTimeMillis = 0;
    }

    public static void main(String[] args) {
        if (args.length < 1) {
            System.err.println("Usage: java OracleDbTool <path-to-db.properties>");
            return;
        }

        String propertiesPath = args[0];
        Properties props = new Properties();

        try (InputStream input = new FileInputStream(propertiesPath)) {
            props.load(input);
        } catch (IOException e) {
            System.err.println("Failed to load properties file: " + e.getMessage());
            return;
        }

        String url = props.getProperty("db.url");
        String user = props.getProperty("db.username");
        String password = props.getProperty("db.password");

        int execs = Integer.parseInt(props.getProperty("execs", "1"));
        int sleepSeconds = Integer.parseInt(props.getProperty("sleep", "0"));

        List<String> queryKeys = new ArrayList<>();
        Map<String, String> queryMap = new LinkedHashMap<>();

        for (String key : props.stringPropertyNames()) {
            if (key.toLowerCase().startsWith("sql")) {
                queryKeys.add(key);
                queryMap.put(key, props.getProperty(key));
            }
        }

        if (queryMap.isEmpty()) {
            System.err.println("No SQL queries defined. Exiting.");
            return;
        }

        Map<String, SqlStats> statsMap = new LinkedHashMap<>();

        try {
            Class.forName("oracle.jdbc.OracleDriver");
        } catch (ClassNotFoundException e) {
            System.err.println("Oracle JDBC driver not found.");
            return;
        }

        String serviceName = extractServiceName(url);
        String logFile = "logs/" + serviceName + ".log";
        new File("logs").mkdirs(); // ensure logs/ exists

        for (int i = 1; i <= execs; i++) {
            System.out.println("\n=== Execution " + i + " of " + execs + " ===");

            try (Connection conn = DriverManager.getConnection(url, user, password);
                 Statement stmt = conn.createStatement()) {

                for (String key : queryKeys) {
                    String sql = queryMap.get(key);
                    SqlStats stat = statsMap.computeIfAbsent(key, k -> new SqlStats());

                    System.out.println("Running: " + key + " → " + sql);
                    long start = System.currentTimeMillis();

                    StringBuilder logEntry = new StringBuilder();
                    logEntry.append("\n=== ").append(key)
                            .append(" | Execution ").append(i)
                            .append(" | ").append(new java.util.Date()).append(" ===\n");
                    logEntry.append("SQL: ").append(sql).append("\n");

                    try (ResultSet rs = stmt.executeQuery(sql)) {
                        ResultSetMetaData meta = rs.getMetaData();
                        int columnCount = meta.getColumnCount();

                        StringBuilder resultOutput = new StringBuilder();
                        for (int c = 1; c <= columnCount; c++) {
                            resultOutput.append(meta.getColumnName(c)).append(c == columnCount ? "\n" : ",");
                        }

                        while (rs.next()) {
                            for (int c = 1; c <= columnCount; c++) {
                                resultOutput.append(rs.getString(c)).append(c == columnCount ? "\n" : ",");
                            }
                        }

                        long elapsed = System.currentTimeMillis() - start;
                        stat.successCount++;
                        stat.totalTimeMillis += elapsed;

                        logEntry.append("Status: SUCCESS\n");
                        logEntry.append("Elapsed: ").append(elapsed).append(" ms\n");

                        if (stat.successCount == 1) {
                            logEntry.append("Output:\n").append(resultOutput);
                        }

                    } catch (SQLException sqle) {
                        stat.failureCount++;
                        logEntry.append("Status: FAILED\n");
                        logEntry.append("Error: ").append(sqle.getMessage()).append("\n");
                    }

                    logEntry.append("=== END OF EXECUTION ===\n");
                    appendToFile(logFile, logEntry.toString());
                }

            } catch (SQLException e) {
                System.err.println("DB connection failed: " + e.getMessage());
            }

            if (i < execs && sleepSeconds > 0) {
                try {
                    Thread.sleep(sleepSeconds * 1000L);
                } catch (InterruptedException ie) {
                    Thread.currentThread().interrupt();
                }
            }
        }

        // Summary
        System.out.println("\n==== Summary Report ====");
        System.out.printf("%-10s %-40s %-10s %-10s %-10s%n", "Key", "SQL", "Success", "Failure", "Avg(ms)");
        for (String key : queryKeys) {
            SqlStats s = statsMap.getOrDefault(key, new SqlStats());
            long avg = s.successCount > 0 ? s.totalTimeMillis / s.successCount : 0;
            System.out.printf("%-10s %-40s %-10d %-10d %-10d%n",
                    key,
                    truncate(queryMap.get(key), 38),
                    s.successCount,
                    s.failureCount,
                    avg);
        }
        System.out.println("=========================");
    }

    private static void appendToFile(String filename, String content) {
        try (FileWriter writer = new FileWriter(filename, true)) {
            writer.write(content);
        } catch (IOException e) {
            System.err.println("Failed to write to " + filename + ": " + e.getMessage());
        }
    }

    private static String truncate(String text, int length) {
        if (text.length() <= length) return text;
        return text.substring(0, length - 3) + "...";
    }

    private static String extractServiceName(String jdbcUrl) {
        if (jdbcUrl == null) return "unknown";
        int lastSlash = jdbcUrl.lastIndexOf('/');
        return (lastSlash >= 0 && lastSlash + 1 < jdbcUrl.length())
                ? jdbcUrl.substring(lastSlash + 1)
                : "unknown";
    }
}
