import Foundation

/// Only the schema/features covered by native Python-mixer conformance may play.
/// A future nested effect must fail closed, not silently produce a simpler mix.
public struct PlaybackEligibility {
    public let reasons: [String]
    public var allowed: Bool { reasons.isEmpty }

    public static func assess(_ edit: EditSnapshot) -> PlaybackEligibility {
        var reasons: [String] = []
        func keys(_ row: [String: Any], _ known: Set<String>, _ context: String) {
            let unknown = Set(row.keys).subtracting(known)
            if !unknown.isEmpty {
                reasons.append("Unsupported \(context): " + unknown.sorted().joined(separator: ", "))
            }
        }
        func numbers(_ row: [String: Any], _ fields: [String], _ context: String) {
            for field in fields where row[field] != nil {
                guard let value = row[field] as? NSNumber, value.doubleValue.isFinite else {
                    reasons.append("Invalid \(context) value: \(field)")
                    continue
                }
            }
        }
        func pairs(_ row: [String: Any], _ fields: [String]) {
            for field in fields where row[field] != nil {
                guard let pairs = row[field] as? [[NSNumber]], pairs.allSatisfy({
                    $0.count == 2 && $0.allSatisfy { $0.doubleValue.isFinite }
                }) else {
                    reasons.append("Invalid range or curve: " + field)
                    continue
                }
            }
        }
        let state = edit.state
        keys(state, ["tracks", "buses", "master_gain_db", "markers", "sync_groups",
            "placeholders", "mix_done", "series", "rate", "media"], "project fields")
        numbers(state, ["master_gain_db", "rate"], "project")
        guard let tracks = state["tracks"] as? [[String: Any]],
              let buses = state["buses"] as? [[String: Any]] else {
            return PlaybackEligibility(reasons: reasons + ["Invalid tracks or buses."])
        }
        for bus in buses {
            keys(bus, ["id", "name", "gain_db", "pan", "mute", "kind"], "bus fields")
            numbers(bus, ["gain_db", "pan"], "bus")
        }
        for track in tracks {
            keys(track, ["id", "name", "kind", "speaker", "bus", "gain_db", "pan",
                "mute", "solo", "clips", "automation", "gate", "target_lufs",
                "mono", "follow_bus_role", "duck"], "track fields")
            numbers(track, ["gain_db", "pan"], "track")
            pairs(track, ["automation", "gate"])
            guard let clips = track["clips"] as? [[String: Any]] else {
                reasons.append("Invalid track clips.")
                continue
            }
            for clip in clips {
                keys(clip, ["id", "media", "start", "offset", "length", "gain_db", "pan",
                    "fade_in", "fade_out", "muted", "name", "envelope", "xfade_in",
                    "xfade_out", "group", "free", "ungated", "auto_silence", "home"], "clip fields")
                pairs(clip, ["envelope", "auto_silence"])
                numbers(clip, ["start", "offset", "length", "gain_db", "pan", "fade_in",
                    "fade_out", "xfade_in", "xfade_out"], "clip")
                if (clip["length"] as? Int ?? -1) < 0 || clip["media"] as? String == nil {
                    reasons.append("Invalid clip bounds or media.")
                }
            }
        }
        return PlaybackEligibility(reasons: reasons)
    }
}
