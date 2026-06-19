use std::env;

#[derive(Clone, Debug)]
pub struct Config {
    pub mongodb_uri: String,
    pub mongodb_db_name: String,
    pub upload_dir: String,
    pub public_base_url: String,
    pub port: u16,
    /// Path to the Unix Domain Socket for the Python ML service.
    /// macOS dev default : /tmp/lms-ml.sock
    /// Linux production  : /run/lms/ml.sock
    pub ml_socket_path: String,
    /// Directory containing the Python ML service (serve.py + .venv/).
    /// Relative to the server's CWD, or absolute.
    pub ml_service_dir: String,
    /// When true the Rust server auto-starts and supervises the ML service.
    /// Set MANAGE_SERVICES=false on VPS where systemd owns the processes.
    pub manage_services: bool,
}

impl Config {
    pub fn from_env() -> anyhow::Result<Self> {
        let default_socket = if cfg!(target_os = "macos") {
            "/tmp/lms-ml.sock".into()
        } else {
            "/run/lms/ml.sock".into()
        };

        let manage_services = env::var("MANAGE_SERVICES")
            .map(|v| v != "false" && v != "0")
            .unwrap_or(true);

        Ok(Config {
            mongodb_uri: env::var("MONGODB_URI")
                .unwrap_or_else(|_| "mongodb://localhost:27017".into()),
            mongodb_db_name: env::var("MONGODB_DB").unwrap_or_else(|_| "lms".into()),
            upload_dir: env::var("UPLOAD_DIR").unwrap_or_else(|_| "./uploads".into()),
            public_base_url: env::var("PUBLIC_BASE_URL")
                .unwrap_or_else(|_| "http://localhost:3000".into()),
            port: env::var("PORT").unwrap_or_else(|_| "3000".into()).parse()?,
            ml_socket_path: env::var("ML_SOCKET_PATH").unwrap_or(default_socket),
            ml_service_dir: env::var("ML_SERVICE_DIR")
                .unwrap_or_else(|_| "../ml-service".into()),
            manage_services,
        })
    }
}
