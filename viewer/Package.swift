// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "KuulasViewerPackage",
    platforms: [.macOS(.v12)],
    products: [.library(name: "KuulasKit", targets: ["KuulasKit"]),
               .library(name: "KuulasViewer", targets: ["KuulasViewer"])],
    targets: [
        .systemLibrary(name: "CSQLite"),
        .systemLibrary(name: "CZlib"),
        .target(name: "KuulasKit", dependencies: ["CSQLite", "CZlib"]),
        .target(name: "KuulasViewer", dependencies: ["KuulasKit"]),
        .testTarget(name: "KuulasKitTests", dependencies: ["KuulasKit"]),
    ]
)
