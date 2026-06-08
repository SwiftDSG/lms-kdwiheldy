use std::time::Duration;

use bytes::Bytes;
use http_body_util::{BodyExt, Full};
use hyper::Request;
use hyper_util::rt::TokioIo;
use serde::{Deserialize, Serialize};
use tokio::net::UnixStream;
use tracing::{info, warn};

// ── Types ─────────────────────────────────────────────────────────────────────

#[derive(Debug, Serialize)]
pub struct ExplainRequest {
    pub question:      String,
    pub options:       Vec<QuestionOption>,
    pub correct_label: String,
    pub subtype:       String,
}

#[derive(Debug, Serialize, Clone)]
pub struct QuestionOption {
    pub label:   String,
    pub content: String,
}

#[derive(Debug, Deserialize)]
pub struct ExplainResponse {
    pub explanation: String,
    pub tip:         String,
}

#[derive(Debug, Serialize)]
pub struct GenerateRequest {
    pub source_question:      String,
    pub source_options:       Vec<GenerateOption>,
    pub source_correct_label: String,
    pub category:             String,
    pub subtype:              String,
}

#[derive(Debug, Serialize)]
pub struct GenerateOption {
    pub label:   String,
    pub content: String,
    pub score:   i32,
}

#[derive(Debug, Deserialize, Serialize)]
pub struct GeneratedQuestion {
    pub content:     String,
    pub options:     Vec<GeneratedOptionResult>,
    pub explanation: String,
    pub tip:         String,
}

#[derive(Debug, Deserialize, Serialize)]
pub struct GeneratedOptionResult {
    pub label:   String,
    pub content: String,
    pub score:   i32,
}

#[derive(Debug, Deserialize, Serialize)]
pub struct AnalogiQuestion {
    pub content:     String,
    pub image_url:   String,
    pub explanation: String,
    pub options:     Vec<GeneratedOptionResult>,
}

// ── Client ────────────────────────────────────────────────────────────────────

/// HTTP/1.1 client that talks to the Python ML service via a Unix Domain Socket.
///
/// Each request opens a fresh connection — no pooling needed since requests
/// are infrequent and dominated by LLM latency (seconds), not connection
/// overhead (microseconds).
pub struct MlClient {
    socket_path: String,
}

impl MlClient {
    pub fn new(socket_path: impl Into<String>) -> Self {
        Self { socket_path: socket_path.into() }
    }

    /// Call `/explain` with exponential-backoff retry.
    ///
    /// Retry schedule (base = 200 ms):
    ///   attempt 0 → fail → wait 200 ms
    ///   attempt 1 → fail → wait 400 ms
    ///   attempt 2 → fail → wait 800 ms
    ///   attempt 3 → return Err (caller returns HTTP 503)
    pub async fn explain(
        &self,
        req: &ExplainRequest,
        max_retries: u32,
    ) -> anyhow::Result<ExplainResponse> {
        let body = serde_json::to_string(req)?;
        let base = Duration::from_millis(200);

        for attempt in 0..=max_retries {
            match self.try_once(&body).await {
                Ok(resp) => return Ok(resp),
                Err(e) => {
                    if attempt == max_retries {
                        return Err(e.context("ML service unavailable after retries"));
                    }
                    let delay = base * 2u32.pow(attempt);
                    warn!(
                        attempt = attempt + 1,
                        max = max_retries,
                        delay_ms = delay.as_millis(),
                        error = %e,
                        "ML request failed, retrying"
                    );
                    tokio::time::sleep(delay).await;
                }
            }
        }
        unreachable!()
    }

    /// Single HTTP POST over the UDS. Returns raw response bytes.
    async fn post_once(&self, path: &str, body: &str) -> anyhow::Result<Bytes> {
        let stream = UnixStream::connect(&self.socket_path).await.map_err(|e| {
            anyhow::anyhow!("Cannot connect to ML socket {}: {}", self.socket_path, e)
        })?;

        let (mut sender, conn) =
            hyper::client::conn::http1::handshake(TokioIo::new(stream)).await?;

        tokio::spawn(async move {
            if let Err(e) = conn.await {
                warn!("ML connection closed: {}", e);
            }
        });

        let req = Request::post(path)
            .header("content-type", "application/json")
            .header("host", "localhost")
            .body(Full::new(Bytes::from(body.to_owned())))?;

        let resp = sender.send_request(req).await?;

        if !resp.status().is_success() {
            let status = resp.status();
            let bytes = resp.collect().await?.to_bytes();
            anyhow::bail!("ML service {}: {}", status, String::from_utf8_lossy(&bytes));
        }

        Ok(resp.collect().await?.to_bytes())
    }

    async fn try_once(&self, body: &str) -> anyhow::Result<ExplainResponse> {
        let bytes = self.post_once("/explain", body).await?;
        Ok(serde_json::from_slice(&bytes)?)
    }

    /// Call `/generate` — no retry, single attempt (admin tool, failures surface as HTTP 500).
    pub async fn generate(&self, req: &GenerateRequest) -> anyhow::Result<GeneratedQuestion> {
        let body = serde_json::to_string(req)?;
        let bytes = self.post_once("/generate", &body).await?;
        Ok(serde_json::from_slice(&bytes)?)
    }

    /// Call `/analogi/generate` — LLM spec → render → upload → return question data (no DB save).
    pub async fn generate_analogi(&self) -> anyhow::Result<AnalogiQuestion> {
        let bytes = self.post_once("/analogi/generate", "{}").await?;
        Ok(serde_json::from_slice(&bytes)?)
    }
}

// ── Startup probe ─────────────────────────────────────────────────────────────

pub async fn probe_ml_service(socket_path: &str) {
    match UnixStream::connect(socket_path).await {
        Ok(_) => info!(socket = socket_path, "ML service reachable"),
        Err(e) => warn!(
            socket = socket_path,
            error = %e,
            "ML service not reachable — /explain will retry per-request"
        ),
    }
}
