// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "AgentOSMobileCore",
    platforms: [
        .iOS(.v16),
        .macOS(.v13),
    ],
    products: [
        .library(name: "AgentOSMobileCore", targets: ["AgentOSMobileCore"]),
    ],
    targets: [
        .target(
            name: "AgentOSMobileCore",
            path: ".",
            exclude: ["README.md", "Tests", "Package.swift", "AgentOSMobileApp.swift", "ContentView.swift", "Info.plist", "project.yml"],
            sources: ["AgentOSMobileCore.swift", "AgentOSKeychain.swift"]
        ),
        .testTarget(
            name: "AgentOSMobileCoreTests",
            dependencies: ["AgentOSMobileCore"],
            path: "Tests"
        ),
    ]
)
