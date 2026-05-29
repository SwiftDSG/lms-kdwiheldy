import SwiftUI
import SwiftData

/// Sidebar / home screen — lists available quizzes.
struct QuizListView: View {
    @Query(sort: \LocalQuiz.title) private var quizzes: [LocalQuiz]
    @Query private var allSessions: [LocalQuizSession]
    @Environment(\.modelContext) private var context

    @State private var isLoading = false
    @State private var selectedQuiz: LocalQuiz?
    @State private var showQuiz = false

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                // ── Custom header ──────────────────────────────────────────────
                HStack {
                    Text("CPNS Quiz")
                        .font(.knp(.h2))
                        .foregroundStyle(Color.fontPrimary)
                    Spacer()
                    Button { Task { await sync() } } label: {
                        Group {
                            if isLoading {
                                ProgressView()
                                    .tint(KnPButtonType.ghost.foreground)
                                    .scaleEffect(0.8)
                                    .frame(width: 16, height: 16)
                            } else {
                                Image(systemName: "arrow.clockwise")
                                    .font(.system(size: 14, weight: .black))
                            }
                        }
                        .foregroundStyle(KnPButtonType.ghost.foreground)
                        .frame(width: 34, height: 34)
                    }
                    .buttonStyle(KnPButtonStyle(type: .ghost, borderWidth: 3))
                }
                .padding(16)
                .background(Color.backgroundOne.ignoresSafeArea(edges: .top))

                Rectangle().fill(Color.borderColor).frame(height: 3)

                // ── Content ───────────────────────────────────────────────────
                ZStack {
                    Color.backgroundTwo.ignoresSafeArea()

                    Group {
                        if quizzes.isEmpty && isLoading {
                            VStack(spacing: 16) {
                                ProgressView()
                                    .tint(Color.fontPrimary)
                                Text("Loading quizzes...")
                                    .font(.knp(.body))
                                    .foregroundStyle(Color.fontPrimary)
                            }
                            .frame(maxWidth: .infinity, maxHeight: .infinity)
                        } else if quizzes.isEmpty {
                            VStack(spacing: 16) {
                                Image(systemName: "book.closed")
                                    .font(.system(size: 48, weight: .black))
                                    .foregroundStyle(Color.fontPrimary.opacity(0.3))
                                Text("No Quizzes")
                                    .font(.knp(.h2))
                                    .foregroundStyle(Color.fontPrimary)
                                Text("Connect to the internet to download quizzes.")
                                    .font(.knp(.body))
                                    .foregroundStyle(Color.fontPrimary.opacity(0.6))
                                    .multilineTextAlignment(.center)
                            }
                            .padding(32)
                            .frame(maxWidth: .infinity, maxHeight: .infinity)
                        } else {
                            ScrollView {
                                LazyVStack(spacing: 16) {
                                    ForEach(quizzes) { quiz in
                                        let session = latestCompletedSession(for: quiz.id)
                                        QuizRowView(quiz: quiz, completedSession: session)
                                            .contentShape(Rectangle())
                                            .onTapGesture {
                                                selectedQuiz = quiz
                                                showQuiz = true
                                            }
                                            .swipeActions(edge: .trailing, allowsFullSwipe: false) {
                                                if session != nil {
                                                    Button(role: .destructive) {
                                                        resetQuiz(quizId: quiz.id)
                                                    } label: {
                                                        Label("Reset", systemImage: "arrow.counterclockwise")
                                                    }
                                                    .tint(.warningColor)
                                                }
                                            }
                                    }
                                }
                                .padding(16)
                            }
                        }
                    }
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
            .toolbar(.hidden, for: .navigationBar)
            .navigationDestination(isPresented: $showQuiz) {
                if let quiz = selectedQuiz {
                    if let session = latestCompletedSession(for: quiz.id) {
                        QuizView(vm: QuizSessionViewModel(
                            quiz: quiz,
                            context: context,
                            completedSession: session
                        ))
                    } else {
                        QuizView(vm: QuizSessionViewModel(quiz: quiz, context: context))
                    }
                }
            }
        }
        .task {
            if quizzes.isEmpty {
                await sync()
            }
        }
    }

    // ── Helpers ───────────────────────────────────────────────────────────────

    private func latestCompletedSession(for quizId: UUID) -> LocalQuizSession? {
        allSessions
            .filter { $0.quizId == quizId && $0.completedAt != nil }
            .max { ($0.completedAt ?? .distantPast) < ($1.completedAt ?? .distantPast) }
    }

    private func resetQuiz(quizId: UUID) {
        for session in allSessions where session.quizId == quizId {
            context.delete(session)
        }
        try? context.save()
    }

    private func sync() async {
        isLoading = true
        await SyncManager.shared.syncQuizzes(context: context)
        let all = (try? context.fetch(FetchDescriptor<LocalQuiz>())) ?? []
        for quiz in all where quiz.questions.isEmpty {
            await SyncManager.shared.syncQuizDetail(id: quiz.id, context: context)
        }
        isLoading = false
    }
}

// MARK: - Row

struct QuizRowView: View {
    let quiz: LocalQuiz
    let completedSession: LocalQuizSession?

    private var score: Int {
        guard let session = completedSession else { return 0 }
        return session.answers.reduce(0) { total, answer in
            guard let optionId = answer.selectedOptionId,
                  let question = quiz.questions.first(where: { $0.id == answer.questionId }),
                  let option = question.options.first(where: { $0.id == optionId }) else { return total }
            let hasCorrect = question.options.contains { $0.isCorrect }
            return total + (hasCorrect ? (option.isCorrect ? 5 : 0) : option.score)
        }
    }
    private var maxScore: Int { quiz.questions.count * 5 }
    private var percentage: Int { maxScore > 0 ? Int(Double(score) / Double(maxScore) * 100) : 0 }

    private var categoryColor: Color {
        switch quiz.category {
        case "TWK": return .calmColor
        case "TIU": return .warningColor
        case "TKP": return .successColor.opacity(0.6)
        default:    return .backgroundTwo
        }
    }

    var body: some View {
        HStack(spacing: 12) {
            // Category badge
            KNPBadge(text: quiz.category, color: categoryColor)

            VStack(alignment: .leading, spacing: 3) {
                Text(quiz.title)
                    .font(.knp(.h5))
                    .foregroundStyle(Color.fontPrimary)
                if let desc = quiz.setDescription {
                    Text(desc)
                        .font(.knp(.caption))
                        .foregroundStyle(Color.fontPrimary.opacity(0.5))
                        .lineLimit(1)
                }
            }

            Spacer()

            if completedSession != nil {
                VStack(alignment: .trailing, spacing: 2) {
                    HStack(spacing: 4) {
                        Image(systemName: "checkmark")
                            .font(.system(size: 10, weight: .black))
                            .foregroundStyle(Color.fontSecondary)
                            .frame(width: 16, height: 16)
                            .background(Color.successColor)
                            .clipShape(Circle())
                        Text("\(percentage)%")
                            .font(.knp(.h4))
                            .foregroundStyle(Color.successColor)
                    }
                    Text("\(score) / \(maxScore) pts")
                        .font(.knp(.caption))
                        .foregroundStyle(Color.fontPrimary.opacity(0.5))
                }
            } else {
                VStack(alignment: .trailing, spacing: 2) {
                    Text("\(quiz.questions.count)")
                        .font(.knp(.h3))
                        .foregroundStyle(Color.fontPrimary)
                    Text("questions")
                        .font(.knp(.caption))
                        .foregroundStyle(Color.fontPrimary.opacity(0.5))
                }
            }

            Image(systemName: "chevron.right")
                .font(.system(size: 12, weight: .black))
                .foregroundStyle(Color.borderColor.opacity(0.4))
        }
        .padding(16)
        .knpCard()
    }
}
