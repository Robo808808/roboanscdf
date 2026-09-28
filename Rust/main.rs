use axum::{extract::State, http::{HeaderMap, StatusCode}, routing::{get, post}, Json, Router};
use regex::Regex;
use serde::Serialize;
use std::{env, path::PathBuf, sync::Arc, time::Duration};
use tokio::{io::AsyncWriteExt, process::Command, sync::Mutex, time::timeout};

struct AppConfig {
    api_key: String,
    sys_password: String,
    dgmgrl: PathBuf,
    transition: Mutex<()>,
}

#[derive(Serialize)]
struct DatabaseStatus {
    name: String,
    role: String,
    dg_connect_identifier: String,
    status: Option<String>,
    transport_lag: Option<String>,
    apply_lag: Option<String>,
}

#[derive(Serialize)]
struct DataGuardStatus {
    configuration_name: String,
    configuration_status: String,
    primary: DatabaseStatus,
    standbys: Vec<DatabaseStatus>,
}

#[derive(Serialize)]
struct ApiResponse {
    status: String,
    message: String,
    detail: String,
}

type ApiError = (StatusCode, Json<ApiResponse>);

fn error(code: StatusCode, message: &str, detail: impl Into<String>) -> ApiError {
    (code, Json(ApiResponse {
        status: "error".into(), message: message.into(), detail: detail.into(),
    }))
}

fn authorized(headers: &HeaderMap, key: &str) -> Result<(), ApiError> {
    if headers.get("X-API-KEY").and_then(|v| v.to_str().ok()) == Some(key) {
        Ok(())
    } else {
        Err(error(StatusCode::UNAUTHORIZED, "Unauthorized", "Missing or invalid X-API-KEY"))
    }
}

#[tokio::main]
async fn main() {
    let oracle_home = env::var("ORACLE_HOME").expect("ORACLE_HOME is required");
    let _ = env::var("ORACLE_SID").expect("ORACLE_SID is required");
    let _ = env::var("TNS_ADMIN").expect("TNS_ADMIN is required");
    let bind_address = env::var("BIND_ADDRESS").unwrap_or_else(|_| "127.0.0.1:8080".into());
    let config = Arc::new(AppConfig {
        api_key: env::var("API_KEY").expect("API_KEY is required"),
        sys_password: env::var("SYS_PASSWORD").expect("SYS_PASSWORD is required"),
        dgmgrl: PathBuf::from(oracle_home).join("bin/dgmgrl"),
        transition: Mutex::new(()),
    });
    let app = Router::new()
        .route("/status", get(get_status))
        .route("/switchover", post(execute_switchover))
        .with_state(config);
    let listener = tokio::net::TcpListener::bind(&bind_address).await.expect("bind failed");
    println!("Listening on {bind_address}");
    axum::serve(listener, app).await.expect("server failed");
}

// The script is sent over stdin. Credentials never become process arguments.
// DGMGRL may echo input or include connection information in output: never return
// or log raw output from a password-authenticated session.
async fn broker(config: &AppConfig, script: &str) -> Result<String, String> {
    let mut child = Command::new(&config.dgmgrl)
        .arg("-silent")
        .stdin(std::process::Stdio::piped())
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::piped())
        .kill_on_drop(true)
        .spawn().map_err(|e| format!("Could not start DGMGRL: {e}"))?;
    let mut stdin = child.stdin.take().ok_or("DGMGRL stdin unavailable")?;
    stdin.write_all(script.as_bytes()).await.map_err(|e| format!("DGMGRL input failed: {e}"))?;
    drop(stdin);
    let out = timeout(Duration::from_secs(300), child.wait_with_output())
        .await.map_err(|_| "DGMGRL timed out; inspect broker state before retrying".to_string())?
        .map_err(|e| format!("DGMGRL failed: {e}"))?;
    let text = format!("{}\n{}", String::from_utf8_lossy(&out.stdout), String::from_utf8_lossy(&out.stderr));
    if !out.status.success() || Regex::new(r"(?m)^\s*(?:ORA|DGM)-\d{5}:").unwrap().is_match(&text) {
        // Do not include text: it can contain a password supplied on stdin.
        return Err(format!("DGMGRL reported an error (exit status: {})", out.status));
    }
    Ok(text)
}

fn field(text: &str, label: &str) -> Option<String> {
    text.lines().find_map(|line| {
        let (key, value) = line.trim().split_once(':')?;
        if key.trim().eq_ignore_ascii_case(label) {
            Some(value.trim().to_string())
        } else { None }
    })
}

fn parse_configuration(text: &str) -> Result<(String, String, String, Vec<String>), String> {
    let config_name = Regex::new(r"(?im)^\s*Configuration\s+-\s*(\S+)").unwrap()
        .captures(text).map(|c| c[1].to_string()).ok_or("Configuration name missing")?;
    let status = field(text, "Configuration Status")
        .filter(|value| !value.is_empty())
        .or_else(|| {
            // DGMGRL normally prints the value beneath "Configuration Status:".
            // Skip blank lines, but stop before another section or prompt.
            let mut lines = text.lines();
            lines.find(|line| line.trim().eq_ignore_ascii_case("Configuration Status:"))?;
            lines.map(str::trim)
                .find(|line| !line.is_empty() && !line.starts_with("DGMGRL>"))
                .map(str::to_string)
        })
        .and_then(|value| value.split_whitespace().next().map(str::to_string))
        .ok_or("Configuration status missing")?;
    let member = Regex::new(r"(?i)^\s*([A-Za-z0-9_$#.-]+)\s+-\s+(Primary|Physical standby) database\b").unwrap();
    let mut primary = None;
    let mut standbys = Vec::new();
    for line in text.lines() {
        if let Some(c) = member.captures(line) {
            if c[2].eq_ignore_ascii_case("Primary") { primary = Some(c[1].to_string()); }
            else { standbys.push(c[1].to_string()); }
        }
    }
    let primary = primary.ok_or("Primary missing")?;
    Ok((config_name, status, primary, standbys))
}

fn parse_database(name: &str, text: &str) -> Result<DatabaseStatus, String> {
    let property = Regex::new(r"(?im)^\s*DGConnectIdentifier\s*=\s*'([^']+)'\s*$").unwrap();
    let dg_connect_identifier = property.captures(text).map(|c| c[1].to_string())
        .ok_or_else(|| format!("DGConnectIdentifier missing for {name}"))?;
    let role = field(text, "Role").ok_or_else(|| format!("Role missing for {name}"))?;
    Ok(DatabaseStatus {
        name: name.into(), role, dg_connect_identifier,
        status: field(text, "Database Status"),
        transport_lag: field(text, "Transport Lag"),
        apply_lag: field(text, "Apply Lag"),
    })
}

async fn inspect(config: &AppConfig) -> Result<DataGuardStatus, String> {
    // Local OS authentication is used only to discover broker members and status.
    let overview = broker(config, "connect /\nshow configuration;\nexit;\n").await?;
    let (configuration_name, configuration_status, primary_name, standby_names) = parse_configuration(&overview)?;
    let mut names = vec![primary_name.clone()];
    names.extend(standby_names);
    let mut databases = Vec::new();
    for name in names {
        // Names came from the broker listing and are restricted to safe characters.
        let output = broker(config, &format!("connect /\nshow database verbose '{name}';\nexit;\n")).await?;
        databases.push(parse_database(&name, &output)?);
    }
    let primary = databases.remove(0);
    if !primary.role.eq_ignore_ascii_case("PRIMARY") {
        return Err("Broker primary role does not match the configuration listing".into());
    }
    Ok(DataGuardStatus { configuration_name, configuration_status, primary, standbys: databases })
}

async fn get_status(headers: HeaderMap, State(config): State<Arc<AppConfig>>)
    -> Result<Json<DataGuardStatus>, ApiError>
{
    authorized(&headers, &config.api_key)?;
    inspect(&config).await.map(Json)
        .map_err(|e| error(StatusCode::BAD_GATEWAY, "Broker status unavailable", e))
}

async fn execute_switchover(headers: HeaderMap, State(config): State<Arc<AppConfig>>)
    -> Result<Json<ApiResponse>, ApiError>
{
    authorized(&headers, &config.api_key)?;
    let _guard = config.transition.try_lock().map_err(|_| error(
        StatusCode::CONFLICT, "Switchover already in progress", "Try again after it completes"))?;
    let before = inspect(&config).await.map_err(|e| error(StatusCode::BAD_GATEWAY, "Broker status unavailable", e))?;
    if before.configuration_status != "SUCCESS" {
        return Err(error(StatusCode::CONFLICT, "Configuration is not healthy", before.configuration_status));
    }
    if before.standbys.len() != 1 {
        return Err(error(StatusCode::CONFLICT, "Target is ambiguous",
            "Exactly one physical standby is required for automatic selection"));
    }
    let target = &before.standbys[0];
    if !target.role.eq_ignore_ascii_case("PHYSICAL STANDBY") {
        return Err(error(StatusCode::CONFLICT, "Target is not a physical standby", &target.role));
    }
    // Connect to the discovered standby with SYS password authentication. The
    // DGConnectIdentifier is an Oracle Net address; SWITCHOVER TO takes the broker name.
    let connect = format!("connect sys/{}@{}\n", config.sys_password, target.dg_connect_identifier);
    let script = format!("{connect}validate database '{}';\nexit;\n", target.name);
    let validation = broker(&config, &script).await
        .map_err(|e| error(StatusCode::BAD_GATEWAY, "Validation failed", e))?;
    let ready = Regex::new(r"(?im)^\s*Ready for Switchover:\s*Yes\s*$").unwrap();
    if !ready.is_match(&validation) {
        return Err(error(StatusCode::CONFLICT, "Standby is not ready for switchover",
            "Check VALIDATE DATABASE in DGMGRL"));
    }
    let script = format!("{connect}switchover to '{}';\nexit;\n", target.name);
    // A role transition can complete even when DGMGRL reports a subsequent
    // ORA-/DGM- message. Never repeat the switchover based on that message.
    let command_result = broker(&config, &script).await;
    let mut changed_role = None;
    for attempt in 0..10 {
        if attempt > 0 { tokio::time::sleep(Duration::from_secs(2)).await; }
        if let Ok(after) = inspect(&config).await {
            if after.primary.name == target.name &&
                after.standbys.iter().any(|db| db.name == before.primary.name &&
                    db.role.eq_ignore_ascii_case("PHYSICAL STANDBY")) {
                if after.configuration_status == "SUCCESS" {
                    return Ok(Json(ApiResponse {
                        status: "success".into(),
                        message: format!("Switchover to {} completed", target.name),
                        detail: format!("{} is primary; configuration status is SUCCESS", target.name),
                    }));
                }
                changed_role = Some(after.configuration_status);
            }
        }
    }
    if let Some(configuration_status) = changed_role {
        return Ok(Json(ApiResponse {
            status: "warning".into(),
            message: format!("Switchover to {} completed; broker is not yet healthy", target.name),
            detail: format!("{} is primary and {} is standby; configuration status is {}. Check /status and broker diagnostics if it persists.",
                target.name, before.primary.name, configuration_status),
        }));
    }
    Err(error(StatusCode::BAD_GATEWAY, "Switchover outcome requires inspection",
        command_result.err().unwrap_or_else(||
            "Target is not yet confirmed as primary; inspect broker before another request".into())))
}
