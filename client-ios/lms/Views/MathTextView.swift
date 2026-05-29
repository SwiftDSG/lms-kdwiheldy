import SwiftUI
import LaTeXSwiftUI

/// Renders text that may contain LaTeX math delimited by $...$ (inline) or $$...$$ (display).
/// Uses LaTeXSwiftUI for native rendering — no WebKit, no network dependency.
struct MathTextView: View {
    let text: String

    // Wrap a digit immediately before \frac / \dfrac in \text{},
    // e.g. $1\frac{3}{4}$ → $\text{1}\frac{3}{4}$, to prevent the black-block
    // rendering artifact in LaTeXSwiftUI.
    private var processedText: String {
        guard let regex = try? NSRegularExpression(pattern: "(\\d)(\\\\d?frac)") else {
            return text
        }
        let range = NSRange(text.startIndex..., in: text)
        return regex.stringByReplacingMatches(in: text, range: range, withTemplate: "\\\\text{$1}$2")
    }

    var body: some View {
        LaTeX(processedText)
            .processEscapes()
            .blockMode(.alwaysInline)
            .parsingMode(.onlyEquations)
            .imageRenderingMode(.template)
            .errorMode(.error)
            .fixedSize(horizontal: false, vertical: true)
    }
}
