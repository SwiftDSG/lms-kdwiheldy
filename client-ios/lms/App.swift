import SwiftUI
import SwiftData

@main
struct lmsApp: App {
    var body: some Scene {
        WindowGroup {
            QuizListView()
        }
        .modelContainer(for: [
            LocalQuiz.self,
            LocalQuestion.self,
            LocalOption.self,
            LocalUserNote.self,
            LocalQuizSession.self,
            LocalAnswer.self,
        ])
    }
}
