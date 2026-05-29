import Foundation
import SwiftData

// MARK: - SwiftData Models (local storage, offline-first)

@Model
final class LocalQuiz {
    @Attribute(.unique) var id: UUID
    var title: String
    var setDescription: String?
    var category: String        // TWK | TIU | TKP | MIXED
    var timeLimit: Int?         // minutes
    var isPublished: Bool
    var lastSyncedAt: Date?

    @Relationship(deleteRule: .cascade, inverse: \LocalQuestion.quiz)
    var questions: [LocalQuestion] = []

    init(
        id: UUID,
        title: String,
        setDescription: String? = nil,
        category: String,
        timeLimit: Int? = nil,
        isPublished: Bool = true,
        lastSyncedAt: Date? = nil
    ) {
        self.id = id
        self.title = title
        self.setDescription = setDescription
        self.category = category
        self.timeLimit = timeLimit
        self.isPublished = isPublished
        self.lastSyncedAt = lastSyncedAt
    }
}

@Model
final class LocalQuestion {
    @Attribute(.unique) var id: UUID
    var quizId: UUID
    var type: String            // MCQ | TRUE_FALSE | ESSAY | IMAGE
    var content: String
    var imageURL: String?
    var explanation: String?
    var position: Int

    var quiz: LocalQuiz?

    @Relationship(deleteRule: .cascade, inverse: \LocalOption.question)
    var options: [LocalOption] = []

    @Relationship(deleteRule: .cascade, inverse: \LocalUserNote.question)
    var note: LocalUserNote?

    init(
        id: UUID,
        quizId: UUID,
        type: String,
        content: String,
        imageURL: String? = nil,
        explanation: String? = nil,
        position: Int
    ) {
        self.id = id
        self.quizId = quizId
        self.type = type
        self.content = content
        self.imageURL = imageURL
        self.explanation = explanation
        self.position = position
    }
}

@Model
final class LocalOption {
    @Attribute(.unique) var id: UUID
    var label: String           // A, B, C, D, E | True, False
    var content: String
    var score: Int              // 0/5 for MCQ/TF; 1-5 for TKP
    var isCorrect: Bool

    var question: LocalQuestion?

    init(id: UUID, label: String, content: String, score: Int, isCorrect: Bool) {
        self.id = id
        self.label = label
        self.content = content
        self.score = score
        self.isCorrect = isCorrect
    }
}

@Model
final class LocalUserNote {
    @Attribute(.unique) var id: UUID
    var questionId: UUID
    /// Serialized PKDrawing binary — stored as external file by SwiftData
    @Attribute(.externalStorage) var drawingData: Data
    var updatedAt: Date

    var question: LocalQuestion?

    init(id: UUID = UUID(), questionId: UUID, drawingData: Data = Data()) {
        self.id = id
        self.questionId = questionId
        self.drawingData = drawingData
        self.updatedAt = Date()
    }
}

@Model
final class LocalQuizSession {
    @Attribute(.unique) var id: UUID
    var quizId: UUID
    var deviceId: String
    var startedAt: Date
    var completedAt: Date?
    var isSynced: Bool

    @Relationship(deleteRule: .cascade, inverse: \LocalAnswer.session)
    var answers: [LocalAnswer] = []

    init(id: UUID = UUID(), quizId: UUID, deviceId: String) {
        self.id = id
        self.quizId = quizId
        self.deviceId = deviceId
        self.startedAt = Date()
        self.isSynced = false
    }
}

@Model
final class LocalAnswer {
    @Attribute(.unique) var id: UUID
    var questionId: UUID
    var selectedOptionId: UUID?
    var essayText: String?
    var answeredAt: Date

    var session: LocalQuizSession?

    init(questionId: UUID, selectedOptionId: UUID? = nil, essayText: String? = nil) {
        self.id = UUID()
        self.questionId = questionId
        self.selectedOptionId = selectedOptionId
        self.essayText = essayText
        self.answeredAt = Date()
    }
}
