use std::env;

#[derive(Clone, Debug)]
pub struct Config {
    pub mongodb_uri: String,
    pub mongodb_db_name: String,
    pub upload_dir: String,
    pub public_base_url: String,
    pub port: u16,
}

impl Config {
    pub fn from_env() -> anyhow::Result<Self> {
        Ok(Config {
            mongodb_uri: env::var("MONGODB_URI")
                .unwrap_or_else(|_| "mongodb://localhost:27017".into()),
            mongodb_db_name: env::var("MONGODB_DB").unwrap_or_else(|_| "lms".into()),
            upload_dir: env::var("UPLOAD_DIR").unwrap_or_else(|_| "./uploads".into()),
            public_base_url: env::var("PUBLIC_BASE_URL")
                .unwrap_or_else(|_| "http://localhost:3000".into()),
            port: env::var("PORT").unwrap_or_else(|_| "3000".into()).parse()?,
        })
    }
}
