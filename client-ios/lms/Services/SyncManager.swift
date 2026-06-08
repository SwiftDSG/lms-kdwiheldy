import Foundation
import SwiftData

/// Handles syncing between the local SwiftData store and the remote backend.
actor SyncManager {
    static let shared = SyncManager()

    private let api = APIClient.shared

    // ── Fetch quiz list (lightweight) ─────────────────────────────────────────

    /// Fetches the published quiz list from the server. Returns the raw server list
    /// for in-memory display — does NOT persist non-downloaded quiz metadata.
    ///
    /// For quizzes already downloaded locally, updates serverUpdatedAt so the UI
    /// can detect when newer content is available.
    ///
    /// Throws if the network request fails; callers use this to detect offline state.
    @MainActor
    func fetchAvailableQuizzes(context: ModelContext) async throws -> [APIQuiz] {
        let remoteQuizzes = try await api.fetchQuizzes()

        // Update serverUpdatedAt only for quizzes already downloaded locally
        for remote in remoteQuizzes {
            let id = remote.id
            let descriptor = FetchDescriptor<LocalQuiz>(
                predicate: #Predicate { $0.id == id && $0.isDownloaded }
            )
            if let local = try? context.fetch(descriptor).first {
                local.serverUpdatedAt = remote.updatedAt
            }
        }
        try? context.save()

        return remoteQuizzes
    }

    // ── Download a single quiz ────────────────────────────────────────────────

    /// Downloads full quiz + questions for a specific quiz. Persists everything to
    /// SwiftData and sets isDownloaded = true.
    @MainActor
    func downloadQuiz(id: UUID, context: ModelContext) async throws {
        let detail = try await api.fetchQuizDetail(id: id)

        await upsertQuizMeta(detail.quiz, context: context)
        for question in detail.questions {
            await upsertQuestion(question, context: context)
        }

        let descriptor = FetchDescriptor<LocalQuiz>(predicate: #Predicate { $0.id == id })
        if let local = try? context.fetch(descriptor).first {
            local.isDownloaded = true
            local.lastSyncedAt = Date()
        }
        try? context.save()
    }

    // ── Upload sessions ───────────────────────────────────────────────────────

    /// Uploads all unsynced local sessions to the backend.
    @MainActor
    func uploadPendingSessions(context: ModelContext) async {
        let descriptor = FetchDescriptor<LocalQuizSession>(
            predicate: #Predicate { !$0.isSynced }
        )
        guard let sessions = try? context.fetch(descriptor) else { return }

        for session in sessions {
            let payload = SubmitSessionPayload(
                id: session.id,
                quizId: session.quizId,
                deviceId: session.deviceId,
                startedAt: session.startedAt,
                completedAt: session.completedAt,
                answers: session.answers.map {
                    SubmitAnswerPayload(
                        questionId: $0.questionId,
                        selectedOptionId: $0.selectedOptionId,
                        essayText: $0.essayText,
                        answeredAt: $0.answeredAt
                    )
                }
            )
            do {
                _ = try await api.submitSession(payload)
                session.isSynced = true
            } catch {
                print("[SyncManager] uploadSession \(session.id) failed: \(error)")
            }
        }
        try? context.save()
    }

    // ── Private helpers ───────────────────────────────────────────────────────

    /// Persists quiz metadata. Called only when the user explicitly downloads a quiz.
    /// Preserves isDownloaded and lastSyncedAt on existing records.
    @MainActor
    private func upsertQuizMeta(_ remote: APIQuiz, context: ModelContext) async {
        let id = remote.id
        let descriptor = FetchDescriptor<LocalQuiz>(predicate: #Predicate { $0.id == id })
        if let existing = try? context.fetch(descriptor).first {
            existing.title = remote.title
            existing.setDescription = remote.description
            existing.category = remote.category
            existing.timeLimit = remote.timeLimit
            existing.isPublished = remote.isPublished
            existing.serverUpdatedAt = remote.updatedAt
        } else {
            let local = LocalQuiz(
                id: remote.id,
                title: remote.title,
                setDescription: remote.description,
                category: remote.category,
                timeLimit: remote.timeLimit,
                isPublished: remote.isPublished,
                serverUpdatedAt: remote.updatedAt,
                isDownloaded: false
            )
            context.insert(local)
        }
        try? context.save()
    }

    @MainActor
    private func upsertQuestion(_ remote: APIQuestion, context: ModelContext) async {
        let id = remote.id
        let descriptor = FetchDescriptor<LocalQuestion>(
            predicate: #Predicate { $0.id == id }
        )

        let local: LocalQuestion
        if let existing = try? context.fetch(descriptor).first {
            existing.content = remote.content
            existing.type = remote.type
            existing.subtype = remote.subtype
            existing.imageURL = remote.imageUrl
            existing.explanation = remote.explanation
            existing.position = remote.position
            local = existing
        } else {
            local = LocalQuestion(
                id: remote.id,
                quizId: remote.quizId,
                type: remote.type,
                subtype: remote.subtype,
                content: remote.content,
                imageURL: remote.imageUrl,
                explanation: remote.explanation,
                position: remote.position
            )
            context.insert(local)

            let quizId = remote.quizId
            let quizDescriptor = FetchDescriptor<LocalQuiz>(
                predicate: #Predicate { $0.id == quizId }
            )
            if let localQuiz = try? context.fetch(quizDescriptor).first {
                local.quiz = localQuiz
            }
        }

        for opt in remote.options {
            let optId = opt.id
            let optDesc = FetchDescriptor<LocalOption>(
                predicate: #Predicate { $0.id == optId }
            )
            if let existing = try? context.fetch(optDesc).first {
                existing.label = opt.label
                existing.content = opt.content
                existing.score = opt.score
            } else {
                let localOpt = LocalOption(
                    id: opt.id,
                    label: opt.label,
                    content: opt.content,
                    score: opt.score
                )
                localOpt.question = local
                context.insert(localOpt)
            }
        }

        try? context.save()
    }
}
