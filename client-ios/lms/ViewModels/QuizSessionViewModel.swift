import Foundation
import SwiftData
import PencilKit

@MainActor
@Observable
final class QuizSessionViewModel {
    // ── State ─────────────────────────────────────────────────────────────────
    var quiz: LocalQuiz
    var questions: [LocalQuestion] = []
    var currentIndex: Int = 0
    var answers: [UUID: LocalAnswer] = [:]      // questionId → answer
    var notes: [UUID: LocalUserNote] = [:]      // questionId → note
    var isSubmitting: Bool = false
    var result: QuizResult? = nil

    private let context: ModelContext
    private let deviceId: String

    // ── Timer ─────────────────────────────────────────────────────────────────
    var secondsRemaining: Int = 0
    var timerActive: Bool = false
    private var timerTask: Task<Void, Never>?

    // ── Init ──────────────────────────────────────────────────────────────────

    init(quiz: LocalQuiz, context: ModelContext) {
        self.quiz = quiz
        self.context = context
        self.deviceId = Self.deviceIdentifier()
        self.questions = quiz.questions.sorted { $0.position < $1.position }

        if let limit = quiz.timeLimit {
            self.secondsRemaining = limit * 60
        }

        // Load existing notes from SwiftData
        loadNotes()
    }

    /// Review-mode init: opens a previously completed session directly in result view.
    init(quiz: LocalQuiz, context: ModelContext, completedSession: LocalQuizSession) {
        self.quiz = quiz
        self.context = context
        self.deviceId = Self.deviceIdentifier()
        self.questions = quiz.questions.sorted { $0.position < $1.position }

        // Pre-populate answers from the stored session
        for answer in completedSession.answers {
            self.answers[answer.questionId] = answer
        }

        self.result = QuizResult(score: calculateScore(), maxScore: questions.count * 5)

        loadNotes()
    }

    // ── Navigation ────────────────────────────────────────────────────────────

    var currentQuestion: LocalQuestion? { questions[safe: currentIndex] }
    var isFirst: Bool { currentIndex == 0 }
    var isLast: Bool { currentIndex == questions.count - 1 }

    func goTo(index: Int) {
        guard questions.indices.contains(index) else { return }
        currentIndex = index
    }

    func next() { if !isLast { currentIndex += 1 } }
    func previous() { if !isFirst { currentIndex -= 1 } }

    // ── Answers ───────────────────────────────────────────────────────────────

    func selectOption(_ optionId: UUID, for questionId: UUID) {
        if let existing = answers[questionId] {
            existing.selectedOptionId = optionId
            existing.essayText = nil
        } else {
            answers[questionId] = LocalAnswer(
                questionId: questionId,
                selectedOptionId: optionId
            )
        }
    }

    func setEssayText(_ text: String, for questionId: UUID) {
        if let existing = answers[questionId] {
            existing.essayText = text
            existing.selectedOptionId = nil
        } else {
            answers[questionId] = LocalAnswer(
                questionId: questionId,
                essayText: text
            )
        }
    }

    func isAnswered(_ questionId: UUID) -> Bool {
        guard let a = answers[questionId] else { return false }
        return a.selectedOptionId != nil || !(a.essayText?.isEmpty ?? true)
    }

    var answeredCount: Int { answers.values.filter { isAnswered($0.questionId) }.count }

    // ── Drawing notes ─────────────────────────────────────────────────────────

    /// Returns or creates a UserNote for the current question.
    func note(for questionId: UUID) -> LocalUserNote {
        if let existing = notes[questionId] { return existing }
        let newNote = LocalUserNote(questionId: questionId)
        context.insert(newNote)
        notes[questionId] = newNote
        return newNote
    }

    /// Called by the canvas view when the drawing changes.
    func saveDrawing(_ drawing: PKDrawing, for questionId: UUID) {
        let n = note(for: questionId)
        n.drawingData = drawing.dataRepresentation()
        n.updatedAt = Date()
        try? context.save()
    }

    // ── Submit ────────────────────────────────────────────────────────────────

    func submitSession() async {
        isSubmitting = true
        timerTask?.cancel()

        let session = LocalQuizSession(
            quizId: quiz.id,
            deviceId: deviceId
        )
        session.completedAt = Date()

        for answer in answers.values {
            let a = LocalAnswer(
                questionId: answer.questionId,
                selectedOptionId: answer.selectedOptionId,
                essayText: answer.essayText
            )
            a.session = session
            context.insert(a)
        }

        context.insert(session)
        try? context.save()

        result = QuizResult(score: calculateScore(), maxScore: questions.count * 5)

        // Attempt immediate sync; failure is OK (retry on next launch)
        await SyncManager.shared.uploadPendingSessions(context: context)
        isSubmitting = false
    }

    // ── Scoring ───────────────────────────────────────────────────────────────

    /// MCQ/TF: 5 pts if the selected option is_correct, 0 otherwise.
    /// TKP (no is_correct option): use the option's stored score (1–5).
    private func calculateScore() -> Int {
        var total = 0
        for question in questions {
            guard let answer = answers[question.id],
                  let optionId = answer.selectedOptionId,
                  let option = question.options.first(where: { $0.id == optionId }) else { continue }
            let hasCorrectOption = question.options.contains { $0.isCorrect }
            if hasCorrectOption {
                total += option.isCorrect ? 5 : 0
            } else {
                total += option.score   // TKP weighted scoring
            }
        }
        return total
    }

    // ── Reset (retry) ─────────────────────────────────────────────────────────

    func reset() {
        // Delete the saved session from SwiftData so the quiz appears fresh on next open
        let quizId = quiz.id
        if let sessions = try? context.fetch(FetchDescriptor<LocalQuizSession>()) {
            for session in sessions where session.quizId == quizId {
                context.delete(session)
            }
            try? context.save()
        }

        currentIndex = 0
        answers = [:]
        result = nil
        timerTask?.cancel()
        timerTask = nil
        timerActive = false
        if let limit = quiz.timeLimit {
            secondsRemaining = limit * 60
        }
    }

    // ── Timer ─────────────────────────────────────────────────────────────────

    func startTimer() {
        guard quiz.timeLimit != nil else { return }
        timerActive = true
        timerTask = Task {
            while secondsRemaining > 0 {
                try? await Task.sleep(nanoseconds: 1_000_000_000)
                if Task.isCancelled { break }
                secondsRemaining -= 1
            }
            if secondsRemaining == 0 {
                await submitSession()
            }
        }
    }

    // ── Helpers ───────────────────────────────────────────────────────────────

    private func loadNotes() {
        let descriptor = FetchDescriptor<LocalUserNote>()
        let allNotes = (try? context.fetch(descriptor)) ?? []
        for note in allNotes where questions.contains(where: { $0.id == note.questionId }) {
            notes[note.questionId] = note
        }
    }

    private static func deviceIdentifier() -> String {
        let key = "device_uuid"
        if let existing = UserDefaults.standard.string(forKey: key) {
            return existing
        }
        let new = UUID().uuidString
        UserDefaults.standard.set(new, forKey: key)
        return new
    }
}

// ── Quiz result ───────────────────────────────────────────────────────────────

struct QuizResult: Identifiable {
    let id = UUID()
    let score: Int
    let maxScore: Int
    var percentage: Int { maxScore > 0 ? Int(Double(score) / Double(maxScore) * 100) : 0 }
}

// ── Safe subscript helper ─────────────────────────────────────────────────────

extension Array {
    subscript(safe index: Index) -> Element? {
        indices.contains(index) ? self[index] : nil
    }
}
