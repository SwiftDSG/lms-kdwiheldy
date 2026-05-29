/**
 * MongoDB setup script for LMS CPNS Quiz Platform.
 *
 * Run once against your MongoDB instance:
 *   mongosh "mongodb://localhost:27017/lms" mongodb_setup.js
 *
 * Collections are created implicitly by the Rust app on first insert.
 * This script just creates indexes and the initial admin user.
 */

// ── Indexes ───────────────────────────────────────────────────────────────────

db.quizzes.createIndex({ "is_published": 1 });
db.quizzes.createIndex({ "questions.id": 1 });  // for question lookups
db.quizzes.createIndex({ "updated_at": -1 });

db.quiz_sessions.createIndex({ "quiz_id": 1 });
db.quiz_sessions.createIndex({ "device_id": 1 });
db.quiz_sessions.createIndex({ "started_at": -1 });

db.admin_users.createIndex({ "email": 1 }, { unique: true });

print("✓ Indexes created");

// ── Initial admin user ────────────────────────────────────────────────────────
// Password hash below = bcrypt("changeme", cost=12)
// CHANGE THIS PASSWORD immediately after first login!

const existingAdmin = db.admin_users.findOne({ email: "admin@example.com" });
if (!existingAdmin) {
  db.admin_users.insertOne({
    _id: UUID().toString(),
    email: "admin@example.com",
    // bcrypt hash of "changeme" — replace with a real hash
    password_hash: "$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewLs2Gm9V5Bq7G1C",
    created_at: new Date(),
  });
  print("✓ Default admin created: admin@example.com / changeme");
  print("  ⚠️  CHANGE THIS PASSWORD before going to production!");
} else {
  print("✓ Admin user already exists, skipping");
}
