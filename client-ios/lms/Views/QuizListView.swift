import SwiftUI
import SwiftData

// MARK: - Display item

/// Unified item for the quiz list, merging the server list (online) with local storage (offline).
struct QuizDisplayItem: Identifiable {
    let id: UUID
    let title: String
    let category: String
    let description: String?
    let serverUpdatedAt: Date?
    /// Non-nil only when the quiz has been downloaded to local storage.
    let local: LocalQuiz?
}

// MARK: - List view

struct QuizListView: View {
    /// Only quizzes the user has explicitly downloaded are stored in SwiftData.
    @Query(filter: #Predicate<LocalQuiz> { $0.isDownloaded == true }, sort: [SortDescriptor(\LocalQuiz.title)])
    private var downloadedQuizzes: [LocalQuiz]

    @Query private var allSessions: [LocalQuizSession]
    @Environment(\.modelContext) private var context

    /// Server quiz list — held in memory only; not persisted.
    @State private var serverQuizzes: [APIQuiz] = []
    @State private var isRefreshing = false
    @State private var isOffline = false
    @State private var downloadingIds: Set<UUID> = []
    @State private var selectedQuiz: LocalQuiz?
    @State private var showQuiz = false

    // ── Merged display list ───────────────────────────────────────────────────

    private var displayItems: [QuizDisplayItem] {
        if isOffline {
            // Offline: only downloaded quizzes are shown
            return downloadedQuizzes.map {
                QuizDisplayItem(id: $0.id, title: $0.title, category: $0.category,
                                description: $0.setDescription,
                                serverUpdatedAt: $0.serverUpdatedAt, local: $0)
            }
        }

        // Online: server list is the source of truth
        var items = serverQuizzes.map { sq in
            QuizDisplayItem(
                id: sq.id, title: sq.title, category: sq.category,
                description: sq.description, serverUpdatedAt: sq.updatedAt,
                local: downloadedQuizzes.first { $0.id == sq.id }
            )
        }

        // Also surface downloaded quizzes that are no longer on the server
        // (e.g., deleted by admin — user still has their data)
        let serverIds = Set(serverQuizzes.map { $0.id })
        for local in downloadedQuizzes where !serverIds.contains(local.id) {
            items.append(QuizDisplayItem(
                id: local.id, title: local.title, category: local.category,
                description: local.setDescription,
                serverUpdatedAt: local.serverUpdatedAt, local: local
            ))
        }

        return items.sorted { $0.title < $1.title }
    }

    // ── Body ──────────────────────────────────────────────────────────────────

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                // ── Header ────────────────────────────────────────────────────
                HStack {
                    Text("CPNS Quiz")
                        .font(.knp(.h2))
                        .foregroundStyle(Color.fontPrimary)
                    Spacer()
                    Button { Task { await refreshList() } } label: {
                        Group {
                            if isRefreshing {
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
                    contentView
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
        .task { await refreshList() }
    }

    @ViewBuilder
    private var contentView: some View {
        let items = displayItems

        if items.isEmpty && isRefreshing {
            VStack(spacing: 16) {
                ProgressView().tint(Color.fontPrimary)
                Text("Loading quizzes...")
                    .font(.knp(.body))
                    .foregroundStyle(Color.fontPrimary)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)

        } else if items.isEmpty && isOffline {
            VStack(spacing: 16) {
                Image(systemName: "wifi.slash")
                    .font(.system(size: 48, weight: .black))
                    .foregroundStyle(Color.fontPrimary.opacity(0.3))
                Text("You're Offline")
                    .font(.knp(.h2))
                    .foregroundStyle(Color.fontPrimary)
                Text("Connect to the internet to browse and download quizzes.")
                    .font(.knp(.body))
                    .foregroundStyle(Color.fontPrimary.opacity(0.6))
                    .multilineTextAlignment(.center)
            }
            .padding(32)
            .frame(maxWidth: .infinity, maxHeight: .infinity)

        } else if items.isEmpty {
            VStack(spacing: 16) {
                Image(systemName: "book.closed")
                    .font(.system(size: 48, weight: .black))
                    .foregroundStyle(Color.fontPrimary.opacity(0.3))
                Text("No Quizzes")
                    .font(.knp(.h2))
                    .foregroundStyle(Color.fontPrimary)
                Text("No quizzes have been published yet.")
                    .font(.knp(.body))
                    .foregroundStyle(Color.fontPrimary.opacity(0.6))
                    .multilineTextAlignment(.center)
            }
            .padding(32)
            .frame(maxWidth: .infinity, maxHeight: .infinity)

        } else {
            List {
                ForEach(items) { item in
                    let session = item.local.flatMap { latestCompletedSession(for: $0.id) }
                    let isDownloading = downloadingIds.contains(item.id)

                    QuizRowView(
                        item: item,
                        completedSession: session,
                        isDownloading: isDownloading,
                        isOffline: isOffline
                    ) {
                        Task { await downloadQuiz(id: item.id) }
                    }
                    .contentShape(Rectangle())
                    .onTapGesture {
                        guard let local = item.local else { return }
                        selectedQuiz = local
                        showQuiz = true
                    }
                    .listRowBackground(Color.backgroundTwo)
                    .listRowSeparator(.hidden)
                    .listRowInsets(EdgeInsets(top: 8, leading: 16, bottom: 8, trailing: 16))
                    .swipeActions(edge: .leading, allowsFullSwipe: true) {
                        if let local = item.local {
                            Button(role: .destructive) {
                                deleteQuiz(local)
                            } label: {
                                Label("Hapus", systemImage: "trash")
                            }
                        }
                    }
                    .swipeActions(edge: .trailing, allowsFullSwipe: false) {
                        if session != nil, let local = item.local {
                            Button {
                                resetQuiz(quizId: local.id)
                            } label: {
                                Label("Reset", systemImage: "arrow.counterclockwise")
                            }
                            .tint(.warningColor)
                        }
                    }
                }
            }
            .listStyle(.plain)
            .background(Color.backgroundTwo)
        }
    }

    // ── Helpers ───────────────────────────────────────────────────────────────

    private func latestCompletedSession(for quizId: UUID) -> LocalQuizSession? {
        allSessions
            .filter { $0.quizId == quizId && $0.completedAt != nil }
            .max { ($0.completedAt ?? .distantPast) < ($1.completedAt ?? .distantPast) }
    }

    private func deleteQuiz(_ quiz: LocalQuiz) {
        context.delete(quiz)   // cascades to questions, options, notes, sessions
        try? context.save()
    }

    private func resetQuiz(quizId: UUID) {
        for session in allSessions where session.quizId == quizId {
            context.delete(session)
        }
        try? context.save()
    }

    /// Lightweight: fetches the quiz list metadata from the server.
    /// On failure, switches to offline mode showing only downloaded quizzes.
    private func refreshList() async {
        isRefreshing = true
        do {
            serverQuizzes = try await SyncManager.shared.fetchAvailableQuizzes(context: context)
            isOffline = false
        } catch {
            isOffline = true
            serverQuizzes = []
        }
        isRefreshing = false
    }

    /// Downloads full questions for a specific quiz. Shows per-row loading state.
    private func downloadQuiz(id: UUID) async {
        downloadingIds.insert(id)
        do {
            try await SyncManager.shared.downloadQuiz(id: id, context: context)
        } catch {
            print("[QuizListView] download failed for \(id): \(error)")
        }
        downloadingIds.remove(id)
    }
}

// MARK: - Row

struct QuizRowView: View {
    let item: QuizDisplayItem
    let completedSession: LocalQuizSession?
    let isDownloading: Bool
    let isOffline: Bool
    let onDownload: () -> Void

    private var isDownloaded: Bool { item.local != nil }

    private var hasUpdate: Bool {
        guard let local = item.local,
              let serverUpdated = item.serverUpdatedAt,
              let lastSynced = local.lastSyncedAt else { return false }
        return serverUpdated > lastSynced
    }

    private var score: Int {
        guard let session = completedSession, let local = item.local else { return 0 }
        return session.answers.reduce(0) { total, answer in
            guard let optionId = answer.selectedOptionId,
                  let question = local.questions.first(where: { $0.id == answer.questionId }),
                  let option = question.options.first(where: { $0.id == optionId }) else { return total }
            let hasCorrect = question.options.contains { $0.isCorrect }
            return total + (hasCorrect ? (option.isCorrect ? 5 : 0) : option.score)
        }
    }
    private var maxScore: Int { (item.local?.questions.count ?? 0) * 5 }
    private var percentage: Int { maxScore > 0 ? Int(Double(score) / Double(maxScore) * 100) : 0 }

    private var categoryColor: Color {
        switch item.category {
        case "TWK": return .calmColor
        case "TIU": return .warningColor
        case "TKP": return .successColor.opacity(0.6)
        default:    return .backgroundTwo
        }
    }

    var body: some View {
        HStack(spacing: 12) {
            KNPBadge(text: item.category, color: categoryColor)

            VStack(alignment: .leading, spacing: 3) {
                Text(item.title)
                    .font(.knp(.h5))
                    .foregroundStyle(Color.fontPrimary)
                if let desc = item.description {
                    Text(desc)
                        .font(.knp(.caption))
                        .foregroundStyle(Color.fontPrimary.opacity(0.5))
                        .lineLimit(1)
                }
            }

            Spacer()

            trailingContent
        }
        .padding(16)
        .knpCard()
        .opacity(isDownloaded ? 1 : 0.75)
    }

    @ViewBuilder
    private var trailingContent: some View {
        if !isDownloaded {
            // ── Not downloaded ────────────────────────────────────────────────
            Button(action: onDownload) {
                if isDownloading {
                    ProgressView()
                        .tint(.white)
                        .scaleEffect(0.75)
                        .frame(width: 80, height: 28)
                } else {
                    Label("Unduh", systemImage: "arrow.down.circle.fill")
                        .font(.knp(.caption))
                        .foregroundStyle(KnPButtonType.primary.foreground)
                        .frame(height: 28)
                        .padding(.horizontal, 10)
                }
            }
            .buttonStyle(KnPButtonStyle(type: .primary))
            .disabled(isOffline)

        } else {
            // ── Downloaded ────────────────────────────────────────────────────
            HStack(spacing: 8) {
                VStack(alignment: .trailing, spacing: 4) {
                    if completedSession != nil {
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
                    } else {
                        Text("\(item.local?.questions.count ?? 0)")
                            .font(.knp(.h3))
                            .foregroundStyle(Color.fontPrimary)
                        Text("questions")
                            .font(.knp(.caption))
                            .foregroundStyle(Color.fontPrimary.opacity(0.5))
                    }

                    // Update badge — only visible when server has newer content
                    if hasUpdate {
                        Button(action: onDownload) {
                            if isDownloading {
                                ProgressView()
                                    .tint(Color.warningColor)
                                    .scaleEffect(0.6)
                                    .frame(height: 18)
                            } else {
                                Label("Update", systemImage: "arrow.down.circle")
                                    .font(.system(size: 11, weight: .semibold))
                                    .padding(.horizontal, 6)
                                    .padding(.vertical, 2)
                                    .background(Color.warningColor.opacity(0.15))
                                    .foregroundStyle(Color.warningColor)
                                    .clipShape(Capsule())
                            }
                        }
                        .disabled(isOffline)
                    }
                }

                Image(systemName: "chevron.right")
                    .font(.system(size: 12, weight: .black))
                    .foregroundStyle(Color.borderColor.opacity(0.4))
            }
        }
    }
}
