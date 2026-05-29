use axum::{
    extract::{Path, Query, State},
    Json,
};
use bson::doc;
use chrono::Utc;
use futures_util::TryStreamExt;
use serde::Deserialize;

use crate::{
    error::{AppError, Result},
    models::quiz::{CreateQuiz, Quiz, UpdateQuiz},
    AppState,
};

// ── Helpers ───────────────────────────────────────────────────────────────────

fn col(state: &AppState) -> mongodb::Collection<Quiz> {
    state.db.collection("quizzes")
}

async fn find_by_id(state: &AppState, id: &str) -> Result<Option<Quiz>> {
    Ok(col(state).find_one(doc! { "id": id }).await?)
}

async fn require_by_id(state: &AppState, id: &str) -> Result<Quiz> {
    find_by_id(state, id)
        .await?
        .ok_or_else(|| AppError::NotFound("Quiz not found".into()))
}

/// Save the modified quiz back using replace_one, returns the updated struct.
async fn save(state: &AppState, mut quiz: Quiz) -> Result<Quiz> {
    quiz.updated_at = Utc::now();
    let result = col(state)
        .replace_one(doc! { "id": &quiz.id }, &quiz)
        .await?;
    if result.matched_count == 0 {
        return Err(AppError::NotFound("Quiz not found".into()));
    }
    Ok(quiz)
}

// ── Public (device key) ───────────────────────────────────────────────────────

/// GET /api/v1/quizzes — list published quizzes (metadata only, no questions).
pub async fn list_published(State(state): State<AppState>) -> Result<Json<Vec<serde_json::Value>>> {
    let quizzes: Vec<Quiz> = col(&state)
        .find(doc! { "is_published": true })
        .await?
        .try_collect()
        .await?;

    let summaries = quizzes
        .into_iter()
        .map(|q| {
            serde_json::json!({
                "id": q.id,
                "title": q.title,
                "description": q.description,
                "category": q.category,
                "time_limit": q.time_limit,
                "is_published": q.is_published,
                "question_count": q.questions.len(),
                "created_at": q.created_at,
                "updated_at": q.updated_at,
            })
        })
        .collect();

    Ok(Json(summaries))
}

#[derive(Deserialize)]
pub struct SyncQuery {
    pub since: Option<chrono::DateTime<Utc>>,
}

/// GET /api/v1/quizzes/:id — full quiz with embedded questions.
/// Supports ?since=<ISO datetime> for delta sync.
pub async fn get_quiz_with_questions(
    State(state): State<AppState>,
    Path(id): Path<String>,
    Query(q): Query<SyncQuery>,
) -> Result<Json<serde_json::Value>> {
    let mut quiz = require_by_id(&state, &id).await?;

    if !quiz.is_published {
        return Err(AppError::NotFound("Quiz not found".into()));
    }

    if let Some(since) = q.since {
        quiz.questions.retain(|q| q.created_at > since);
    }

    quiz.questions.sort_by_key(|q| q.position);

    let quiz_id = &quiz.id;
    let questions: Vec<serde_json::Value> = quiz.questions.iter().map(|q| {
        let options: Vec<serde_json::Value> = q.options.iter().map(|o| serde_json::json!({
            "id": o.id,
            "question_id": q.id,
            "label": o.label,
            "content": o.content,
            "score": o.score,
            "is_correct": o.is_correct,
        })).collect();
        serde_json::json!({
            "id": q.id,
            "quiz_id": quiz_id,
            "type": q.r#type,
            "content": q.content,
            "image_url": q.image_url,
            "explanation": q.explanation,
            "position": q.position,
            "options": options,
            "created_at": q.created_at,
        })
    }).collect();

    Ok(Json(serde_json::json!({
        "quiz": {
            "id": quiz.id,
            "title": quiz.title,
            "description": quiz.description,
            "category": quiz.category,
            "time_limit": quiz.time_limit,
            "is_published": quiz.is_published,
            "created_at": quiz.created_at,
            "updated_at": quiz.updated_at,
        },
        "questions": questions,
    })))
}

// ── Admin ─────────────────────────────────────────────────────────────────────

/// GET /api/v1/admin/quizzes — list all (including drafts), metadata only.
pub async fn admin_list(State(state): State<AppState>) -> Result<Json<Vec<serde_json::Value>>> {
    let quizzes: Vec<Quiz> = col(&state)
        .find(doc! {})
        .await?
        .try_collect()
        .await?;

    let summaries = quizzes
        .into_iter()
        .map(|q| {
            serde_json::json!({
                "id": q.id,
                "title": q.title,
                "description": q.description,
                "category": q.category,
                "time_limit": q.time_limit,
                "is_published": q.is_published,
                "question_count": q.questions.len(),
                "created_at": q.created_at,
                "updated_at": q.updated_at,
            })
        })
        .collect();

    Ok(Json(summaries))
}

/// GET /api/v1/admin/quizzes/:id — full quiz with questions (admin editor).
pub async fn admin_get(
    State(state): State<AppState>,
    Path(id): Path<String>,
) -> Result<Json<Quiz>> {
    let mut quiz = require_by_id(&state, &id).await?;
    quiz.questions.sort_by_key(|q| q.position);
    Ok(Json(quiz))
}

/// POST /api/v1/admin/quizzes
pub async fn admin_create(
    State(state): State<AppState>,
    Json(body): Json<CreateQuiz>,
) -> Result<Json<Quiz>> {
    validate_category(&body.category)?;
    let quiz = Quiz::new(body.title, body.description, body.category, body.time_limit);
    col(&state).insert_one(&quiz).await?;
    Ok(Json(quiz))
}

/// PUT /api/v1/admin/quizzes/:id
pub async fn admin_update(
    State(state): State<AppState>,
    Path(id): Path<String>,
    Json(body): Json<UpdateQuiz>,
) -> Result<Json<Quiz>> {
    if let Some(ref cat) = body.category {
        validate_category(cat)?;
    }
    let mut quiz = require_by_id(&state, &id).await?;
    if let Some(t) = body.title       { quiz.title = t; }
    if let Some(d) = body.description { quiz.description = Some(d); }
    if let Some(c) = body.category    { quiz.category = c; }
    if let Some(l) = body.time_limit  { quiz.time_limit = Some(l); }
    Ok(Json(save(&state, quiz).await?))
}

/// DELETE /api/v1/admin/quizzes/:id
pub async fn admin_delete(
    State(state): State<AppState>,
    Path(id): Path<String>,
) -> Result<Json<serde_json::Value>> {
    let result = col(&state)
        .delete_one(doc! { "id": &id })
        .await?;
    if result.deleted_count == 0 {
        return Err(AppError::NotFound("Quiz not found".into()));
    }
    Ok(Json(serde_json::json!({ "deleted": id })))
}

/// POST /api/v1/admin/quizzes/:id/publish — toggle published flag.
pub async fn admin_toggle_publish(
    State(state): State<AppState>,
    Path(id): Path<String>,
) -> Result<Json<Quiz>> {
    let mut quiz = require_by_id(&state, &id).await?;
    quiz.is_published = !quiz.is_published;
    Ok(Json(save(&state, quiz).await?))
}

// ── Validation ────────────────────────────────────────────────────────────────

fn validate_category(cat: &str) -> Result<()> {
    match cat {
        "TWK" | "TIU" | "TKP" | "MIXED" => Ok(()),
        _ => Err(AppError::BadRequest(
            "category must be one of: TWK, TIU, TKP, MIXED".into(),
        )),
    }
}
