# Rust DG switchover app
A single executable that consumes parameters at startup, uses DG commands and returns structured JSON.
## Environment variables
SYS password, API key, and Oracle environment variables set in OS level.
## Installation
Create a new directory
initialize with cargo new dataguard-api
replace src/main.rs with the code.
## compile
cargo build --release --target x86_64-unknown-linux-musl
## Run
export API_KEY="secure-rest-token"
export SYS_PASSWORD="oracle_sys_password"
export ORACLE_HOME="/u01/app/oracle/product/19.x/dbhome_1"
export TNS_ADMIN="/u01/app/oracle/product/19.x/dbhome_1/network/admin"
export ORACLE_SID="SID"

./dataguard-api