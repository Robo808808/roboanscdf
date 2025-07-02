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

        for (int i = 1; i <= execs; i++) {
            System.out.println("\n=== Execution " + i + " of " + execs + " ===");

            try (Connection conn = DriverManager.getConnection(url, user, password);
                 Statement stmt = conn.createStatement()) {

                for (String key : queryKeys) {
                    String sql = queryMap.get(key);
                    SqlStats stat = statsMap.computeIfAbsent(key, k -> new SqlStats());

                    System.out.println("Running: " + key + " → " + sql);
                    long start = System.currentTimeMillis();

                    try (ResultSet rs = stmt.executeQuery(sql)) {
                        while (rs.next()) {
                            // Consume result (no output)
                        }
                        long elapsed = System.currentTimeMillis() - start;
                        stat.successCount++;
                        stat.totalTimeMillis += elapsed;
                        System.out.println("Success (" + elapsed + " ms)");
                    } catch (SQLException sqle) {
                        stat.failureCount++;
                        System.err.println("Failed: " + sqle.getMessage());
                    }
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

    private static String truncate(String text, int length) {
        if (text.length() <= length) return text;
        return text.substring(0, length - 3) + "...";
    }
}
