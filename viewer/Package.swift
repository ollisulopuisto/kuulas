// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "KuulasViewerPackage",
    platforms: [.macOS(.v12)],
    products: [.library(name: "KuulasKit", targets: ["KuulasKit"])],
    targets: [
        .systemLibrary(name: "CSQLite"),
        .systemLibrary(name: "CZlib"),
        .target(name: "KuulasKit", dependencies: ["CSQLite", "CZlib"]),
        .testTarget(name: "KuulasKitTests", dependencies: ["KuulasKit"]),
    ]
)
