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
            ?? "http://10.67.52.10:3000"
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

    func fetchAIExplanation(questionId: UUID) async throws -> AIExplanationResponse {
        try await get(
            "/api/v1/questions/\(questionId.uuidString.lowercased())/explain"
        )
    }
}

