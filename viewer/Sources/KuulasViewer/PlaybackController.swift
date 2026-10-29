import Foundation
import Combine
import KuulasKit

/// Main-thread view state; audio decoding/mixing remains on PreviewPlayer's queue.
/// Replacing an edit disposes its player before any next edit can start.
final class PlaybackController: ObservableObject {
    @Published var frame = 0.0
    @Published var playing = false
    @Published var error: String?
    private var player: PreviewPlayer?
    private var timer: Timer?
    private var revision = 0
    private var opening = false

    func toggle(root: URL, snapshot: ProjectSnapshot, edit: EditSnapshot) {
        if playing { pause(); return }
        guard !opening else { return }
        error = nil
        if let player { start(player); return }
        opening = true
        revision += 1
        let token = revision
        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            let result = Result { try PreviewPlayer(root: root, snapshot: snapshot, edit: edit) }
            DispatchQueue.main.async { [weak self] in
                guard let self, token == self.revision else { return }
                self.opening = false
                switch result {
                case .success(let player):
                    self.player = player
                    player.onError = { [weak self] message in
                        guard let self, token == self.revision else { return }
                        self.error = message
                        self.playing = false
                        self.timer?.invalidate()
                    }
                    self.start(player)
                case .failure(let error): self.error = String(describing: error)
                }
            }
        }
    }

    private func start(_ player: PreviewPlayer) {
        player.play(at: Int(frame))
        playing = true
        timer?.invalidate()
        let token = revision
        timer = Timer.scheduledTimer(withTimeInterval: 0.05, repeats: true) { [weak self] _ in
            player.position { [weak self] position, active in
                guard let self, token == self.revision, self.playing else { return }
                self.frame = Double(position)
                self.playing = active
                if !active { self.timer?.invalidate() }
            }
        }
    }

    func pause() {
        player?.stop()
        playing = false
        timer?.invalidate()
    }

    func seek(_ frame: Double) {
        self.frame = frame
        if playing { player?.play(at: Int(frame)) }
    }

    func reset() {
        revision += 1
        opening = false
        pause()
        player = nil
        frame = 0
        error = nil
    }

    deinit { timer?.invalidate(); player?.stop() }
}
