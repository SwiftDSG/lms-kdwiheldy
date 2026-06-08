//! Background supervisor that auto-starts Ollama and the Python ML service,
//! and restarts them if they crash.
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
    ollama_bin:  String,
    uvicorn_bin: PathBuf,
    serve_dir:   PathBuf,
    socket_path: String,
    ollama_proc: Arc<Mutex<Option<Child>>>,
    ml_proc:     Arc<Mutex<Option<Child>>>,
}

impl ServiceManager {
    pub fn new(config: &Config) -> Self {
        let ml_dir = std::fs::canonicalize(&config.ml_service_dir)
            .unwrap_or_else(|_| PathBuf::from(&config.ml_service_dir));
        ServiceManager {
            ollama_bin:  config.ollama_bin.clone(),
            uvicorn_bin: ml_dir.join(".venv/bin/uvicorn"),
            serve_dir:   ml_dir,
            socket_path: config.ml_socket_path.clone(),
            ollama_proc: Arc::new(Mutex::new(None)),
            ml_proc:     Arc::new(Mutex::new(None)),
        }
    }

    /// Check if Ollama is reachable, start it if not.
    async fn ensure_ollama(&self) {
        let mut guard = self.ollama_proc.lock().await;

        // If we own a child handle, see whether it has exited.
        if let Some(child) = guard.as_mut() {
            match child.try_wait() {
                Ok(Some(status)) => {
                    tracing::warn!("Ollama exited ({}); will restart", status);
                    *guard = None;
                }
                Ok(None) => {
                    // Still running — nothing to do.
                    return;
                }
                Err(e) => {
                    tracing::warn!("try_wait on Ollama child failed: {e}; assuming dead");
                    *guard = None;
                }
            }
        }

        // No managed child. Is an external Ollama already listening?
        if tokio::net::TcpStream::connect("127.0.0.1:11434").await.is_ok() {
            return; // External instance — leave it alone.
        }

        tracing::info!("Starting Ollama  bin={}", self.ollama_bin);
        match Command::new(&self.ollama_bin)
            .arg("serve")
            .spawn()
        {
            Ok(child) => {
                *guard = Some(child);
            }
            Err(e) => {
                tracing::error!("Failed to start Ollama: {e}");
            }
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
        match Command::new(&self.uvicorn_bin)
            .args(["serve:app", "--uds", &self.socket_path])
            .current_dir(&self.serve_dir)
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

    /// Start both services immediately (non-blocking — Axum starts while they init),
    /// then spawn a background loop that re-checks every 15 s.
    pub async fn start_and_watch(self: Arc<Self>) {
        // Initial start attempt (runs concurrently with Axum startup).
        self.ensure_ollama().await;
        self.ensure_ml_service().await;

        // Background watchdog.
        tokio::spawn(async move {
            loop {
                sleep(Duration::from_secs(15)).await;
                self.ensure_ollama().await;
                self.ensure_ml_service().await;
            }
        });
    }
}
