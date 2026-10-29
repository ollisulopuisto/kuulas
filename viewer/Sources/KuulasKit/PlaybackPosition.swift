import Foundation

/// Pure transport bounds shared by the UI and queued player.
public enum PlaybackPosition {
    public static func length(_ state: [String: Any]) -> Int {
        (state["tracks"] as? [[String: Any]] ?? [])
            .flatMap { $0["clips"] as? [[String: Any]] ?? [] }
            .filter { !($0["muted"] as? Bool ?? false) }
            .map { max(0, ($0["start"] as? Int ?? 0) + ($0["length"] as? Int ?? 0)) }
            .max() ?? 0
    }

    public static func start(_ requested: Int, length: Int) -> Int {
        // Play at the end restarts; seek itself may still display the end.
        requested >= length ? 0 : max(0, requested)
    }
}
