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

            GeometryReader { geo in
                CanvasView(
                    questionId: questionId,
                    note: note,
                    tool: tool,
                    clearTrigger: clearTrigger,
                    availableSize: geo.size,
                    onDrawingChanged: onDrawingChanged
                )
            }
            .ignoresSafeArea(.container, edges: .bottom)
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
    var availableSize: CGSize
    var onDrawingChanged: (PKDrawing) -> Void

    // Canvas is 2× the available view in each dimension (same aspect ratio),
    // giving the user 4× the writing area before needing to scroll.
    private var canvasSize: CGSize {
        guard availableSize.width > 0, availableSize.height > 0 else {
            return CGSize(width: 2048, height: 2048)
        }
        return CGSize(width: availableSize.width * 2, height: availableSize.height * 2)
    }

    func makeUIView(context: Context) -> UIScrollView {
        let size = canvasSize
        context.coordinator.storedCanvasSize = size

        let canvas = PKCanvasView()
        canvas.frame = CGRect(origin: .zero, size: size)
        canvas.drawingPolicy = .anyInput
        canvas.backgroundColor = UIColor(Color.backgroundOne)
        canvas.isScrollEnabled = false
        canvas.delegate = context.coordinator

        if let drawing = try? PKDrawing(data: note.drawingData) {
            canvas.drawing = drawing
        }
        canvas.tool = makePKTool(zoomScale: 1)
        context.coordinator.canvasView = canvas

        let scrollView = UIScrollView()
        scrollView.addSubview(canvas)
        scrollView.contentSize = size
        scrollView.minimumZoomScale = 0.01  // updated after layout
        scrollView.maximumZoomScale = 5.0
        scrollView.delegate = context.coordinator
        context.coordinator.scrollView = scrollView
        scrollView.backgroundColor = UIColor(Color.backgroundTwo)
        scrollView.showsHorizontalScrollIndicator = false
        scrollView.showsVerticalScrollIndicator = false
        scrollView.bouncesZoom = true

        // Set minimum zoom = fit-to-view (full canvas visible), start at 1×
        DispatchQueue.main.async {
            let minScale = min(
                scrollView.bounds.width / size.width,
                scrollView.bounds.height / size.height
            )
            if minScale > 0 { scrollView.minimumZoomScale = minScale }
            scrollView.setZoomScale(1.0, animated: false)
            scrollView.contentOffset = .zero
        }

        return scrollView
    }

    func updateUIView(_ scrollView: UIScrollView, context: Context) {
        guard let canvas = context.coordinator.canvasView else { return }

        // Keep minimum zoom = fit-to-view using the stored canvas size
        let storedSize = context.coordinator.storedCanvasSize
        if storedSize.width > 0 {
            let minScale = min(
                scrollView.bounds.width / storedSize.width,
                scrollView.bounds.height / storedSize.height
            )
            if minScale > 0 { scrollView.minimumZoomScale = minScale }
        }

        if context.coordinator.currentQuestionId != questionId {
            // Question switched — reload drawing and reset zoom to 1×
            context.coordinator.currentQuestionId = questionId
            canvas.drawing = (try? PKDrawing(data: note.drawingData)) ?? PKDrawing()
            scrollView.setZoomScale(max(1.0, scrollView.minimumZoomScale), animated: false)
            scrollView.contentOffset = .zero
        } else if context.coordinator.lastClearTrigger != clearTrigger {
            // Clear triggered
            context.coordinator.lastClearTrigger = clearTrigger
            canvas.drawing = PKDrawing()
            onDrawingChanged(PKDrawing())
        }

        context.coordinator.currentTool = tool
        canvas.tool = makePKTool(zoomScale: scrollView.zoomScale)
    }

    func makeCoordinator() -> Coordinator {
        Coordinator(questionId: questionId, onChanged: onDrawingChanged)
    }

    private func makePKTool(zoomScale: CGFloat) -> PKTool {
        let scale = max(zoomScale, 0.01)
        switch tool.mode {
        case .eraser:
            return PKEraserTool(.bitmap, width: 20 / scale)
        case .pen:
            return PKInkingTool(.pen, color: tool.color.ui, width: tool.thickness / scale)
        }
    }

    final class Coordinator: NSObject, PKCanvasViewDelegate, UIScrollViewDelegate {
        var currentQuestionId: UUID
        var lastClearTrigger: Bool = false
        let onChanged: (PKDrawing) -> Void
        weak var canvasView: PKCanvasView?
        weak var scrollView: UIScrollView?
        var currentTool: DrawingTool = DrawingTool()
        var storedCanvasSize: CGSize = .zero

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
            scrollView.contentInset = .zero
            guard let canvas = canvasView else { return }
            let scale = max(scrollView.zoomScale, 0.01)
            switch currentTool.mode {
            case .eraser:
                canvas.tool = PKEraserTool(.bitmap, width: 20 / scale)
            case .pen:
                canvas.tool = PKInkingTool(.pen, color: currentTool.color.ui, width: currentTool.thickness / scale)
            }
        }
    }
}
