use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use uuid::Uuid;

// ── Embedded sub-documents ────────────────────────────────────────────────────

/// Embedded inside a Question document.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct QuestionOption {
    pub id: String,
    pub label: String,      // "A"–"E" | "True" | "False"
    pub content: String,
    /// 0/5 for MCQ/TF (binary); 1–5 for TKP (weighted)
    pub score: i32,
    pub is_correct: bool,
}

/// Embedded inside a Quiz document.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Question {
    pub id: String,
    pub r#type: String,     // "MCQ" | "TRUE_FALSE" | "ESSAY" | "IMAGE"
    pub content: String,
    pub image_url: Option<String>,
    pub explanation: Option<String>,
    pub position: i32,
    pub options: Vec<QuestionOption>,
    pub created_at: DateTime<Utc>,
}

// ── Top-level collection document ─────────────────────────────────────────────

/// MongoDB document in the `quizzes` collection.
/// `id` is our application UUID string; MongoDB auto-manages `_id` (ObjectId).
/// Questions (and their options) are fully embedded.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Quiz {
    pub id: String,
    pub title: String,
    pub description: Option<String>,
    pub category: String,   // "TWK" | "TIU" | "TKP" | "MIXED"
    pub time_limit: Option<i32>,
    pub is_published: bool,
    pub questions: Vec<Question>,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
}

impl Quiz {
    pub fn new(
        title: String,
        description: Option<String>,
        category: String,
        time_limit: Option<i32>,
    ) -> Self {
        let now = Utc::now();
        Self {
            id: Uuid::new_v4().to_string(),
            title,
            description,
            category,
            time_limit,
            is_published: false,
            questions: vec![],
            created_at: now,
            updated_at: now,
        }
    }
}

// ── Request body types ────────────────────────────────────────────────────────

#[derive(Debug, Deserialize)]
pub struct CreateQuiz {
    pub title: String,
    pub description: Option<String>,
    pub category: String,
    pub time_limit: Option<i32>,
}

#[derive(Debug, Deserialize)]
pub struct UpdateQuiz {
    pub title: Option<String>,
    pub description: Option<String>,
    pub category: Option<String>,
    pub time_limit: Option<i32>,
}

#[derive(Debug, Deserialize)]
pub struct CreateOption {
    pub label: String,
    pub content: String,
    pub score: i32,
    pub is_correct: bool,
}

#[derive(Debug, Deserialize)]
pub struct CreateQuestion {
    pub quiz_id: String,
    pub r#type: String,
    pub content: String,
    pub image_url: Option<String>,
    pub explanation: Option<String>,
    pub position: i32,
    pub options: Option<Vec<CreateOption>>,
}

#[derive(Debug, Deserialize)]
pub struct UpdateQuestion {
    pub r#type: Option<String>,
    pub content: Option<String>,
    pub image_url: Option<String>,
    pub explanation: Option<String>,
    pub position: Option<i32>,
    pub options: Option<Vec<CreateOption>>,
}

/// Bulk import: one quiz + all questions in a single JSON payload.
#[derive(Debug, Deserialize)]
pub struct BulkImport {
    pub quiz: BulkQuizMeta,
    pub questions: Vec<BulkQuestion>,
}

#[derive(Debug, Deserialize)]
pub struct BulkQuizMeta {
    pub title: String,
    pub description: Option<String>,
    pub category: String,
    pub time_limit: Option<i32>,
}

#[derive(Debug, Deserialize)]
pub struct BulkQuestion {
    pub r#type: String,
    pub content: String,
    pub image_url: Option<String>,
    pub explanation: Option<String>,
    pub position: i32,
    pub options: Option<Vec<CreateOption>>,
}
