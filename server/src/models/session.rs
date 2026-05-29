use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use uuid::Uuid;

/// Embedded answer inside a QuizSession document.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SessionAnswer {
    pub question_id: String,
    pub selected_option_id: Option<String>,
    pub essay_text: Option<String>,
    pub points_earned: i32,
    pub answered_at: DateTime<Utc>,
}

/// MongoDB document in the `quiz_sessions` collection.
/// `id` is our application UUID string; MongoDB auto-manages `_id` (ObjectId).
/// Answers are fully embedded.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct QuizSession {
    pub id: String,             // generated on device
    pub quiz_id: String,
    pub device_id: String,      // anonymous device UUID
    pub started_at: DateTime<Utc>,
    pub completed_at: Option<DateTime<Utc>>,
    pub score: Option<i32>,
    pub answers: Vec<SessionAnswer>,
    pub synced_at: DateTime<Utc>,
}

// ── Request body types ────────────────────────────────────────────────────────

#[derive(Debug, Deserialize)]
pub struct SubmitSession {
    pub id: String,
    pub quiz_id: String,
    pub device_id: String,
    pub started_at: DateTime<Utc>,
    pub completed_at: Option<DateTime<Utc>>,
    pub answers: Vec<SubmitAnswer>,
}

#[derive(Debug, Deserialize)]
pub struct SubmitAnswer {
    pub question_id: String,
    pub selected_option_id: Option<String>,
    pub essay_text: Option<String>,
    pub answered_at: DateTime<Utc>,
}

impl SubmitSession {
    /// Generate a new server-side session ID if the client didn't supply one.
    pub fn ensure_id(mut self) -> Self {
        if self.id.is_empty() {
            self.id = Uuid::new_v4().to_string();
        }
        self
    }
}
