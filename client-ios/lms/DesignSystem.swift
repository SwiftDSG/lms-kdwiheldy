import SwiftUI

// MARK: - Color Palette
//
// fontPrimary, fontSecondary, backgroundOne, backgroundTwo are auto-generated
// by Xcode from the asset catalog (ASSETCATALOG_COMPILER_GENERATE_SWIFT_ASSET_SYMBOL_EXTENSIONS).
// Only declare aliases that Xcode doesn't generate (suffixed names used in views).

extension Color {
    static let borderColor  = Color("border-color")   // #311D15 dark brown
    static let successColor = Color("success-color")  // #03C583 green
    static let errorColor   = Color("error-color")    // #FF9093 red
    static let warningColor = Color("warning-color")  // #FFD890 orange
    static let calmColor    = Color("calm-color")     // #AED1F6 light blue
}

// MARK: - Typography

extension Font {
    static func knp(_ style: KNPTextStyle) -> Font {
        .custom(style.fontName, size: style.size)
    }

    enum KNPTextStyle {
        case h1, h2, h3, h4, h5, h6, body, caption, mono

        var fontName: String {
            switch self {
            case .h1, .h2, .h3: return "Montserrat-Black"
            case .h4:            return "Montserrat-ExtraBold"
            case .h5:            return "Montserrat-Bold"
            case .h6:            return "Montserrat-SemiBold"
            case .body:          return "Montserrat-Medium"
            case .caption:       return "Montserrat-Regular"
            case .mono:          return "Montserrat-Bold"
            }
        }

        var size: CGFloat {
            switch self {
            case .h1:      return 24
            case .h2:      return 20
            case .h3:      return 18
            case .h4:      return 16
            case .h5:      return 14
            case .h6:      return 13
            case .body:    return 15
            case .caption: return 13
            case .mono:    return 14
            }
        }
    }
}

// MARK: - Button Type

/// Mirrors KNP's ButtonType enum. Defines the fill/foreground pair for each variant.
enum KnPButtonType {
    case primary    // success green bg, white fg
    case secondary  // white bg, dark fg
    case warning    // orange bg, white fg
    case ghost      // gray bg, dark fg
    case filled     // dark brown bg, white fg  (active / currently-selected)
    case error      // light red bg, dark fg    (wrong-answer indicators)

    var fill: Color {
        switch self {
        case .primary:   return .successColor
        case .secondary: return .backgroundOne
        case .warning:   return .warningColor
        case .ghost:     return .backgroundTwo
        case .filled:    return .fontPrimary
        case .error:     return .errorColor
        }
    }

    var foreground: Color {
        switch self {
        case .primary, .warning, .filled: return .fontSecondary
        case .secondary, .ghost, .error:  return .fontPrimary
        }
    }
}

// MARK: - KnPButtonStyle (mirrors KnPButtonStyle from KNP project)
//
// The label provides: content (text / icon), foreground color, and frame size.
// The style provides: background fill + border + press overlay + scale animation.
// Never override font, foreground, or frame inside makeBody.

struct KnPButtonStyle: ButtonStyle {
    var type: KnPButtonType = .secondary
    var cornerRadius: CGFloat = 6
    var borderWidth: CGFloat = 3

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .background {
                ZStack {
                    RoundedRectangle(cornerRadius: cornerRadius)
                        .fill(type.fill)
                    RoundedRectangle(cornerRadius: cornerRadius)
                        .strokeBorder(Color.borderColor, lineWidth: borderWidth)
                    // Press overlay — matches KNP's 0.1 opacity dark press effect
                    RoundedRectangle(cornerRadius: cornerRadius)
                        .fill(Color.fontPrimary)
                        .opacity(configuration.isPressed ? 0.1 : 0)
                }
            }
            .scaleEffect(configuration.isPressed ? 0.95 : 1)
            .animation(.spring(duration: 0.25), value: configuration.isPressed)
    }
}

// MARK: - KnPSwatchStyle (for drawing canvas color swatches)
//
// Same pattern as KnPButtonStyle but fill is a custom drawing color,
// and the press overlay lightens instead of darkening.

struct KnPSwatchStyle: ButtonStyle {
    var fill: Color
    var isSelected: Bool

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .background {
                ZStack {
                    RoundedRectangle(cornerRadius: 5)
                        .fill(fill)
                    RoundedRectangle(cornerRadius: 5)
                        .strokeBorder(Color.borderColor, lineWidth: 3)
                    RoundedRectangle(cornerRadius: 5)
                        .fill(Color.backgroundOne)
                        .opacity(configuration.isPressed ? 0.2 : 0)
                }
            }
            .scaleEffect(configuration.isPressed ? 0.92 : 1)
            .animation(.spring(duration: 0.2), value: configuration.isPressed)
    }
}

// MARK: - KNPCard (non-interactive container)

struct KNPCard: ViewModifier {
    var radius: CGFloat = 12
    var borderWidth: CGFloat = 3

    func body(content: Content) -> some View {
        content
            .background(Color.backgroundOne)
            .clipShape(RoundedRectangle(cornerRadius: radius))
            .overlay(
                RoundedRectangle(cornerRadius: radius)
                    .strokeBorder(Color.borderColor, lineWidth: borderWidth)
            )
    }
}

extension View {
    func knpCard(radius: CGFloat = 12, borderWidth: CGFloat = 3) -> some View {
        modifier(KNPCard(radius: radius, borderWidth: borderWidth))
    }
}

// MARK: - Toolbar buttons
//
// Navigation bar items on iOS 26 receive a system glass layer that sits outside
// the reach of ButtonStyle. These components bypass that by placing the KnP
// background inside the label and using .buttonStyle(.plain).

/// Icon + text toolbar button (e.g. "‹ Back", "↺ Retry").
struct KnPToolbarTextButton: View {
    let icon: String
    let text: String
    let type: KnPButtonType
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: 4) {
                Image(systemName: icon)
                    .font(.system(size: 12, weight: .black))
                Text(text)
                    .font(.knp(.h6))
            }
            .foregroundStyle(type.foreground)
            .padding(.horizontal, 10)
            .frame(minHeight: 32)
            .background {
                ZStack {
                    RoundedRectangle(cornerRadius: 6).fill(type.fill)
                    RoundedRectangle(cornerRadius: 6).strokeBorder(Color.borderColor, lineWidth: 3)
                }
            }
        }
        .buttonStyle(.plain)
    }
}

/// Icon-only square toolbar button, with optional loading state.
struct KnPToolbarIconButton: View {
    let icon: String
    let type: KnPButtonType
    var isLoading: Bool = false
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            Group {
                if isLoading {
                    ProgressView()
                        .tint(type.foreground)
                        .scaleEffect(0.8)
                        .frame(width: 16, height: 16)
                } else {
                    Image(systemName: icon)
                        .font(.system(size: 14, weight: .black))
                }
            }
            .foregroundStyle(type.foreground)
            .frame(width: 34, height: 34)
            .background {
                ZStack {
                    RoundedRectangle(cornerRadius: 6).fill(type.fill)
                    RoundedRectangle(cornerRadius: 6).strokeBorder(Color.borderColor, lineWidth: 3)
                }
            }
        }
        .buttonStyle(.plain)
    }
}

// MARK: - KNPBadge (non-interactive display chip)

struct KNPBadge: View {
    let text: String
    var color: Color = .calmColor

    var body: some View {
        Text(text)
            .font(.knp(.h6))
            .foregroundStyle(Color.fontPrimary)
            .padding(.horizontal, 10)
            .padding(.vertical, 5)
            .background(color)
            .clipShape(RoundedRectangle(cornerRadius: 6))
            .overlay(
                RoundedRectangle(cornerRadius: 6)
                    .strokeBorder(Color.borderColor, lineWidth: 3)
            )
    }
}
