use axum::{
    extract::{Multipart, State},
    Json,
};
use std::path::Path;
use uuid::Uuid;

use crate::{error::{AppError, Result}, AppState};

/// POST /api/v1/admin/upload/image — upload a question image.
/// Returns the public URL to store in question.image_url.
pub async fn upload_image(
    State(state): State<AppState>,
    mut multipart: Multipart,
) -> Result<Json<serde_json::Value>> {
    while let Some(field) = multipart
        .next_field()
        .await
        .map_err(|e| AppError::BadRequest(e.to_string()))?
    {
        let content_type = field
            .content_type()
            .unwrap_or("application/octet-stream")
            .to_string();

        if !matches!(
            content_type.as_str(),
            "image/jpeg" | "image/png" | "image/gif" | "image/webp"
        ) {
            return Err(AppError::BadRequest("Only image files are accepted".into()));
        }

        let ext = match content_type.as_str() {
            "image/jpeg" => "jpg",
            "image/png" => "png",
            "image/gif" => "gif",
            "image/webp" => "webp",
            _ => "bin",
        };

        let filename = format!("{}.{}", Uuid::new_v4(), ext);
        let filepath = Path::new(&state.config.upload_dir).join(&filename);

        let data = field
            .bytes()
            .await
            .map_err(|e| AppError::BadRequest(e.to_string()))?;

        tokio::fs::write(&filepath, &data)
            .await
            .map_err(|e| AppError::Internal(anyhow::anyhow!("Write file: {e}")))?;

        let url = format!("{}/uploads/{}", state.config.public_base_url, filename);
        return Ok(Json(serde_json::json!({ "url": url })));
    }

    Err(AppError::BadRequest("No file provided".into()))
}
