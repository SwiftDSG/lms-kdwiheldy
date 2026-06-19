//! Background supervisor that auto-starts the Python ML service and restarts
//! it if it crashes.
//!
//! Wire-up in main.rs:
//!   if config.manage_services {
//!       Arc::new(ServiceManager::new(&config)).start_and_watch().await;
//!   }

use std::path::PathBuf;
use std::sync::Arc;
use tokio::process::{Child, Command};
use tokio::sync::Mutex;
use tokio::time::{sleep, Duration};

use crate::config::Config;

pub struct ServiceManager {
    python_bin:  PathBuf,
    serve_dir:   PathBuf,
    socket_path: String,
    ml_proc:     Arc<Mutex<Option<Child>>>,
}

impl ServiceManager {
    pub fn new(config: &Config) -> Self {
        let ml_dir = std::fs::canonicalize(&config.ml_service_dir)
            .unwrap_or_else(|_| PathBuf::from(&config.ml_service_dir));
        ServiceManager {
            python_bin:  ml_dir.join(".venv/bin/python"),
            serve_dir:   ml_dir,
            socket_path: config.ml_socket_path.clone(),
            ml_proc:     Arc::new(Mutex::new(None)),
        }
    }

    /// Check if the ML service is reachable via UDS, start it if not.
    async fn ensure_ml_service(&self) {
        let mut guard = self.ml_proc.lock().await;

        // Check whether our managed child has exited.
        if let Some(child) = guard.as_mut() {
            match child.try_wait() {
                Ok(Some(status)) => {
                    tracing::warn!("ML service exited ({}); will restart", status);
                    *guard = None;
                }
                Ok(None) => {
                    return; // Still running.
                }
                Err(e) => {
                    tracing::warn!("try_wait on ML service child failed: {e}; assuming dead");
                    *guard = None;
                }
            }
        }

        // No managed child. Is an external instance already listening?
        if tokio::net::UnixStream::connect(&self.socket_path).await.is_ok() {
            return; // External instance — leave it alone.
        }

        // Remove a stale socket file so uvicorn can bind.
        if let Err(e) = tokio::fs::remove_file(&self.socket_path).await {
            if e.kind() != std::io::ErrorKind::NotFound {
                tracing::warn!("Could not remove stale ML socket: {e}");
            }
        }

        tracing::info!(
            "Starting ML service  dir={} socket={}",
            self.serve_dir.display(),
            self.socket_path
        );
        match Command::new(&self.python_bin)
            .arg("serve.py")
            .current_dir(&self.serve_dir)
            .stdout(std::process::Stdio::inherit())
            .stderr(std::process::Stdio::inherit())
            .spawn()
        {
            Ok(child) => {
                *guard = Some(child);
            }
            Err(e) => {
                tracing::error!("Failed to start ML service: {e}");
            }
        }
    }

    /// Start the ML service immediately (non-blocking — Axum starts while it inits),
    /// then spawn a background loop that re-checks every 15 s.
    pub async fn start_and_watch(self: Arc<Self>) {
        self.ensure_ml_service().await;

        tokio::spawn(async move {
            loop {
                sleep(Duration::from_secs(15)).await;
                self.ensure_ml_service().await;
            }
        });
    }
}
