# CPNS Quiz — iPad App

SwiftUI iPad application for CPNS exam preparation.

## Setup in Xcode

1. Open Xcode → **File → New → Project**
2. Choose **App** under iOS
3. Set:
   - Product Name: `CPNS-Quiz`
   - Bundle Identifier: `com.yourname.cpns-quiz`
   - Interface: SwiftUI
   - Language: Swift
   - Storage: SwiftData
4. Replace generated source files with the Swift files in `CPNS-Quiz/`
5. Add `PencilKit` framework: Target → Frameworks → `+` → PencilKit

## Info.plist Keys to Add

```xml
<key>API_BASE_URL</key>
<string>https://api.yourdomain.com</string>

<key>DEVICE_API_KEY</key>
<string>your_device_api_key_here</string>
```

## Requirements

- iPad with Apple Pencil support
- iOS 17+ / iPadOS 17+
- Xcode 15+

## Architecture

- **Views/**: SwiftUI views (split layout, question panel, PencilKit canvas)
- **ViewModels/**: `QuizSessionViewModel` — central state for a quiz session
- **Models/**: SwiftData model definitions (local persistence)
- **Services/**: `APIClient` (network) + `SyncManager` (offline sync logic)
