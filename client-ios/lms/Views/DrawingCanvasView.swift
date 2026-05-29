import SwiftUI
import PencilKit

// MARK: - Tool state

private struct DrawingTool: Equatable {
    enum Mode: Equatable { case pen, eraser }
    var mode: Mode = .pen
    var color: DrawingColor = DrawingColor.all[0]
    var thickness: CGFloat = 2

    static let thicknesses: [CGFloat] = [2, 5, 12]
}

/// Named drawing colors — visible on a white canvas.
struct DrawingColor: Equatable, Identifiable {
    let id: String
    let swiftUI: Color
    let ui: UIColor

    static let all: [DrawingColor] = [
        DrawingColor("Brown",  Color(red: 0.192, green: 0.114, blue: 0.082), UIColor(red: 0.192, green: 0.114, blue: 0.082, alpha: 1)),
        DrawingColor("Blue",   Color(red: 0.18,  green: 0.42,  blue: 0.75),  UIColor(red: 0.18,  green: 0.42,  blue: 0.75,  alpha: 1)),
        DrawingColor("Green",  Color(red: 0.01,  green: 0.57,  blue: 0.38),  UIColor(red: 0.01,  green: 0.57,  blue: 0.38,  alpha: 1)),
        DrawingColor("Red",    Color(red: 0.80,  green: 0.15,  blue: 0.18),  UIColor(red: 0.80,  green: 0.15,  blue: 0.18,  alpha: 1)),
        DrawingColor("Orange", Color(red: 0.85,  green: 0.55,  blue: 0.00),  UIColor(red: 0.85,  green: 0.55,  blue: 0.00,  alpha: 1)),
    ]

    init(_ id: String, _ swiftUI: Color, _ ui: UIColor) {
        self.id = id; self.swiftUI = swiftUI; self.ui = ui
    }
}

// MARK: - Public wrapper

struct DrawingCanvasView: View {
    var questionId: UUID
    var note: LocalUserNote
    var onDrawingChanged: (PKDrawing) -> Void

    @State private var tool = DrawingTool()
    @State private var clearTrigger = false

    var body: some View {
        VStack(spacing: 0) {
            DrawingToolbar(tool: $tool, onClear: {
                clearTrigger.toggle()
            })
            .background(Color.backgroundTwo)

            Rectangle().fill(Color.borderColor).frame(height: 3)

            CanvasView(
                questionId: questionId,
                note: note,
                tool: tool,
                clearTrigger: clearTrigger,
                onDrawingChanged: onDrawingChanged
            )
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(Color.backgroundOne)
        }
    }
}

// MARK: - Toolbar

private struct DrawingToolbar: View {
    @Binding var tool: DrawingTool
    var onClear: () -> Void

    var body: some View {
        HStack(spacing: 12) {

            // ── Color swatches ────────────────────────────────────────────────
            HStack(spacing: 6) {
                ForEach(DrawingColor.all) { color in
                    let isPenColor = tool.mode == .pen && tool.color == color

                    Button {
                        tool.color = color
                        tool.mode  = .pen
                    } label: {
                        // Checkmark icon only — background comes from KnPSwatchStyle
                        ZStack {
                            if isPenColor {
                                Image(systemName: "checkmark")
                                    .font(.system(size: 10, weight: .black))
                                    .foregroundStyle(Color.backgroundOne)
                            }
                        }
                        .frame(width: 28, height: 28)
                    }
                    .buttonStyle(KnPSwatchStyle(fill: color.swiftUI, isSelected: isPenColor))
                }
            }

            // ── Separator ─────────────────────────────────────────────────────
            Rectangle().fill(Color.borderColor.opacity(0.3)).frame(width: 2, height: 28)

            // ── Thickness ─────────────────────────────────────────────────────
            HStack(spacing: 6) {
                ForEach(Array(DrawingTool.thicknesses.enumerated()), id: \.offset) { _, size in
                    let isActive = tool.mode == .pen && tool.thickness == size
                    let type: KnPButtonType = isActive ? .filled : .secondary

                    Button {
                        tool.thickness = size
                        tool.mode = .pen
                    } label: {
                        ZStack {
                            Circle()
                                .fill(type.foreground)
                                .frame(
                                    width: min(size * 1.8, 16),
                                    height: min(size * 1.8, 16)
                                )
                        }
                        .frame(width: 28, height: 28)
                    }
                    .buttonStyle(KnPButtonStyle(type: type, cornerRadius: 5, borderWidth: 3))
                }
            }

            // ── Separator ─────────────────────────────────────────────────────
            Rectangle().fill(Color.borderColor.opacity(0.3)).frame(width: 2, height: 28)

            // ── Eraser ────────────────────────────────────────────────────────
            let isEraser = tool.mode == .eraser
            Button {
                tool.mode = .eraser
            } label: {
                Image(systemName: "eraser.fill")
                    .font(.system(size: 13, weight: .bold))
                    .foregroundStyle(isEraser ? KnPButtonType.filled.foreground : KnPButtonType.secondary.foreground)
                    .frame(width: 28, height: 28)
            }
            .buttonStyle(KnPButtonStyle(type: isEraser ? .filled : .secondary, cornerRadius: 5, borderWidth: 3))

            Spacer()

            // ── Clear ─────────────────────────────────────────────────────────
            Button(action: onClear) {
                HStack(spacing: 4) {
                    Image(systemName: "trash")
                        .font(.system(size: 12, weight: .black))
                        .foregroundStyle(.fontPrimary)
                    Text("Clear")
                        .font(.knp(.mono))
                        .foregroundStyle(.fontPrimary)
                }
                .foregroundStyle(KnPButtonType.warning.foreground)
                .padding(.horizontal, 10)
                .frame(minHeight: 28)
            }
            .buttonStyle(KnPButtonStyle(type: .warning, cornerRadius: 5, borderWidth: 3))
        }
        .padding(16)
    }
}

// MARK: - UIViewRepresentable canvas (with zoom + pan)

private struct CanvasView: UIViewRepresentable {
    var questionId: UUID
    var note: LocalUserNote
    var tool: DrawingTool
    var clearTrigger: Bool
    var onDrawingChanged: (PKDrawing) -> Void

    private static let canvasSize = CGSize(width: 2048, height: 2048)

    func makeUIView(context: Context) -> UIScrollView {
        let canvas = PKCanvasView()
        canvas.frame = CGRect(origin: .zero, size: Self.canvasSize)
        canvas.drawingPolicy = .anyInput
        canvas.backgroundColor = .white
        canvas.isScrollEnabled = false
        canvas.delegate = context.coordinator

        if let drawing = try? PKDrawing(data: note.drawingData) {
            canvas.drawing = drawing
        }
        canvas.tool = makePKTool()
        context.coordinator.canvasView = canvas

        let scrollView = UIScrollView()
        scrollView.addSubview(canvas)
        scrollView.contentSize = Self.canvasSize
        scrollView.minimumZoomScale = 0.05
        scrollView.maximumZoomScale = 5.0
        scrollView.delegate = context.coordinator
        scrollView.backgroundColor = UIColor(Color.backgroundOne)
        scrollView.showsHorizontalScrollIndicator = false
        scrollView.showsVerticalScrollIndicator = false
        scrollView.bouncesZoom = true

        // Fit to view once layout is known
        DispatchQueue.main.async {
            let scale = min(
                scrollView.bounds.width / Self.canvasSize.width,
                scrollView.bounds.height / Self.canvasSize.height
            )
            if scale > 0 {
                scrollView.setZoomScale(max(scale, scrollView.minimumZoomScale), animated: false)
            }
        }

        return scrollView
    }

    func updateUIView(_ scrollView: UIScrollView, context: Context) {
        guard let canvas = context.coordinator.canvasView else { return }

        if context.coordinator.currentQuestionId != questionId {
            // Question switched — reload drawing and reset zoom
            context.coordinator.currentQuestionId = questionId
            canvas.drawing = (try? PKDrawing(data: note.drawingData)) ?? PKDrawing()
            let scale = min(
                scrollView.bounds.width / Self.canvasSize.width,
                scrollView.bounds.height / Self.canvasSize.height
            )
            if scale > 0 {
                scrollView.setZoomScale(max(scale, scrollView.minimumZoomScale), animated: false)
            }
            scrollView.contentOffset = .zero
        } else if context.coordinator.lastClearTrigger != clearTrigger {
            // Clear triggered
            context.coordinator.lastClearTrigger = clearTrigger
            canvas.drawing = PKDrawing()
            onDrawingChanged(PKDrawing())
        }

        canvas.tool = makePKTool()
    }

    func makeCoordinator() -> Coordinator {
        Coordinator(questionId: questionId, onChanged: onDrawingChanged)
    }

    private func makePKTool() -> PKTool {
        switch tool.mode {
        case .eraser:
            return PKEraserTool(.bitmap, width: 20)
        case .pen:
            return PKInkingTool(.pen, color: tool.color.ui, width: tool.thickness)
        }
    }

    final class Coordinator: NSObject, PKCanvasViewDelegate, UIScrollViewDelegate {
        var currentQuestionId: UUID
        var lastClearTrigger: Bool = false
        let onChanged: (PKDrawing) -> Void
        weak var canvasView: PKCanvasView?

        init(questionId: UUID, onChanged: @escaping (PKDrawing) -> Void) {
            self.currentQuestionId = questionId
            self.onChanged = onChanged
        }

        func canvasViewDrawingDidChange(_ canvasView: PKCanvasView) {
            onChanged(canvasView.drawing)
        }

        func viewForZooming(in scrollView: UIScrollView) -> UIView? {
            canvasView
        }

        func scrollViewDidZoom(_ scrollView: UIScrollView) {
            // Keep canvas centered while zooming
            let x = max((scrollView.bounds.width - scrollView.contentSize.width) / 2, 0)
            let y = max((scrollView.bounds.height - scrollView.contentSize.height) / 2, 0)
            scrollView.contentInset = UIEdgeInsets(top: y, left: x, bottom: y, right: x)
        }
    }
}
