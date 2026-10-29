import AppKit
import SwiftUI
import KuulasViewer

@main
final class AppDelegate: NSObject, NSApplicationDelegate {
    private var windows: [NSWindow] = []

    func applicationDidFinishLaunching(_ notification: Notification) {
        let menu = NSMenu()
        let application = NSMenuItem()
        let applicationMenu = NSMenu()
        applicationMenu.addItem(withTitle: "Quit Kuulas Viewer", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        application.submenu = applicationMenu
        menu.addItem(application)
        let file = NSMenuItem()
        let fileMenu = NSMenu(title: "File")
        fileMenu.addItem(withTitle: "Open…", action: #selector(openDocument(_:)), keyEquivalent: "o")
        file.submenu = fileMenu
        menu.addItem(file)
        NSApp.mainMenu = menu
        NSApp.setActivationPolicy(.regular)
        NSApp.activate(ignoringOtherApps: true)
        if windows.isEmpty { openDocument(nil) }
    }

    @objc func openDocument(_ sender: Any?) {
        let panel = NSOpenPanel()
        panel.canChooseFiles = true
        panel.canChooseDirectories = true
        panel.treatsFilePackagesAsDirectories = false
        if panel.runModal() == .OK, let url = panel.url { open(url) }
    }

    func application(_ application: NSApplication, open urls: [URL]) {
        for url in urls { open(url) }
    }

    private func open(_ url: URL) {
        let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 820, height: 560),
            styleMask: [.titled, .closable, .resizable, .miniaturizable], backing: .buffered, defer: false)
        window.title = "Kuulas Viewer: " + url.deletingPathExtension().lastPathComponent
        window.contentView = NSHostingView(rootView: ProjectView(root: url))
        window.isReleasedWhenClosed = false
        window.center()
        window.makeKeyAndOrderFront(nil)
        windows.append(window)
    }
}
