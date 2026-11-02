import SwiftUI
import KuulasKit

/// One native view shared by the application and Quick Look extension.
/// UI is not visually accepted until checked on macOS at actual pixels.
public struct ProjectView: View {
    let root: URL
    @State private var snapshot: ProjectSnapshot?
    @State private var error: String?
    @State private var editID = "main"
    @StateObject private var playback = PlaybackController()

    public init(root: URL) { self.root = root }

    private var selected: EditSnapshot? {
        snapshot?.edits.first { $0.id == editID } ?? snapshot?.edits.first
    }
    private var length: Int {
        selected.map { PlaybackPosition.length($0.state) } ?? 0
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text(snapshot?.name ?? root.deletingPathExtension().lastPathComponent)
                .font(.title2).textSelection(.enabled)
            Text("Read-only preview. The project is never changed.")
                .foregroundColor(.secondary)
            if let error { Text(error).foregroundColor(.red).textSelection(.enabled) }
            if let snapshot, let selected {
                Picker("Edit", selection: $editID) {
                    ForEach(snapshot.edits, id: \.id) { edit in
                        Text(edit.name + (edit.archived ? " (archived)" : "")).tag(edit.id)
                    }
                }
                .onChange(of: editID) { _ in playback.reset() }
                ScrollView {
                    VStack(alignment: .leading, spacing: 8) {
                        ForEach(Array((selected.state["tracks"] as? [[String: Any]] ?? []).enumerated()),
                                id: \.offset) { _, track in
                            VStack(alignment: .leading) {
                                Text(track["name"] as? String ?? "Track").font(.headline)
                                GeometryReader { geometry in
                                    ZStack(alignment: .leading) {
                                        Color.secondary.opacity(0.1)
                                        ForEach(Array((track["clips"] as? [[String: Any]] ?? []).enumerated()),
                                                id: \.offset) { _, clip in
                                            Rectangle()
                                                .fill((clip["muted"] as? Bool ?? false) ? Color.gray : Color.accentColor)
                                                .frame(width: max(1, geometry.size.width *
                                                    Double(clip["length"] as? Int ?? 0) / Double(max(1, length))))
                                                .offset(x: geometry.size.width *
                                                    Double(clip["start"] as? Int ?? 0) / Double(max(1, length)))
                                        }
                                    }
                                }.frame(height: 28)
                            }
                        }
                    }
                }.frame(minHeight: 160)
                Slider(value: Binding(get: { playback.frame }, set: { playback.seek($0) }), in: 0...Double(max(1, length))) {
                    Text("Position")
                }
                Text(String(format: "%.2f / %.2f s", playback.frame / Double(snapshot.rate),
                            Double(length) / Double(snapshot.rate)))
                    .monospacedDigit()
                let eligibility = PlaybackEligibility.assess(selected)
                Button(playback.playing ? "Pause" : "Play") {
                    playback.toggle(root: root, snapshot: snapshot, edit: selected)
                }.disabled(!eligibility.allowed || length == 0)
                .keyboardShortcut(.space, modifiers: [])
                if let message = playback.error {
                    Text(message).foregroundColor(.red).textSelection(.enabled)
                }
                Text(eligibility.reasons.joined(separator: "\n"))
                    .font(.callout).foregroundColor(.secondary).textSelection(.enabled)
            } else if error == nil { ProgressView("Reading project…") }
        }
        .padding(20).frame(minWidth: 480, minHeight: 360)
        .onDisappear { playback.reset() }
        .task {
            do {
                let loaded = try await Task.detached(priority: .userInitiated) {
                    try ProjectReader.read(at: root)
                }.value
                snapshot = loaded
                editID = loaded.edits.first(where: { $0.id == "main" })?.id ?? loaded.edits[0].id
            } catch { self.error = String(describing: error) }
        }
    }
}
