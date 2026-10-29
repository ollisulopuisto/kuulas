import AppKit
import Quartz
import SwiftUI
import KuulasViewer

final class PreviewViewController: NSViewController, QLPreviewingController {
    override func loadView() { view = NSView() }

    func preparePreviewOfFile(at url: URL, completionHandler handler: @escaping (Error?) -> Void) {
        let host = NSHostingView(rootView: ProjectView(root: url))
        host.translatesAutoresizingMaskIntoConstraints = false
        view.subviews.forEach { $0.removeFromSuperview() }
        view.addSubview(host)
        NSLayoutConstraint.activate([
            host.leadingAnchor.constraint(equalTo: view.leadingAnchor),
            host.trailingAnchor.constraint(equalTo: view.trailingAnchor),
            host.topAnchor.constraint(equalTo: view.topAnchor),
            host.bottomAnchor.constraint(equalTo: view.bottomAnchor),
        ])
        preferredContentSize = NSSize(width: 820, height: 560)
        handler(nil)
    }
}
