import SwiftUI

/// Full-screen review screen shown after a quiz is submitted.
struct QuizResultView: View {
    @Bindable var vm: QuizSessionViewModel
    let result: QuizResult
    var onRetry: () -> Void

    @Environment(\.dismiss) private var dismiss

    private var gradeType: KnPButtonType {
        switch result.percentage {
        case 80...: return .primary
        case 60...: return .filled
        case 40...: return .warning
        default:    return .error
        }
    }

    private var gradeName: String {
        switch result.percentage {
        case 80...: return "Excellent"
        case 60...: return "Good"
        case 40...: return "Fair"
        default:    return "Keep Practicing"
        }
    }

    var body: some View {
        VStack(spacing: 0) {
            // ── Custom header ──────────────────────────────────────────────────
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
                    
                    Button(action: onRetry) {
                        HStack(spacing: 4) {
                            Image(systemName: "arrow.counterclockwise")
                                .font(.system(size: 12, weight: .black))
                            Text("Retry")
                                .font(.knp(.h6))
                        }
                        .foregroundStyle(KnPButtonType.ghost.foreground)
                        .padding(.horizontal, 10)
                        .frame(minHeight: 32)
                    }
                    .buttonStyle(KnPButtonStyle(type: .ghost, borderWidth: 3))
                }
                VStack(spacing: 1) {
                    Text(vm.quiz.title)
                        .font(.knp(.h5))
                        .foregroundStyle(Color.fontPrimary)
                        .lineLimit(1)
                    Text("Review Answers")
                        .font(.knp(.caption))
                        .foregroundStyle(Color.fontPrimary.opacity(0.5))
                }
            }
            .padding(16)
            .background(Color.backgroundOne.ignoresSafeArea(edges: .top))

            Rectangle().fill(Color.borderColor).frame(height: 3)

            scoreStrip
            Rectangle().fill(Color.borderColor).frame(height: 3)

            GeometryReader { geo in
                HStack(spacing: 0) {
                    reviewPanel
                        .frame(width: geo.size.width * 0.5)
                    canvasPanel(width: geo.size.width * 0.5)
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
    }

    // ── Score strip ───────────────────────────────────────────────────────────

    private var scoreStrip: some View {
        HStack {
            HStack(spacing: 6) {
                Image(systemName: "star.fill")
                    .font(.system(size: 12, weight: .black))
                Text(gradeName)
                    .font(.knp(.h5))
            }
            .foregroundStyle(gradeType.foreground)
            .padding(.horizontal, 12)
            .padding(.vertical, 6)
            .background {
                ZStack {
                    RoundedRectangle(cornerRadius: 6).fill(gradeType.fill)
                    RoundedRectangle(cornerRadius: 6).strokeBorder(Color.borderColor, lineWidth: 3)
                }
            }

            Spacer()

            Text("\(result.score) / \(result.maxScore) pts")
                .font(.knp(.h6))
                .foregroundStyle(Color.fontPrimary.opacity(0.6))
            Text("·")
                .foregroundStyle(Color.fontPrimary.opacity(0.3))
            Text("\(result.percentage)%")
                .font(.knp(.h4))
                .foregroundStyle(gradeType.fill)
        }
        .padding(16)
        .background(Color.backgroundOne)
    }

    // ── Left panel ────────────────────────────────────────────────────────────

    private var reviewPanel: some View {
        VStack(spacing: 0) {
            ResultNavigatorView(vm: vm, questionStatus: questionStatus)
                .padding(.vertical, 16)
                .background(Color.backgroundTwo)

            Rectangle().fill(Color.borderColor).frame(height: 3)

            if let question = vm.currentQuestion {
                ScrollView {
                    ReviewQuestionDetailView(
                        question: question,
                        selectedOptionId: vm.answers[question.id]?.selectedOptionId,
                        essayText: vm.answers[question.id]?.essayText,
                        vm: vm
                    )
                    .padding(16)
                }
                .background(Color.backgroundOne)
            } else {
                Spacer()
            }

            Rectangle().fill(Color.borderColor).frame(height: 3)

            HStack {
                Button { vm.previous() } label: {
                    Image(systemName: "chevron.left")
                        .font(.system(size: 16, weight: .black))
                        .foregroundStyle(KnPButtonType.secondary.foreground)
                        .frame(width: 44, height: 44)
                }
                .buttonStyle(KnPButtonStyle(type: .secondary))
                .disabled(vm.isFirst)
                .opacity(vm.isFirst ? 0.3 : 1)

                Spacer()
                Text("\(vm.currentIndex + 1) / \(vm.questions.count)")
                    .font(.knp(.h6))
                    .foregroundStyle(Color.fontPrimary.opacity(0.6))
                Spacer()

                Button { vm.next() } label: {
                    Image(systemName: "chevron.right")
                        .font(.system(size: 16, weight: .black))
                        .foregroundStyle(KnPButtonType.secondary.foreground)
                        .frame(width: 44, height: 44)
                }
                .buttonStyle(KnPButtonStyle(type: .secondary))
                .disabled(vm.isLast)
                .opacity(vm.isLast ? 0.3 : 1)
            }
            .padding(16)
            .background(Color.backgroundOne)
        }
    }

    // ── Right panel ───────────────────────────────────────────────────────────

    @ViewBuilder
    private func canvasPanel(width: CGFloat) -> some View {
        if let question = vm.currentQuestion {
            let note = vm.note(for: question.id)
            DrawingCanvasView(
                questionId: question.id,
                note: note,
                onDrawingChanged: { vm.saveDrawing($0, for: question.id) }
            )
            .frame(width: width)
            .background(Color.backgroundOne)
            .id(question.id)
            .overlay {
                if vm.aiExplanationLoading.contains(question.id) {
                    VStack(spacing: 12) {
                        ProgressView().tint(Color.fontPrimary).scaleEffect(1.5)
                        Text("Generating AI Explanation...")
                            .font(.knp(.body))
                            .foregroundStyle(Color.fontPrimary.opacity(0.6))
                    }
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                    .background(Color.backgroundOne)
                } else if vm.aiExplanationVisible.contains(question.id),
                          let result = vm.aiExplanations[question.id] {
                    AIExplanationOverlay(
                        explanation: result.aiExplanation,
                        tip: result.aiTip
                    ) {
                        vm.dismissAIExplanation(for: question.id)
                    }
                }
            }
        }
    }

    // ── Answer status ─────────────────────────────────────────────────────────

    enum AnswerStatus { case correct, wrong, unanswered }

    func questionStatus(_ question: LocalQuestion) -> AnswerStatus {
        guard let answer = vm.answers[question.id],
              let optId = answer.selectedOptionId,
              let opt = question.options.first(where: { $0.id == optId }) else { return .unanswered }
        let hasCorrect = question.options.contains { $0.isCorrect }
        if !hasCorrect { return .correct }
        return opt.isCorrect ? .correct : .wrong
    }
}

// MARK: - Result Navigator

private struct ResultNavigatorView: View {
    @Bindable var vm: QuizSessionViewModel
    let questionStatus: (LocalQuestion) -> QuizResultView.AnswerStatus

    var body: some View {
        ScrollViewReader { proxy in
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 8) {
                    ForEach(vm.questions.indices, id: \.self) { i in
                        let q = vm.questions[i]
                        let isCurrent = vm.currentIndex == i
                        let status    = questionStatus(q)
                        let type      = bubbleType(status: status, current: isCurrent)

                        Button {
                            vm.goTo(index: i)
                            withAnimation { proxy.scrollTo(i, anchor: .center) }
                        } label: {
                            Text("\(i + 1)")
                                .font(.knp(.h6))
                                .foregroundStyle(type.foreground)
                                .frame(width: 28, height: 28)
                        }
                        .buttonStyle(KnPButtonStyle(type: type, borderWidth: 3))
                        .id(i)
                    }
                }
                .padding(.horizontal, 16)
            }
            .onChange(of: vm.currentIndex) { _, new in
                withAnimation { proxy.scrollTo(new, anchor: .center) }
            }
        }
    }

    private func bubbleType(status: QuizResultView.AnswerStatus, current: Bool) -> KnPButtonType {
        if current { return .filled }
        switch status {
        case .correct:    return .primary
        case .wrong:      return .error
        case .unanswered: return .secondary
        }
    }
}

// MARK: - Review Question Detail

private struct ReviewQuestionDetailView: View {
    let question: LocalQuestion
    let selectedOptionId: UUID?
    let essayText: String?
    @Bindable var vm: QuizSessionViewModel

    private var hasCorrectOptions: Bool {
        question.options.contains { $0.isCorrect }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack {
                Text("Question \(question.position)")
                    .font(.knp(.caption))
                    .foregroundStyle(Color.fontPrimary.opacity(0.5))
                Spacer()
                KNPBadge(text: question.type, color: .calmColor)
            }

            if let urlStr = question.imageURL, let url = URL(string: urlStr) {
                AsyncImage(url: url) { img in img.resizable().scaledToFit() }
                    placeholder: { ProgressView().tint(Color.fontPrimary) }
                    .frame(maxHeight: 200)
                    .clipShape(RoundedRectangle(cornerRadius: 8))
                    .overlay(
                        RoundedRectangle(cornerRadius: 8)
                            .strokeBorder(Color.borderColor, lineWidth: 3)
                    )
            }

            MathTextView(text: question.content)
                .font(.knp(.body))
                .foregroundStyle(Color.fontPrimary)

            switch question.type {
            case "MCQ", "TRUE_FALSE", "IMAGE":
                ReviewOptionsView(
                    options: question.options,
                    selectedId: selectedOptionId,
                    hasCorrectOptions: hasCorrectOptions
                )
            case "ESSAY":
                VStack(alignment: .leading, spacing: 8) {
                    HStack(spacing: 6) {
                        Image(systemName: "pencil")
                            .font(.system(size: 12, weight: .black))
                        Text("Your Answer")
                            .font(.knp(.h6))
                    }
                    .foregroundStyle(Color.fontPrimary.opacity(0.5))

                    if let text = essayText, !text.isEmpty {
                        Text(text)
                            .font(.knp(.body))
                            .foregroundStyle(Color.fontPrimary)
                            .padding(12)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .background(Color.backgroundTwo)
                            .clipShape(RoundedRectangle(cornerRadius: 8))
                            .overlay(
                                RoundedRectangle(cornerRadius: 8)
                                    .strokeBorder(Color.borderColor.opacity(0.4), lineWidth: 3)
                            )
                    } else {
                        Text("No answer provided")
                            .font(.knp(.body))
                            .foregroundStyle(Color.fontPrimary.opacity(0.4))
                            .padding(12)
                    }
                }
            default:
                EmptyView()
            }

            if let explanation = question.explanation, !explanation.isEmpty {
                VStack(alignment: .leading, spacing: 8) {
                    HStack(spacing: 6) {
                        Image(systemName: "lightbulb.fill")
                            .font(.system(size: 12, weight: .black))
                            .foregroundStyle(.fontPrimary)
                        Text("Explanation")
                            .font(.knp(.h6))
                            .foregroundStyle(.fontPrimary)
                    }
                    .foregroundStyle(KnPButtonType.warning.foreground)
                    .padding(.horizontal, 10)
                    .padding(.vertical, 6)
                    .background {
                        ZStack {
                            RoundedRectangle(cornerRadius: 6).fill(KnPButtonType.warning.fill)
                            RoundedRectangle(cornerRadius: 6).strokeBorder(Color.borderColor, lineWidth: 3)
                        }
                    }

                    MathTextView(text: explanation)
                        .font(.knp(.body))
                        .foregroundStyle(Color.fontPrimary)
                }
                .padding(12)
                .background(Color.warningColor.opacity(0.1))
                .clipShape(RoundedRectangle(cornerRadius: 8))
                .overlay(
                    RoundedRectangle(cornerRadius: 8)
                        .strokeBorder(Color.borderColor.opacity(0.3), lineWidth: 3)
                )
            }

            aiExplanationTrigger
        }
    }

    @ViewBuilder
    private var aiExplanationTrigger: some View {
        if !question.subtype.needsMlExplain {
            EmptyView()
        } else if vm.aiExplanationLoading.contains(question.id) {
            HStack(spacing: 8) {
                ProgressView().tint(Color.fontPrimary)
                Text("Generating...")
                    .font(.knp(.body))
                    .foregroundStyle(Color.fontPrimary.opacity(0.5))
            }
        } else {
            Button {
                Task { await vm.fetchAIExplanation(for: question) }
            } label: {
                HStack(spacing: 6) {
                    Image(systemName: "brain")
                        .font(.system(size: 12, weight: .black))
                    Text(vm.aiExplanations[question.id] != nil ? "Show AI Explanation" : "Get AI Explanation")
                        .font(.knp(.h6))
                }
                .foregroundStyle(KnPButtonType.ghost.foreground)
                .padding(.horizontal, 10)
                .frame(minHeight: 36)
            }
            .buttonStyle(KnPButtonStyle(type: .ghost, borderWidth: 3))
        }
    }
}

// MARK: - AI Explanation overlay (right panel)

private struct AIExplanationOverlay: View {
    let explanation: String
    let tip: String
    let onDismiss: () -> Void

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                HStack(spacing: 6) {
                    Image(systemName: "brain")
                        .font(.system(size: 12, weight: .black))
                    Text("AI Explanation")
                        .font(.knp(.h6))
                }
                .foregroundStyle(KnPButtonType.filled.foreground)
                .padding(.horizontal, 10)
                .frame(height: 28)
                .background {
                    ZStack {
                        RoundedRectangle(cornerRadius: 6).fill(KnPButtonType.filled.fill)
                        RoundedRectangle(cornerRadius: 6).strokeBorder(Color.borderColor, lineWidth: 3)
                    }
                }

                Spacer()

                Button(action: onDismiss) {
                    Image(systemName: "xmark")
                        .font(.system(size: 12, weight: .black))
                        .foregroundStyle(KnPButtonType.secondary.foreground)
                        .frame(width: 28, height: 28)
                }
                .buttonStyle(KnPButtonStyle(type: .secondary, borderWidth: 3))
            }
            .padding(16)
            .background(Color.backgroundTwo)

            Rectangle().fill(Color.borderColor).frame(height: 3)

            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    MathTextView(text: explanation)
                        .font(.knp(.body))
                        .foregroundStyle(Color.fontPrimary)
                        .frame(maxWidth: .infinity, alignment: .leading)

                    if !tip.isEmpty {
                        VStack(alignment: .leading, spacing: 8) {
                            HStack(spacing: 6) {
                                Image(systemName: "lightbulb.fill")
                                    .font(.system(size: 12, weight: .black))
                                    .foregroundStyle(.fontPrimary)
                                Text("Study Tip")
                                    .font(.knp(.h6))
                                    .foregroundStyle(.fontPrimary)
                            }
                            .foregroundStyle(KnPButtonType.warning.foreground)
                            .padding(.horizontal, 10)
                            .frame(height: 28)
                            .background {
                                ZStack {
                                    RoundedRectangle(cornerRadius: 6).fill(KnPButtonType.warning.fill)
                                    RoundedRectangle(cornerRadius: 6).strokeBorder(Color.borderColor, lineWidth: 3)
                                }
                            }

                            MathTextView(text: tip)
                                .font(.knp(.body))
                                .foregroundStyle(Color.fontPrimary)
                                .frame(maxWidth: .infinity, alignment: .leading)
                        }
                        .padding(12)
                        .background(Color.warningColor.opacity(0.1))
                        .clipShape(RoundedRectangle(cornerRadius: 8))
                        .overlay(
                            RoundedRectangle(cornerRadius: 8)
                                .strokeBorder(Color.borderColor.opacity(0.3), lineWidth: 3)
                        )
                    }
                }
                .padding(16)
            }
            .background(Color.backgroundOne)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
        .background(Color.backgroundOne)
    }
}

// MARK: - Review Options (read-only — no button interaction)

private struct ReviewOptionsView: View {
    let options: [LocalOption]
    let selectedId: UUID?
    let hasCorrectOptions: Bool

    var sortedOptions: [LocalOption] { options.sorted { $0.label < $1.label } }

    var body: some View {
        VStack(spacing: 8) {
            ForEach(sortedOptions, id: \.id) { opt in
                let isSelected = selectedId == opt.id
                let isCorrect  = hasCorrectOptions && opt.isCorrect
                let isWrong    = isSelected && hasCorrectOptions && !opt.isCorrect
                let rowType    = rowButtonType(correct: isCorrect, wrong: isWrong, selected: isSelected)

                HStack(spacing: 12) {
                    // Label square
                    ZStack {
                        RoundedRectangle(cornerRadius: 6).fill(rowType.fill)
                        RoundedRectangle(cornerRadius: 6).strokeBorder(Color.borderColor, lineWidth: 3)

                        if isCorrect {
                            Image(systemName: "checkmark")
                                .font(.system(size: 12, weight: .black))
                                .foregroundStyle(KnPButtonType.primary.foreground)
                        } else if isWrong {
                            Image(systemName: "xmark")
                                .font(.system(size: 12, weight: .black))
                                .foregroundStyle(KnPButtonType.error.foreground)
                        } else if isSelected {
                            Image(systemName: "checkmark")
                                .font(.system(size: 12, weight: .black))
                                .foregroundStyle(KnPButtonType.filled.foreground)
                        } else {
                            Text(opt.label)
                                .font(.knp(.h5))
                                .foregroundStyle(Color.fontPrimary)
                        }
                    }
                    .frame(width: 32, height: 32)

                    if let url = URL(string: opt.content), opt.content.hasPrefix("http") {
                        AsyncImage(url: url) { img in
                            img.resizable().scaledToFit()
                        } placeholder: {
                            ProgressView().tint(Color.fontPrimary)
                        }
                        .frame(height: 80)
                        .frame(maxWidth: .infinity, alignment: .leading)
                    } else {
                        MathTextView(text: opt.content)
                            .font(.knp(.body))
                            .foregroundStyle(Color.fontPrimary)
                            .frame(maxWidth: .infinity, alignment: .leading)
                    }

                    if hasCorrectOptions {
                        if isCorrect {
                            Text("+5 pts")
                                .font(.knp(.h6))
                                .foregroundStyle(KnPButtonType.primary.foreground)
                                .padding(.horizontal, 8)
                                .padding(.vertical, 4)
                                .background {
                                    ZStack {
                                        RoundedRectangle(cornerRadius: 4).fill(KnPButtonType.primary.fill)
                                        RoundedRectangle(cornerRadius: 4).strokeBorder(Color.borderColor, lineWidth: 3)
                                    }
                                }
                        }
                    } else {
                        Text("\(opt.score) pts")
                            .font(.knp(.h6))
                            .foregroundStyle(isSelected ? Color.fontPrimary : Color.fontPrimary.opacity(0.4))
                    }
                }
                .padding(12)
                .frame(maxWidth: .infinity)
                .background {
                    ZStack {
                        RoundedRectangle(cornerRadius: 8).fill(rowType.fill.opacity(isSelected || isCorrect ? 1 : 0))
                        RoundedRectangle(cornerRadius: 8).strokeBorder(Color.borderColor.opacity(rowBorderOpacity(correct: isCorrect, wrong: isWrong, selected: isSelected)), lineWidth: 3)
                    }
                }
            }
        }
    }

    private func rowButtonType(correct: Bool, wrong: Bool, selected: Bool) -> KnPButtonType {
        if correct  { return .primary }
        if wrong    { return .error }
        if selected { return .filled }
        return .secondary
    }

    private func rowBorderOpacity(correct: Bool, wrong: Bool, selected: Bool) -> Double {
        (correct || wrong || selected) ? 1.0 : 0.25
    }
}
