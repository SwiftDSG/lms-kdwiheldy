use axum::{
    extract::{Path, State},
    Json,
};
use bson::doc;
use chrono::Utc;
use futures_util::TryStreamExt;

use crate::{
    error::{AppError, Result},
    models::{
        quiz::Quiz,
        session::{QuizSession, SessionAnswer, SubmitSession},
    },
    AppState,
};

fn col(state: &AppState) -> mongodb::Collection<QuizSession> {
    state.db.collection("quiz_sessions")
}

fn quiz_col(state: &AppState) -> mongodb::Collection<Quiz> {
    state.db.collection("quizzes")
}

/// POST /api/v1/sessions — submit a completed quiz session from the iPad app.
pub async fn submit(
    State(state): State<AppState>,
    Json(body): Json<SubmitSession>,
) -> Result<Json<serde_json::Value>> {
    // Idempotent — skip if session already exists (device retry)
    let existing = col(&state)
        .find_one(doc! { "id": &body.id })
        .await?;

    if existing.is_some() {
        return Ok(Json(serde_json::json!({
            "session_id": body.id,
            "score": existing.unwrap().score,
            "note": "already synced",
        })));
    }

    // Look up option scores from the quiz (embedded structure)
    let quiz = quiz_col(&state)
        .find_one(doc! { "id": &body.quiz_id })
        .await?;

    let mut total_score = 0i32;
    let mut answers: Vec<SessionAnswer> = Vec::new();

    for submitted in &body.answers {
        let points = if let (Some(q), Some(opt_id)) = (&quiz, &submitted.selected_option_id) {
            q.questions
                .iter()
                .find(|q| q.id == submitted.question_id)
                .and_then(|q| q.options.iter().find(|o| &o.id == opt_id))
                .map(|o| o.score)
                .unwrap_or(0)
        } else {
            0
        };
        total_score += points;

        answers.push(SessionAnswer {
            question_id: submitted.question_id.clone(),
            selected_option_id: submitted.selected_option_id.clone(),
            essay_text: submitted.essay_text.clone(),
            points_earned: points,
            answered_at: submitted.answered_at,
        });
    }

    let session = QuizSession {
        id: body.id.clone(),
        quiz_id: body.quiz_id,
        device_id: body.device_id,
        started_at: body.started_at,
        completed_at: body.completed_at,
        score: Some(total_score),
        answers,
        synced_at: Utc::now(),
    };

    col(&state).insert_one(&session).await?;

    Ok(Json(serde_json::json!({
        "session_id": body.id,
        "score": total_score,
    })))
}

/// GET /api/v1/admin/sessions — list sessions (most recent 200).
pub async fn admin_list(State(state): State<AppState>) -> Result<Json<Vec<serde_json::Value>>> {
    let sessions: Vec<QuizSession> = col(&state)
        .find(doc! {})
        .await?
        .try_collect()
        .await?;

    let summaries = sessions
        .into_iter()
        .map(|s| {
            serde_json::json!({
                "id": s.id,
                "quiz_id": s.quiz_id,
                "device_id": s.device_id,
                "score": s.score,
                "started_at": s.started_at,
                "completed_at": s.completed_at,
                "synced_at": s.synced_at,
            })
        })
        .collect();

    Ok(Json(summaries))
}

/// GET /api/v1/admin/sessions/:id — session detail with embedded answers.
pub async fn admin_get(
    State(state): State<AppState>,
    Path(id): Path<String>,
) -> Result<Json<QuizSession>> {
    col(&state)
        .find_one(doc! { "id": &id })
        .await?
        .ok_or_else(|| AppError::NotFound("Session not found".into()))
        .map(Json)
}
