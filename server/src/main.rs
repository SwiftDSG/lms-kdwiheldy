use axum::{
    routing::{delete, get, post, put},
    Router,
};
use mongodb::Client;
use std::sync::Arc;
use tower_http::{cors::CorsLayer, services::ServeDir, trace::TraceLayer};
use tracing_subscriber::{layer::SubscriberExt, util::SubscriberInitExt};

mod config;
mod error;
mod ml_client;
mod models;
mod routes;
mod service_manager;

use config::Config;
use ml_client::MlClient;

#[derive(Clone)]
pub struct AppState {
    pub db: mongodb::Database,
    pub config: Arc<Config>,
    pub ml: Arc<MlClient>,
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    dotenvy::dotenv().ok();

    tracing_subscriber::registry()
        .with(tracing_subscriber::EnvFilter::new(
            std::env::var("RUST_LOG").unwrap_or_else(|_| "info".into()),
        ))
        .with(tracing_subscriber::fmt::layer())
        .init();

    let config = Arc::new(Config::from_env()?);

    // Ensure upload directory exists
    tokio::fs::create_dir_all(&config.upload_dir).await?;

    // Connect to MongoDB
    let client = Client::with_uri_str(&config.mongodb_uri).await?;
    let db = client.database(&config.mongodb_db_name);
    tracing::info!("Connected to MongoDB: db={}", config.mongodb_db_name);

    // Auto-start Ollama + ML service (unless managed externally via systemd).
    if config.manage_services {
        Arc::new(service_manager::ServiceManager::new(&config))
            .start_and_watch()
            .await;
    }

    let ml = Arc::new(MlClient::new(&config.ml_socket_path));
    ml_client::probe_ml_service(&config.ml_socket_path).await;

    let state = AppState { db, config: config.clone(), ml };

    let app = Router::new()
        // Public
        .route("/api/v1/quizzes", get(routes::quizzes::list_published))
        .route("/api/v1/quizzes/{id}", get(routes::quizzes::get_quiz_with_questions))
        .route("/api/v1/sessions", post(routes::sessions::submit))
        // Admin — quizzes
        .route("/api/v1/admin/quizzes", get(routes::quizzes::admin_list))
        .route("/api/v1/admin/quizzes", post(routes::quizzes::admin_create))
        .route("/api/v1/admin/quizzes/{id}", get(routes::quizzes::admin_get))
        .route("/api/v1/admin/quizzes/{id}", put(routes::quizzes::admin_update))
        .route("/api/v1/admin/quizzes/{id}", delete(routes::quizzes::admin_delete))
        .route("/api/v1/admin/quizzes/{id}/publish", post(routes::quizzes::admin_toggle_publish))
        // Admin — questions
        .route("/api/v1/admin/questions", get(routes::questions::admin_list))
        .route("/api/v1/admin/questions", post(routes::questions::admin_create))
        .route("/api/v1/admin/questions/bulk", post(routes::questions::admin_bulk_import))
        .route("/api/v1/admin/questions/generate", post(routes::questions::admin_generate))
        .route("/api/v1/admin/questions/generate/analogi", post(routes::questions::admin_generate_analogi))
        .route("/api/v1/admin/questions/{id}", get(routes::questions::admin_get).put(routes::questions::admin_update).delete(routes::questions::admin_delete))
        // Public — AI explanation
        .route("/api/v1/questions/{id}/explain", get(routes::questions::explain))
        // Admin — upload & sessions
        .route("/api/v1/admin/upload/image", post(routes::upload::upload_image))
        .route("/api/v1/admin/sessions", get(routes::sessions::admin_list))
        .route("/api/v1/admin/sessions/{id}", get(routes::sessions::admin_get))
        // Static uploads
        .nest_service("/uploads", ServeDir::new(&config.upload_dir))
        .layer(CorsLayer::permissive())
        .layer(TraceLayer::new_for_http())
        .with_state(state);

    let addr = format!("0.0.0.0:{}", config.port);
    tracing::info!("Listening on {addr}");
    let listener = tokio::net::TcpListener::bind(&addr).await?;
    axum::serve(listener, app).await?;

    Ok(())
}
