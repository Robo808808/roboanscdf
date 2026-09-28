use axum::{
    extract::State,
    http::{HeaderMap, StatusCode},
    routing::get,
    Json, Router,
};
use regex::Regex;
use serde::Serialize;
use std::{env, process::Command, sync::Arc};

// 1. App configuration state, populated from env vars on start
struct AppConfig {
    api_key: String,
    sys_password: String,
    oracle_home: String,
}

#[derive(Serialize)]
struct ApiResponse {
    status: String,
    message: String,
    detail: String,
}

#[tokio::main]
async fn main() {
    // Read parameters from environment (like your FastAPI setup)
    let config = Arc::new(AppConfig {
        api_key: env::var("API_KEY").expect("API_KEY environment variable is required"),
        sys_password: env::var("SYS_PASSWORD").expect("SYS_PASSWORD environment variable is required"),
        oracle_home: env::var("ORACLE_HOME").expect("ORACLE_HOME environment variable is required"),
    });

    // Verify TNS_ADMIN and ORACLE_SID are present just to fail early if missing
    let _ = env::var("TNS_ADMIN").expect("TNS_ADMIN environment variable is required");
    let _ = env::var("ORACLE_SID").expect("ORACLE_SID environment variable is required");

    let app = Router::new()
        .route("/status", get(get_status))
        .route("/switchover", get(execute_switchover))
        .with_state(config); // Shares our secure parameters across all async endpoints

    // Bind to an unprivileged port suitable for non-root execution
    let listener = tokio::net::TcpListener::bind("0.0.0.0:8080").await.unwrap();
    println!("DataGuard automation binary listening natively on port 8080...");
    axum::serve(listener, app).await.unwrap();
}

// 2. Security Middleware Guard Function
fn is_authorized(headers: &HeaderMap, expected_key: &str) -> bool {
    if let Some(auth_header) = headers.get("X-API-KEY") {
        if let Ok(key_str) = auth_header.to_str() {
            return key_str == expected_key;
        }
    }
    false
}

// Endpoint: GET /status
async fn get_status(
    headers: HeaderMap,
    State(config): State<Arc<AppConfig>>,
) -> (StatusCode, Json<ApiResponse>) {
    if !is_authorized(&headers, &config.api_key) {
        return (StatusCode::UNAUTHORIZED, Json(ApiResponse {
            status: "error".to_string(),
            message: "Unauthorized access".to_string(),
            detail: "Missing or invalid X-API-KEY header".to_string(),
        }));
    }

    // Call dgmgrl securely passing the local sys authentication string
    let dgmgrl_path = format!("{}/bin/dgmgrl", config.oracle_home);
    let cmd_output = Command::new(&dgmgrl_path)
        .args(["/ ", "show configuration;"])
        .output();

    match cmd_output {
        Ok(output) => {
            let stdout_str = String::from_utf8_lossy(&output.stdout).to_string();
            (StatusCode::OK, Json(ApiResponse {
                status: "success".to_string(),
                message: "DataGuard configuration retrieved successfully".to_string(),
                detail: stdout_str,
            }))
        }
        Err(e) => (StatusCode::INTERNAL_SERVER_ERROR, Json(ApiResponse {
            status: "error".to_string(),
            message: "Failed to execute dgmgrl utility".to_string(),
            detail: e.to_string(),
        })),
    }
}

// Endpoint: GET /switchover
async fn execute_switchover(
    headers: HeaderMap,
    State(config): State<Arc<AppConfig>>,
) -> (StatusCode, Json<ApiResponse>) {
    if !is_authorized(&headers, &config.api_key) {
        return (StatusCode::UNAUTHORIZED, Json(ApiResponse {
            status: "error".to_string(),
            message: "Unauthorized access".to_string(),
            detail: "Missing or invalid X-API-KEY header".to_string(),
        }));
    }

    let dgmgrl_path = format!("{}/bin/dgmgrl", config.oracle_home);

    // Step A: First run status check to dynamically parse out the Standby DG Identifier
    let check_output = Command::new(&dgmgrl_path).args(["/ ", "show configuration;"]).output();
    let standby_identifier = match check_output {
        Ok(out) => {
            let text = String::from_utf8_lossy(&out.stdout);
            // Quick regex pattern searching for common Broker output formats identifying standbys
            let re = Regex::new(r"(?i)(\S+)\s+-\s+Physical standby database").unwrap();
            if let Some(caps) = re.captures(&text) {
                caps.get(1).map(|m| m.as_str().to_string())
            } else {
                None
            }
        }
        Err(_) => None,
    };

    let target_db = match standby_identifier {
        Some(db) => db,
        None => {
            return (StatusCode::BAD_REQUEST, Json(ApiResponse {
                status: "failed".to_string(),
                message: "Switchover aborted".to_string(),
                detail: "Could not automatically determine standalone Standby connect identifier from dgmgrl output.".to_string(),
            }));
        }
    };

    // Step B: Authenticate dynamically using password directly into dgmgrl to safely trigger target remount
    let connect_string = format!("sys/{}@{}", config.sys_password, target_db);
    let switch_command = format!("switchover to {};", target_db);

    let final_output = Command::new(&dgmgrl_path)
        .args([&connect_string, &switch_command])
        .output();

    match final_output {
        Ok(output) => {
            let raw_log = String::from_utf8_lossy(&output.stdout).to_string();
            if raw_log.contains("Successful") || raw_log.contains("completed") {
                (StatusCode::OK, Json(ApiResponse {
                    status: "success".to_string(),
                    message: format!("Database switchover to {} completed successfully.", target_db),
                    detail: raw_log,
                }))
            } else {
                (StatusCode::INTERNAL_SERVER_ERROR, Json(ApiResponse {
                    status: "failed".to_string(),
                    message: "DataGuard dgmgrl script threw execution warning/errors.".to_string(),
                    detail: raw_log,
                }))
            }
        }
        Err(e) => (StatusCode::INTERNAL_SERVER_ERROR, Json(ApiResponse {
            status: "error".to_string(),
            message: "Failed to invoke target switchover instruction".to_string(),
            detail: e.to_string(),
        })),
    }
}