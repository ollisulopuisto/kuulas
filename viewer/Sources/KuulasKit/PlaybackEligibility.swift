import Foundation

/// A reader returning data does not prove its player can reproduce that data.
/// Until a feature has sample-level conformance, refuse it rather than quietly
/// playing a simpler mix. This is an explicit gate, not a completeness claim.
public struct PlaybackEligibility {
    public let reasons: [String]
    public var allowed: Bool { reasons.isEmpty }

    public static func assess(_ edit: EditSnapshot) -> PlaybackEligibility {
        var reasons: [String] = []
        let state = edit.state
        // The player is not implemented yet. Even the simplest edit must not
        // accidentally become playable merely because all fields were parsed.
        reasons.append("Native playback has not yet passed audio conformance.")
        let knownProject: Set<String> = ["tracks", "buses", "master_gain_db", "markers",
            "sync_groups", "placeholders", "mix_done", "series", "rate", "media"]
        let unknown = Set(state.keys).subtracting(knownProject)
        if !unknown.isEmpty { reasons.append("Unknown project fields: " + unknown.sorted().joined(separator: ", ")) }
        for track in state["tracks"] as? [[String: Any]] ?? [] {
            let name = track["name"] as? String ?? ""
            if !(track["gate"] as? [Any] ?? []).isEmpty {
                reasons.append("Track gates need audio conformance: " + name)
            }
            if !(track["automation"] as? [Any] ?? []).isEmpty {
                reasons.append("Track automation needs audio conformance: " + name)
            }
            for clip in track["clips"] as? [[String: Any]] ?? [] {
                if !(clip["auto_silence"] as? [Any] ?? []).isEmpty {
                    reasons.append("Clip auto-silence needs audio conformance: " + name)
                }
            }
        }
        return PlaybackEligibility(reasons: reasons)
    }
}
