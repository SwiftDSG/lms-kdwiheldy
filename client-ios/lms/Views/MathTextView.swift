import SwiftUI
import LaTeXSwiftUI

/// Renders text that may contain LaTeX math delimited by $...$ (inline) or $$...$$ (display).
/// Uses LaTeXSwiftUI for native rendering — no WebKit, no network dependency.
struct MathTextView: View {
    let text: String

    // Wrap every bare digit sequence inside $...$ in \text{} to prevent
    // LaTeXSwiftUI rendering artifacts. Handles digits anywhere in math mode:
    // bases, exponents (^5 → ^{\text{5}}, ^{5+3} → ^{\text{5}+\text{3}}),
    // fractions, results, etc. Existing \text{...} blocks are left untouched.
    private var processedText: String {
        wrapDigitsInMathSegments(text)
    }

    var body: some View {
        LaTeX(processedText)
            .parsingMode(.onlyEquations)
            .imageRenderingMode(.original)
            .blockMode(.alwaysInline)
            .errorMode(.error)
            .fixedSize(horizontal: false, vertical: true)
    }

    // MARK: - Private helpers

    private func wrapDigitsInMathSegments(_ input: String) -> String {
        var result = ""
        var i = input.startIndex
        var inMath = false
        var segStart = input.startIndex

        while i < input.endIndex {
            if input[i] == "$" {
                if !inMath {
                    result += input[segStart..<i] // text before math
                    result += "$"
                    inMath = true
                    segStart = input.index(after: i)
                } else {
                    result += wrapBareDigitsInMath(String(input[segStart..<i]))
                    result += "$"
                    inMath = false
                    segStart = input.index(after: i)
                }
            }
            i = input.index(after: i)
        }
        // Append any remaining text
        result += input[segStart...]
        return result
    }

    private func wrapBareDigitsInMath(_ math: String) -> String {
        var result = ""
        var i = math.startIndex

        while i < math.endIndex {
            // 1. \text{ ... } — keep as-is, don't re-wrap contents
            if math[i...].hasPrefix("\\text{") {
                let start = i
                i = math.index(i, offsetBy: 6) // skip past \text{
                var depth = 1
                while i < math.endIndex && depth > 0 {
                    if math[i] == "{" { depth += 1 }
                    else if math[i] == "}" { depth -= 1 }
                    i = math.index(after: i)
                }
                result += math[start..<i]
            }
            // 2. ^ followed by a bare digit (no brace): ^5 → ^{\text{5}}
            else if math[i] == "^",
                    let next = math.index(i, offsetBy: 1, limitedBy: math.endIndex),
                    next < math.endIndex,
                    math[next].isNumber {
                result += "^{"
                i = next
                var digits = ""
                while i < math.endIndex && math[i].isNumber {
                    digits.append(math[i])
                    i = math.index(after: i)
                }
                result += "\\text{\(digits)}"
                result += "}"
            }
            // 3. Bare digit sequence → \text{...}
            else if math[i].isNumber {
                var digits = ""
                while i < math.endIndex && math[i].isNumber {
                    digits.append(math[i])
                    i = math.index(after: i)
                }
                result += "\\text{\(digits)}"
            }
            // 4. Pass through unchanged
            else {
                result.append(math[i])
                i = math.index(after: i)
            }
        }
        return result
    }
}
