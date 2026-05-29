import SwiftUI

/// Left panel: question navigator (number bubbles) + question content.
struct QuestionPanelView: View {
    @Bindable var vm: QuizSessionViewModel

    var body: some View {
        VStack(spacing: 0) {
            // ── Navigator ─────────────────────────────────────────────────────
            QuestionNavigatorView(vm: vm)
                .padding(.vertical, 16)
                .background(Color.backgroundTwo)

            Rectangle().fill(Color.borderColor).frame(height: 3)

            // ── Question content ───────────────────────────────────────────────
            if let question = vm.currentQuestion {
                ScrollView {
                    QuestionDetailView(question: question, vm: vm)
                        .padding(16)
                }
                .background(Color.backgroundOne)
            } else {
                Spacer()
                Text("No questions available")
                    .font(.knp(.body))
                    .foregroundStyle(Color.fontPrimary.opacity(0.4))
                Spacer()
            }

            // ── Navigation bar ────────────────────────────────────────────────
            Rectangle().fill(Color.borderColor).frame(height: 3)

            HStack(spacing: 12) {
                // Previous
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

                // Submit or Next
                if vm.isLast {
                    Button {
                        Task { await vm.submitSession() }
                    } label: {
                        Text("Submit")
                            .font(.knp(.h5))
                            .foregroundStyle(KnPButtonType.primary.foreground)
                            .padding(.horizontal, 20)
                            .frame(minHeight: 44)
                    }
                    .buttonStyle(KnPButtonStyle(type: .primary))
                    .disabled(vm.isSubmitting)
                    .opacity(vm.isSubmitting ? 0.5 : 1)
                } else {
                    Button { vm.next() } label: {
                        Image(systemName: "chevron.right")
                            .font(.system(size: 16, weight: .black))
                            .foregroundStyle(KnPButtonType.secondary.foreground)
                            .frame(width: 44, height: 44)
                    }
                    .buttonStyle(KnPButtonStyle(type: .secondary))
                }
            }
            .padding(16)
            .background(Color.backgroundOne)
        }
    }
}

// MARK: - Question navigator (numbered bubbles)

struct QuestionNavigatorView: View {
    @Bindable var vm: QuizSessionViewModel

    var body: some View {
        ScrollViewReader { proxy in
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 8) {
                    ForEach(vm.questions.indices, id: \.self) { i in
                        let q = vm.questions[i]
                        let isCurrent  = vm.currentIndex == i
                        let isAnswered = vm.isAnswered(q.id)
                        let type: KnPButtonType = isCurrent ? .filled : (isAnswered ? .primary : .secondary)

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
}

// MARK: - Question detail

struct QuestionDetailView: View {
    let question: LocalQuestion
    @Bindable var vm: QuizSessionViewModel

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
                AsyncImage(url: url) { img in
                    img.resizable().scaledToFit()
                } placeholder: {
                    ProgressView().tint(Color.fontPrimary)
                }
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
            case "MCQ", "TRUE_FALSE":
                OptionsView(question: question, vm: vm)
            case "ESSAY":
                EssayInputView(questionId: question.id, vm: vm)
            default:
                EmptyView()
            }
        }
    }
}

// MARK: - MCQ / True-False options

struct OptionsView: View {
    let question: LocalQuestion
    @Bindable var vm: QuizSessionViewModel

    var sortedOptions: [LocalOption] {
        question.options.sorted { $0.label < $1.label }
    }

    var selectedId: UUID? { vm.answers[question.id]?.selectedOptionId }

    var body: some View {
        VStack(spacing: 8) {
            ForEach(sortedOptions, id: \.id) { opt in
                let isSelected = selectedId == opt.id

                Button {
                    vm.selectOption(opt.id, for: question.id)
                } label: {
                    HStack(spacing: 12) {
                        // Label badge — fills dark when selected
                        Text(opt.label)
                            .font(.knp(.h5))
                            .foregroundStyle(isSelected ? Color.fontSecondary : Color.fontPrimary)
                            .frame(width: 32, height: 32)
                            .background {
                                ZStack {
                                    RoundedRectangle(cornerRadius: 6)
                                        .fill(isSelected ? Color.fontPrimary : Color.backgroundTwo)
                                    RoundedRectangle(cornerRadius: 6)
                                        .strokeBorder(Color.borderColor, lineWidth: 3)
                                }
                            }

                        MathTextView(text: opt.content)
                            .font(.knp(.body))
                            .foregroundStyle(Color.fontPrimary)
                            .frame(maxWidth: .infinity, alignment: .leading)
                    }
                    .padding(12)
                    .frame(maxWidth: .infinity)
                }
                .buttonStyle(KnPButtonStyle(
                    type: isSelected ? .ghost : .secondary,
                    borderWidth: 3
                ))
            }
        }
    }
}

// MARK: - Essay input

struct EssayInputView: View {
    let questionId: UUID
    @Bindable var vm: QuizSessionViewModel

    @State private var text: String = ""

    var body: some View {
        TextEditor(text: $text)
            .font(.knp(.body))
            .foregroundStyle(Color.fontPrimary)
            .frame(minHeight: 120)
            .padding(10)
            .background(Color.backgroundOne)
            .clipShape(RoundedRectangle(cornerRadius: 8))
            .overlay(
                RoundedRectangle(cornerRadius: 8)
                    .strokeBorder(Color.borderColor, lineWidth: 3)
            )
            .onChange(of: text) { _, new in
                vm.setEssayText(new, for: questionId)
            }
            .onAppear {
                text = vm.answers[questionId]?.essayText ?? ""
            }
    }
}
