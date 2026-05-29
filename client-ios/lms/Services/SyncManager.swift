import Foundation
import SwiftData

/// Handles syncing between the local SwiftData store and the remote backend.
actor SyncManager {
    static let shared = SyncManager()

    private let api = APIClient.shared

    // ── Download quizzes ──────────────────────────────────────────────────────

    /// Fetches all published quizzes and upserts them into the local store.
    @MainActor
    func syncQuizzes(context: ModelContext) async {
        do {
            let remoteQuizzes = try await api.fetchQuizzes()
            for remote in remoteQuizzes {
                await upsertQuiz(remote, context: context)
            }
        } catch {
            print("[SyncManager] fetchQuizzes failed: \(error)")
        }
    }

    /// Downloads full question details for a specific quiz.
    @MainActor
    func syncQuizDetail(id: UUID, context: ModelContext) async {
        do {
            // Check if we have a local copy and use delta sync
            let descriptor = FetchDescriptor<LocalQuiz>(
                predicate: #Predicate { $0.id == id }
            )
            let existing = try? context.fetch(descriptor).first

            let detail: APIQuizDetail
            if let lastSync = existing?.lastSyncedAt {
                detail = try await api.fetchQuizDelta(id: id, since: lastSync)
            } else {
                detail = try await api.fetchQuizDetail(id: id)
            }

            await upsertQuiz(detail.quiz, context: context)
            for question in detail.questions {
                await upsertQuestion(question, context: context)
            }

            // Update lastSyncedAt
            if let local = existing {
                local.lastSyncedAt = Date()
            }
            try? context.save()
        } catch {
            print("[SyncManager] syncQuizDetail failed: \(error)")
        }
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

    @MainActor
    private func upsertQuiz(_ remote: APIQuiz, context: ModelContext) async {
        let id = remote.id
        let descriptor = FetchDescriptor<LocalQuiz>(
            predicate: #Predicate { $0.id == id }
        )
        if let existing = try? context.fetch(descriptor).first {
            existing.title = remote.title
            existing.setDescription = remote.description
            existing.category = remote.category
            existing.timeLimit = remote.timeLimit
            existing.isPublished = remote.isPublished
        } else {
            let local = LocalQuiz(
                id: remote.id,
                title: remote.title,
                setDescription: remote.description,
                category: remote.category,
                timeLimit: remote.timeLimit,
                isPublished: remote.isPublished
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
            existing.imageURL = remote.imageUrl
            existing.explanation = remote.explanation
            existing.position = remote.position
            local = existing
        } else {
            local = LocalQuestion(
                id: remote.id,
                quizId: remote.quizId,
                type: remote.type,
                content: remote.content,
                imageURL: remote.imageUrl,
                explanation: remote.explanation,
                position: remote.position
            )
            context.insert(local)

            // Set the quiz relationship so LocalQuiz.questions is populated
            let quizId = remote.quizId
            let quizDescriptor = FetchDescriptor<LocalQuiz>(
                predicate: #Predicate { $0.id == quizId }
            )
            if let localQuiz = try? context.fetch(quizDescriptor).first {
                local.quiz = localQuiz
            }
        }

        // Upsert options
        for opt in remote.options {
            let optId = opt.id
            let optDesc = FetchDescriptor<LocalOption>(
                predicate: #Predicate { $0.id == optId }
            )
            if let existing = try? context.fetch(optDesc).first {
                existing.label = opt.label
                existing.content = opt.content
                existing.score = opt.score
                existing.isCorrect = opt.isCorrect
            } else {
                let localOpt = LocalOption(
                    id: opt.id,
                    label: opt.label,
                    content: opt.content,
                    score: opt.score,
                    isCorrect: opt.isCorrect
                )
                localOpt.question = local
                context.insert(localOpt)
            }
        }

        try? context.save()
    }
}
