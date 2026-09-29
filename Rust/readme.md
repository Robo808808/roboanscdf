# Rust DG switchover app
A single executable that consumes parameters at startup, uses DG commands and returns structured JSON.
## Environment variables
SYS password, API key, and Oracle environment variables set in OS level.
## Install Rust as privileged user
### RHEL 9
sudo dnf install rust-toolset gcc  
### RHEL 8
sudo dnf module install rust-toolset  
sudo dnf install gcc  
rustc --version  
cargo --version  
## Rust as non-privileged user
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs -o rustup-init.sh  
sh rustup-init.sh  
. "$HOME/.cargo/env"
rustc --version  
cargo --version  
## Installation
Create a new directory  
initialize with cargo new dataguard-api  
replace src/main.rs with the code.  

dataguard-api/  
├── Cargo.toml  
└── src/  
    └── main.rs  

## compile
cd dataguard-api  
cargo build --release  
file target/release/dataguard-api  
ldd target/release/dataguard-api  
cargo build --release --target x86_64-unknown-linux-musl  

chmod u+x dataguard-api 
./dataguard-api --help  

## Run
export API_KEY="secure-rest-token"  
export SYS_PASSWORD="oracle_sys_password"  
export ORACLE_HOME="/u01/app/oracle/product/19.x/dbhome_1"  
export TNS_ADMIN="/u01/app/oracle/product/19.x/dbhome_1/network/admin"  
export ORACLE_SID="SID"  
export BIND_ADDRESS=10.20.30.40:8080  

cargo build --release  
./target/release/dataguard-api  

./dataguard-api  
