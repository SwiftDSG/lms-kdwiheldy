import Foundation
import SwiftData

// MARK: - Enums

enum QuestionSubtype: String, Codable, CaseIterable {
    // TWK
    case pancasila          = "PANCASILA"
    case uud1945            = "UUD_1945"
    case bhinneka           = "BHINNEKA"
    case nkri               = "NKRI"
    case sejarahNasional    = "SEJARAH_NASIONAL"
    case sistemPemerintahan = "SISTEM_PEMERINTAHAN"
    case belaNegara         = "BELA_NEGARA"
    case bahasaIndonesia    = "BAHASA_INDONESIA"
    // TIU
    case analogiVerbal           = "ANALOGI_VERBAL"
    case analogiGambar           = "ANALOGI_GAMBAR"
    case silogisme               = "SILOGISME"
    case antonim                 = "ANTONIM"
    case sinonim                 = "SINONIM"
    case aritmatika              = "ARITMATIKA"
    case deretAngka              = "DERET_ANGKA"
    case soalCerita              = "SOAL_CERITA"
    case perbandinganKuantitatif = "PERBANDINGAN_KUANTITATIF"
    // TKP
    case pelayananPublik    = "PELAYANAN_PUBLIK"
    case profesionalisme    = "PROFESIONALISME"
    case jejaringKerja      = "JEJARING_KERJA"
    case sosialBudaya       = "SOSIAL_BUDAYA"
    case teknologiInformasi = "TEKNOLOGI_INFORMASI"
    case orientasiBelajar   = "ORIENTASI_BELAJAR"
    case mengendalikanDiri  = "MENGENDALIKAN_DIRI"
    case beradaptasi        = "BERADAPTASI"
    case kreativitasInovasi = "KREATIVITAS_INOVASI"

    /// Mirrors SubtypeConfig.needs_ml_explain on the server.
    /// False → the /explain endpoint short-circuits to stored explanation; no point showing the AI button.
    var needsMlExplain: Bool {
        switch self {
        case .analogiGambar:
            return false
        case .antonim, .sinonim, .analogiVerbal:
            return false
        case .pelayananPublik, .profesionalisme, .jejaringKerja, .sosialBudaya,
             .teknologiInformasi, .orientasiBelajar, .mengendalikanDiri,
             .beradaptasi, .kreativitasInovasi:
            return false
        default:
            return true
        }
    }
}

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
    /// The server's updated_at timestamp — refreshed on every list fetch.
    /// Compare with lastSyncedAt to detect available updates.
    var serverUpdatedAt: Date?
    /// True once questions have been fully downloaded for this quiz.
    var isDownloaded: Bool

    @Relationship(deleteRule: .cascade, inverse: \LocalQuestion.quiz)
    var questions: [LocalQuestion] = []

    init(
        id: UUID,
        title: String,
        setDescription: String? = nil,
        category: String,
        timeLimit: Int? = nil,
        isPublished: Bool = true,
        lastSyncedAt: Date? = nil,
        serverUpdatedAt: Date? = nil,
        isDownloaded: Bool = false
    ) {
        self.id = id
        self.title = title
        self.setDescription = setDescription
        self.category = category
        self.timeLimit = timeLimit
        self.isPublished = isPublished
        self.lastSyncedAt = lastSyncedAt
        self.serverUpdatedAt = serverUpdatedAt
        self.isDownloaded = isDownloaded
    }
}

@Model
final class LocalQuestion {
    @Attribute(.unique) var id: UUID
    var quizId: UUID
    var type: String            // MCQ | TRUE_FALSE | ESSAY | IMAGE
    var subtype: QuestionSubtype
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
        subtype: QuestionSubtype,
        content: String,
        imageURL: String? = nil,
        explanation: String? = nil,
        position: Int
    ) {
        self.id = id
        self.quizId = quizId
        self.type = type
        self.subtype = subtype
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
    /// MCQ/TF: 0 = wrong, 5 = correct. TKP: 1–5 weighted (best = 5).
    var score: Int

    var question: LocalQuestion?

    /// True when this option is the best/correct answer (score == 5).
    var isCorrect: Bool { score == 5 }

    init(id: UUID, label: String, content: String, score: Int) {
        self.id = id
        self.label = label
        self.content = content
        self.score = score
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
    var startedAt: Date
    var completedAt: Date?

    @Relationship(deleteRule: .cascade, inverse: \LocalAnswer.session)
    var answers: [LocalAnswer] = []

    init(id: UUID = UUID(), quizId: UUID) {
        self.id = id
        self.quizId = quizId
        self.startedAt = Date()
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
