use axum::{
    extract::{Path, Query, State},
    Json,
};
use bson::doc;
use chrono::Utc;
use futures_util::TryStreamExt;
use serde::Deserialize;
use uuid::Uuid;

use crate::{
    error::{AppError, Result},
    models::quiz::{
        BulkImport, CreateQuestion, Question, QuestionOption, Quiz, UpdateQuestion,
    },
    AppState,
};

fn col(state: &AppState) -> mongodb::Collection<Quiz> {
    state.db.collection("quizzes")
}

// ── Helpers ───────────────────────────────────────────────────────────────────

/// Find the quiz that embeds the given question id.
async fn quiz_containing(state: &AppState, question_id: &str) -> Result<Quiz> {
    col(state)
        .find_one(doc! { "questions.id": question_id })
        .await?
        .ok_or_else(|| AppError::NotFound("Question not found".into()))
}

fn make_options(body_opts: Option<&[crate::models::quiz::CreateOption]>) -> Vec<QuestionOption> {
    body_opts
        .unwrap_or_default()
        .iter()
        .map(|o| QuestionOption {
            id: Uuid::new_v4().to_string(),
            label: o.label.clone(),
            content: o.content.clone(),
            score: o.score,
        })
        .collect()
}

// ── Admin routes ──────────────────────────────────────────────────────────────

#[derive(Deserialize)]
pub struct QuestionFilter {
    pub quiz_id: Option<String>,
}

/// GET /api/v1/admin/questions?quiz_id=<uuid>
pub async fn admin_list(
    State(state): State<AppState>,
    Query(filter): Query<QuestionFilter>,
) -> Result<Json<Vec<serde_json::Value>>> {
    let quizzes: Vec<Quiz> = col(&state).find(doc! {}).await?.try_collect().await?;

    let questions: Vec<serde_json::Value> = quizzes
        .into_iter()
        .filter(|q| filter.quiz_id.as_ref().map_or(true, |id| &q.id == id))
        .flat_map(|q| {
            let quiz_id = q.id.clone();
            q.questions.into_iter().map(move |question| {
                serde_json::json!({
                    "id": question.id,
                    "quiz_id": quiz_id,
                    "type": question.r#type,
                    "subtype": question.subtype,
                    "content": question.content,
                    "image_url": question.image_url,
                    "explanation": question.explanation,
                    "position": question.position,
                    "options": question.options,
                    "created_at": question.created_at,
                })
            })
        })
        .collect();

    Ok(Json(questions))
}

/// GET /api/v1/admin/questions/:id — fetch a single question by its id.
pub async fn admin_get(
    State(state): State<AppState>,
    Path(question_id): Path<String>,
) -> Result<Json<serde_json::Value>> {
    let quiz = quiz_containing(&state, &question_id).await?;
    let q = quiz
        .questions
        .iter()
        .find(|q| q.id == question_id)
        .ok_or_else(|| AppError::NotFound("Question not found".into()))?;
    let quiz_id = &quiz.id;
    let options: Vec<serde_json::Value> = q.options.iter().map(|o| serde_json::json!({
        "id": o.id,
        "question_id": q.id,
        "label": o.label,
        "content": o.content,
        "score": o.score,
    })).collect();
    Ok(Json(serde_json::json!({
        "id": q.id,
        "quiz_id": quiz_id,
        "type": q.r#type,
        "subtype": q.subtype,
        "content": q.content,
        "image_url": q.image_url,
        "explanation": q.explanation,
        "position": q.position,
        "options": options,
        "created_at": q.created_at,
    })))
}

/// POST /api/v1/admin/questions — push a question into a quiz's embedded array.
pub async fn admin_create(
    State(state): State<AppState>,
    Json(body): Json<CreateQuestion>,
) -> Result<Json<serde_json::Value>> {
    validate_type(&body.r#type)?;

    let mut quiz: Quiz = col(&state)
        .find_one(doc! { "id": &body.quiz_id })
        .await?
        .ok_or_else(|| AppError::NotFound("Quiz not found".into()))?;

    let question = Question {
        id: Uuid::new_v4().to_string(),
        r#type: body.r#type.clone(),
        subtype: body.subtype.clone(),
        content: body.content.clone(),
        image_url: body.image_url.clone(),
        explanation: body.explanation.clone(),
        position: body.position,
        options: make_options(body.options.as_deref()),
        created_at: Utc::now(),
    };
    let q_id = question.id.clone();
    quiz.questions.push(question);
    quiz.updated_at = Utc::now();

    col(&state)
        .replace_one(doc! { "id": &quiz.id }, &quiz)
        .await?;

    let saved_q = quiz.questions.into_iter().find(|q| q.id == q_id).unwrap();
    Ok(Json(serde_json::json!({
        "quiz_id": body.quiz_id,
        "question": saved_q,
    })))
}

/// PUT /api/v1/admin/questions/:id — update fields of an embedded question.
pub async fn admin_update(
    State(state): State<AppState>,
    Path(question_id): Path<String>,
    Json(body): Json<UpdateQuestion>,
) -> Result<Json<serde_json::Value>> {
    if let Some(ref t) = body.r#type { validate_type(t)?; }

    let mut quiz = quiz_containing(&state, &question_id).await?;

    let q = quiz
        .questions
        .iter_mut()
        .find(|q| q.id == question_id)
        .ok_or_else(|| AppError::NotFound("Question not found".into()))?;

    if let Some(t) = body.r#type      { q.r#type = t; }
    if let Some(s) = body.subtype     { q.subtype = s; }
    if let Some(c) = body.content     { q.content = c; }
    if let Some(u) = body.image_url   { q.image_url = if u.is_empty() { None } else { Some(u) }; }
    if let Some(e) = body.explanation { q.explanation = if e.is_empty() { None } else { Some(e) }; }
    if let Some(p) = body.position    { q.position = p; }
    if let Some(opts) = body.options  { q.options = make_options(Some(&opts)); }

    let updated_q = q.clone();
    quiz.updated_at = Utc::now();

    col(&state)
        .replace_one(doc! { "id": &quiz.id }, &quiz)
        .await?;

    Ok(Json(serde_json::json!({ "question": updated_q })))
}

/// DELETE /api/v1/admin/questions/:id — remove question from embedded array.
pub async fn admin_delete(
    State(state): State<AppState>,
    Path(question_id): Path<String>,
) -> Result<Json<serde_json::Value>> {
    let mut quiz = quiz_containing(&state, &question_id).await?;
    quiz.questions.retain(|q| q.id != question_id);
    quiz.updated_at = Utc::now();
    col(&state)
        .replace_one(doc! { "id": &quiz.id }, &quiz)
        .await?;
    Ok(Json(serde_json::json!({ "deleted": question_id })))
}

/// POST /api/v1/admin/questions/bulk — create a new quiz with all questions at once.
pub async fn admin_bulk_import(
    State(state): State<AppState>,
    Json(body): Json<BulkImport>,
) -> Result<Json<serde_json::Value>> {
    validate_category(&body.quiz.category)?;

    let mut quiz = Quiz::new(
        body.quiz.title,
        body.quiz.description,
        body.quiz.category,
        body.quiz.time_limit,
    );

    for bq in &body.questions {
        validate_type(&bq.r#type)?;
        quiz.questions.push(Question {
            id: Uuid::new_v4().to_string(),
            r#type: bq.r#type.clone(),
            subtype: bq.subtype.clone(),
            content: bq.content.clone(),
            image_url: bq.image_url.clone(),
            explanation: bq.explanation.clone(),
            position: bq.position,
            options: make_options(bq.options.as_deref()),
            created_at: Utc::now(),
        });
    }

    let count = quiz.questions.len();
    let quiz_id = quiz.id.clone();
    col(&state).insert_one(&quiz).await?;

    Ok(Json(serde_json::json!({
        "quiz_id": quiz_id,
        "questions_imported": count,
    })))
}

/// GET /api/v1/questions/:id/explain — generate an in-depth AI explanation via RAG + Ollama.
pub async fn explain(
    State(state): State<AppState>,
    Path(question_id): Path<String>,
) -> Result<Json<serde_json::Value>> {
    let quiz = quiz_containing(&state, &question_id).await?;
    let q = quiz
        .questions
        .iter()
        .find(|q| q.id == question_id)
        .ok_or_else(|| AppError::NotFound("Question not found".into()))?;

    let subtype_str = serde_json::to_value(&q.subtype)
        .ok()
        .and_then(|v| v.as_str().map(|s| s.to_string()))
        .unwrap_or_default();

    let needs_ml = q.subtype.config().needs_ml_explain;
    tracing::info!(
        question_id = %question_id,
        subtype     = %subtype_str,
        needs_ml    = needs_ml,
        has_stored_explanation = q.explanation.is_some(),
        "── [explain] request received ─────────────────────────────────────────"
    );

    if !needs_ml {
        let stored = q.explanation.as_deref().unwrap_or("");
        tracing::info!(
            subtype  = %subtype_str,
            returned = %stored,
            "── [explain] short-circuit: returning stored explanation ───────────────"
        );
        return Ok(Json(serde_json::json!({
            "ai_explanation": stored,
            "ai_tip": "",
        })));
    }

    let req = crate::ml_client::ExplainRequest {
        question: q.content.clone(),
        options: q.options.iter().map(|o| crate::ml_client::QuestionOption {
            label:   o.label.clone(),
            content: o.content.clone(),
            score:   o.score,
        }).collect(),
        subtype: subtype_str,
    };

    let uds_body = serde_json::to_string(&req).unwrap_or_default();
    tracing::info!(
        question = %req.question,
        subtype  = %req.subtype,
        options  = ?req.options.iter().map(|o| format!("{}. {} (score={})", o.label, o.content, o.score)).collect::<Vec<_>>(),
        uds_json = %uds_body,
        "── [explain] sending to ML service via UDS ────────────────────────────"
    );

    let resp = state.ml.explain(&req, 3).await?;

    tracing::info!(
        explanation = %resp.explanation,
        tip         = %resp.tip,
        "── [explain] ML service response ──────────────────────────────────────"
    );

    Ok(Json(serde_json::json!({
        "ai_explanation": resp.explanation,
        "ai_tip": resp.tip,
    })))
}

/// POST /api/v1/admin/questions/generate — generate one question similar to a source question.
pub async fn admin_generate(
    State(state): State<AppState>,
    Json(body): Json<AdminGenerateBody>,
) -> Result<Json<serde_json::Value>> {
    let quiz = quiz_containing(&state, &body.source_question_id).await?;

    let source = quiz
        .questions
        .iter()
        .find(|q| q.id == body.source_question_id)
        .ok_or_else(|| AppError::NotFound("Source question not found".into()))?;

    let subtype_str = serde_json::to_value(&source.subtype)
        .ok()
        .and_then(|v| v.as_str().map(|s| s.to_string()))
        .unwrap_or_default();

    let req = crate::ml_client::GenerateRequest {
        source_question: source.content.clone(),
        source_options:  source.options.iter().map(|o| crate::ml_client::GenerateOption {
            label:   o.label.clone(),
            content: o.content.clone(),
            score:   o.score,
        }).collect(),
        category: quiz.category.clone(),
        subtype:  subtype_str,
    };

    let generated = state.ml.generate(&req).await?;
    Ok(Json(serde_json::json!({ "question": generated })))
}

/// POST /api/v1/admin/questions/generate/analogi — generate one analogi gambar question via ML pipeline.
pub async fn admin_generate_analogi(
    State(state): State<AppState>,
) -> Result<Json<serde_json::Value>> {
    let generated = state.ml.generate_analogi().await?;
    Ok(Json(serde_json::json!({ "question": generated })))
}

#[derive(serde::Deserialize)]
pub struct AdminGenerateBody {
    pub source_question_id: String,
}

// ── Validation ────────────────────────────────────────────────────────────────

fn validate_type(t: &str) -> Result<()> {
    match t {
        "MCQ" | "TRUE_FALSE" | "ESSAY" | "IMAGE" => Ok(()),
        _ => Err(AppError::BadRequest(
            "type must be one of: MCQ, TRUE_FALSE, ESSAY, IMAGE".into(),
        )),
    }
}

fn validate_category(cat: &str) -> Result<()> {
    match cat {
        "TWK" | "TIU" | "TKP" | "MIXED" => Ok(()),
        _ => Err(AppError::BadRequest(
            "category must be one of: TWK, TIU, TKP, MIXED".into(),
        )),
    }
}

// Subtype validation is handled at deserialization time by serde via QuestionSubtype enum.
