import Foundation

// MARK: - API response types (mirrors backend JSON)

struct APIQuiz: Decodable {
    let id: UUID
    let title: String
    let description: String?
    let category: String
    let timeLimit: Int?
    let isPublished: Bool
    let createdAt: Date
    let updatedAt: Date

    enum CodingKeys: String, CodingKey {
        case id, title, description, category
        case timeLimit = "time_limit"
        case isPublished = "is_published"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
    }
}

struct APIOption: Decodable {
    let id: UUID
    let label: String
    let content: String
    let score: Int
}

struct APIQuestion: Decodable {
    let id: UUID
    let quizId: UUID
    let type: String
    let subtype: QuestionSubtype
    let content: String
    let imageUrl: String?
    let explanation: String?
    let position: Int
    let createdAt: Date
    let options: [APIOption]

    enum CodingKeys: String, CodingKey {
        case id, type, subtype, content, explanation, position, options
        case quizId = "quiz_id"
        case imageUrl = "image_url"
        case createdAt = "created_at"
    }
}

struct APIQuizDetail: Decodable {
    let quiz: APIQuiz
    let questions: [APIQuestion]
}

struct APISessionResult: Decodable {
    let sessionId: UUID
    let score: Int

    enum CodingKeys: String, CodingKey {
        case sessionId = "session_id"
        case score
    }
}

struct AIExplanationResponse: Decodable {
    let aiExplanation: String
    let aiTip: String

    enum CodingKeys: String, CodingKey {
        case aiExplanation = "ai_explanation"
        case aiTip         = "ai_tip"
    }
}

// MARK: - API Client

actor APIClient {
    static let shared = APIClient()

    private let baseURL: URL
    private let deviceKey: String
    private let session: URLSession

    private init() {
        // Read from Info.plist or use defaults for development
        let base = Bundle.main.object(forInfoDictionaryKey: "API_BASE_URL") as? String
            ?? "http://10.67.49.195:3000"
        let key = Bundle.main.object(forInfoDictionaryKey: "DEVICE_API_KEY") as? String
            ?? "dev_api_key_for_ipad"
        self.baseURL = URL(string: base)!
        self.deviceKey = key

        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 60
        self.session = URLSession(configuration: config)
    }

    private var decoder: JSONDecoder {
        let d = JSONDecoder()
        // chrono (Rust) serializes datetimes with microseconds, e.g. "2024-01-01T00:00:00.123456Z"
        // The plain .iso8601 strategy can't handle fractional seconds, so we try both.
        let withFractions: ISO8601DateFormatter = {
            let f = ISO8601DateFormatter()
            f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
            return f
        }()
        let withoutFractions = ISO8601DateFormatter()
        d.dateDecodingStrategy = .custom { decoder in
            let container = try decoder.singleValueContainer()
            let str = try container.decode(String.self)
            if let date = withFractions.date(from: str) { return date }
            if let date = withoutFractions.date(from: str) { return date }
            throw DecodingError.dataCorruptedError(
                in: container,
                debugDescription: "Cannot parse date: \(str)"
            )
        }
        return d
    }

    private func get<T: Decodable>(_ path: String) async throws -> T {
        var req = URLRequest(url: baseURL.appendingPathComponent(path))
        req.setValue(deviceKey, forHTTPHeaderField: "X-Device-Key")
        let (data, resp) = try await session.data(for: req)
        print("[APIClient] GET \(path) →", (resp as? HTTPURLResponse)?.statusCode ?? -1)
        print("[APIClient] Body:", String(data: data, encoding: .utf8) ?? "<binary>")
        try validate(resp)
        return try decoder.decode(T.self, from: data)
    }

    private func post<T: Decodable, B: Encodable>(_ path: String, body: B) async throws -> T {
        var req = URLRequest(url: baseURL.appendingPathComponent(path))
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.setValue(deviceKey, forHTTPHeaderField: "X-Device-Key")
        req.httpBody = try JSONEncoder().encode(body)
        let (data, resp) = try await session.data(for: req)
        try validate(resp)
        return try decoder.decode(T.self, from: data)
    }

    private func validate(_ response: URLResponse) throws {
        guard let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode) else {
            throw URLError(.badServerResponse)
        }
    }

    // ── Public endpoints ──────────────────────────────────────────────────────

    func fetchQuizzes() async throws -> [APIQuiz] {
        try await get("/api/v1/quizzes")
    }

    func fetchQuizDetail(id: UUID) async throws -> APIQuizDetail {
        try await get("/api/v1/quizzes/\(id.uuidString.lowercased())")
    }

    func fetchQuizDelta(id: UUID, since: Date) async throws -> APIQuizDetail {
        let iso = ISO8601DateFormatter().string(from: since)
        return try await get("/api/v1/quizzes/\(id.uuidString.lowercased())?since=\(iso)")
    }

    func submitSession(_ payload: SubmitSessionPayload) async throws -> APISessionResult {
        try await post("/api/v1/sessions", body: payload)
    }

    func fetchAIExplanation(questionId: UUID) async throws -> AIExplanationResponse {
        try await get(
            "/api/v1/questions/\(questionId.uuidString.lowercased())/explain"
        )
    }
}

// MARK: - Submit payload

struct SubmitSessionPayload: Encodable {
    let id: String           // lowercase UUID string
    let quizId: String       // lowercase UUID string
    let deviceId: String
    let startedAt: Date
    let completedAt: Date?
    let answers: [SubmitAnswerPayload]

    init(id: UUID, quizId: UUID, deviceId: String, startedAt: Date, completedAt: Date?, answers: [SubmitAnswerPayload]) {
        self.id = id.uuidString.lowercased()
        self.quizId = quizId.uuidString.lowercased()
        self.deviceId = deviceId
        self.startedAt = startedAt
        self.completedAt = completedAt
        self.answers = answers
    }

    enum CodingKeys: String, CodingKey {
        case id
        case quizId = "quiz_id"
        case deviceId = "device_id"
        case startedAt = "started_at"
        case completedAt = "completed_at"
        case answers
    }
}

struct SubmitAnswerPayload: Encodable {
    let questionId: String        // lowercase UUID string
    let selectedOptionId: String? // lowercase UUID string
    let essayText: String?
    let answeredAt: Date

    init(questionId: UUID, selectedOptionId: UUID?, essayText: String?, answeredAt: Date) {
        self.questionId = questionId.uuidString.lowercased()
        self.selectedOptionId = selectedOptionId?.uuidString.lowercased()
        self.essayText = essayText
        self.answeredAt = answeredAt
    }

    enum CodingKeys: String, CodingKey {
        case questionId = "question_id"
        case selectedOptionId = "selected_option_id"
        case essayText = "essay_text"
        case answeredAt = "answered_at"
    }
}
