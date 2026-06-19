use std::time::Duration;

use serde::{Deserialize, Serialize};
use tokio::io::{AsyncBufReadExt, AsyncReadExt, AsyncWriteExt, BufReader};
use tokio::net::UnixStream;
use tracing::{info, warn};

// ── Types ─────────────────────────────────────────────────────────────────────

#[derive(Debug, Serialize)]
pub struct ExplainRequest {
    pub question: String,
    pub options:  Vec<QuestionOption>,
    pub subtype:  String,
}

#[derive(Debug, Serialize, Clone)]
pub struct QuestionOption {
    pub label:   String,
    pub content: String,
    pub score:   i32,
}

#[derive(Debug, Deserialize)]
pub struct ExplainResponse {
    pub explanation: String,
    pub tip:         String,
}

#[derive(Debug, Serialize)]
pub struct GenerateRequest {
    pub source_question: String,
    pub source_options:  Vec<GenerateOption>,
    pub category:        String,
    pub subtype:         String,
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

pub struct MlClient {
    socket_path: String,
}

impl MlClient {
    pub fn new(socket_path: impl Into<String>) -> Self {
        Self { socket_path: socket_path.into() }
    }

    /// Send a request and read the response over the UDS.
    ///
    /// Protocol:
    ///   Request:  "<verb> <byte_len>\n<json_bytes>"
    ///   Response: "ok <byte_len>\n<json_bytes>"
    ///          or "error <byte_len>\n<message>"
    async fn send_recv(&self, verb: &str, body: &str) -> anyhow::Result<Vec<u8>> {
        let stream = UnixStream::connect(&self.socket_path).await.map_err(|e| {
            anyhow::anyhow!("Cannot connect to ML socket {}: {}", self.socket_path, e)
        })?;

        let (read_half, mut write_half) = stream.into_split();

        let payload = body.as_bytes();
        write_half.write_all(format!("{} {}\n", verb, payload.len()).as_bytes()).await?;
        write_half.write_all(payload).await?;
        // Keep write_half alive — dropping it sends EOF to the Python reader, which
        // the disconnect monitor would mistake for a client disconnect.

        let mut reader = BufReader::new(read_half);
        let mut header = String::new();
        reader.read_line(&mut header).await?;

        let header = header.trim();
        let (status, len_str) = header
            .split_once(' ')
            .ok_or_else(|| anyhow::anyhow!("Invalid ML response header: {:?}", header))?;
        let len: usize = len_str
            .parse()
            .map_err(|_| anyhow::anyhow!("Invalid ML response length: {:?}", len_str))?;

        let mut buf = vec![0u8; len];
        reader.read_exact(&mut buf).await?;

        if status == "error" {
            anyhow::bail!("ML service error: {}", String::from_utf8_lossy(&buf));
        }

        Ok(buf)
    }

    /// Call `explain` with exponential-backoff retry (200 / 400 / 800 ms).
    pub async fn explain(
        &self,
        req: &ExplainRequest,
        max_retries: u32,
    ) -> anyhow::Result<ExplainResponse> {
        let body = serde_json::to_string(req)?;
        let base = Duration::from_millis(200);

        for attempt in 0..=max_retries {
            match self.send_recv("explain", &body).await {
                Ok(bytes) => return Ok(serde_json::from_slice(&bytes)?),
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

    /// Call `generate` — single attempt (admin tool; failures surface as HTTP 500).
    pub async fn generate(&self, req: &GenerateRequest) -> anyhow::Result<GeneratedQuestion> {
        let body  = serde_json::to_string(req)?;
        let bytes = self.send_recv("generate", &body).await?;
        Ok(serde_json::from_slice(&bytes)?)
    }

    /// Call `analogi` — LLM spec → render → upload → return question data.
    pub async fn generate_analogi(&self) -> anyhow::Result<AnalogiQuestion> {
        let bytes = self.send_recv("analogi", "{}").await?;
        Ok(serde_json::from_slice(&bytes)?)
    }
}

// ── Startup probe ─────────────────────────────────────────────────────────────

pub async fn probe_ml_service(socket_path: &str) {
    match UnixStream::connect(socket_path).await {
        Ok(_)  => info!(socket = socket_path, "ML service reachable"),
        Err(e) => warn!(
            socket = socket_path,
            error  = %e,
            "ML service not reachable — /explain will retry per-request"
        ),
    }
}
