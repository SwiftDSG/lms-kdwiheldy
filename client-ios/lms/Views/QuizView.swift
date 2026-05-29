import SwiftUI
import PencilKit

/// Root quiz view — 50/50 split: left = questions, right = drawing canvas.
/// Swaps to QuizResultView in-place when the quiz is submitted.
struct QuizView: View {
    @State var vm: QuizSessionViewModel
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        if let result = vm.result {
            // ── Review mode ───────────────────────────────────────────────────
            QuizResultView(
                vm: vm,
                result: result,
                onRetry: { vm.reset() }
            )
        } else {
            // ── Quiz mode ─────────────────────────────────────────────────────
            VStack(spacing: 0) {
                ZStack {
                    HStack {
                        Button { dismiss() } label: {
                            HStack(spacing: 4) {
                                Image(systemName: "chevron.left")
                                    .font(.system(size: 12, weight: .black))
                                Text("Back")
                                    .font(.knp(.h6))
                            }
                            .foregroundStyle(KnPButtonType.secondary.foreground)
                            .padding(.horizontal, 10)
                            .frame(minHeight: 32)
                        }
                        .buttonStyle(KnPButtonStyle(type: .secondary, borderWidth: 3))
                        
                        Spacer()
                        
                        if vm.quiz.timeLimit != nil {
                            TimerView(secondsRemaining: vm.secondsRemaining)
                        }
                    }
                    VStack(spacing: 1) {
                        Text(vm.quiz.title)
                            .font(.knp(.h5))
                            .foregroundStyle(Color.fontPrimary)
                        Text("\(vm.answeredCount)/\(vm.questions.count) answered")
                            .font(.knp(.caption))
                            .foregroundStyle(Color.fontPrimary.opacity(0.5))
                    }
                }
                .padding(16)
                .background(Color.backgroundOne.ignoresSafeArea(edges: .top))

                Rectangle().fill(Color.borderColor).frame(height: 3)

                GeometryReader { geo in
                    HStack(spacing: 0) {
                        QuestionPanelView(vm: vm)
                            .frame(width: geo.size.width * 0.5)

                        if let question = vm.currentQuestion {
                            let note = vm.note(for: question.id)
                            DrawingCanvasView(
                                questionId: question.id,
                                note: note,
                                onDrawingChanged: { drawing in
                                    vm.saveDrawing(drawing, for: question.id)
                                }
                            )
                            .frame(width: geo.size.width * 0.5)
                            .background(Color.backgroundOne)
                            .id(question.id)
                        }
                    }
                    .overlay(
                        Rectangle()
                            .fill(Color.borderColor)
                            .frame(width: 3)
                            .ignoresSafeArea(edges: .bottom),
                        alignment: .center
                    )
                }
                .background(Color.backgroundOne.ignoresSafeArea(edges: .bottom))
            }
            .background(Color.backgroundOne)
            .toolbar(.hidden, for: .navigationBar)
            .navigationBarBackButtonHidden(true)
            .onAppear {
                vm.startTimer()
            }
        }
    }
}

// MARK: - Timer display

struct TimerView: View {
    let secondsRemaining: Int

    var isUrgent: Bool { secondsRemaining < 300 } // < 5 min

    var formatted: String {
        let m = secondsRemaining / 60
        let s = secondsRemaining % 60
        return String(format: "%02d:%02d", m, s)
    }

    var body: some View {
        HStack(spacing: 4) {
            Image(systemName: "clock")
                .font(.system(size: 12, weight: .black))
            Text(formatted)
                .font(.knp(.mono))
        }
        .foregroundStyle(isUrgent ? Color.fontSecondary : Color.fontPrimary)
        .padding(.horizontal, 12)
        .padding(.vertical, 6)
        .background(isUrgent ? Color.errorColor : Color.backgroundTwo)
        .clipShape(RoundedRectangle(cornerRadius: 6))
        .overlay(
            RoundedRectangle(cornerRadius: 6)
                .strokeBorder(Color.borderColor, lineWidth: 3)
        )
    }
}
