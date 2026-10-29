import Foundation

public protocol SampleSource {
    /// Project-rate source samples, planar channel arrays, zero padded.
    func read(media: String, first: Int, count: Int) throws -> [[Double]]
}

/// Independent native interpretation, bound to Python mixer sample fixtures.
/// All coordinates are integer project frames, including source envelopes.
public enum SampleMixer {
    private static func number(_ row: [String: Any], _ key: String, _ fallback: Double = 0) -> Double {
        (row[key] as? NSNumber)?.doubleValue ?? fallback
    }
    private static func integer(_ row: [String: Any], _ key: String) -> Int {
        (row[key] as? NSNumber)?.intValue ?? 0
    }
    private static func flag(_ row: [String: Any], _ key: String) -> Bool {
        (row[key] as? NSNumber)?.boolValue ?? false
    }
    private static func gain(_ db: Double) -> Double { pow(10, db / 20) }
    private static func ramp(_ frame: Int, _ begin: Int, _ length: Int) -> Double {
        guard length > 0 else { return 1 }
        let x = min(1, max(0, Double(frame - begin) / Double(length)))
        return pow(sin(.pi * x / 2), 2)
    }
    private static func curve(_ raw: Any?, _ frame: Int) -> Double {
        let points = raw as? [[NSNumber]] ?? []
        guard let first = points.first, first.count == 2 else { return 0 }
        if frame <= first[0].intValue { return first[1].doubleValue }
        for (a, b) in zip(points, points.dropFirst()) where a.count == 2 && b.count == 2 {
            if frame <= b[0].intValue {
                let span = b[0].doubleValue - a[0].doubleValue
                if span <= 0 { return b[1].doubleValue }
                let fraction = (Double(frame) - a[0].doubleValue) / span
                return a[1].doubleValue + fraction * (b[1].doubleValue - a[1].doubleValue)
            }
        }
        return points.last?[1].doubleValue ?? 0
    }
    private static func gated(_ raw: Any?, _ frame: Int, _ rate: Int) -> Double {
        let ranges = raw as? [[Int]] ?? []
        let width = max(1, Int((0.030 * Double(rate)).rounded(.toNearestOrEven)))
        var value = 1.0
        for pair in ranges where pair.count == 2 {
            let a = pair[0], b = pair[1]
            if frame >= a && frame < b { return 0 }
            if frame >= a - width && frame < a {
                value *= ramp(-frame, -(a - 1), width)
            }
            if frame >= b && frame < b + width { value *= ramp(frame, b, width) }
        }
        return value
    }
    private static func pan(_ value: Double, mono: Bool) -> (Double, Double) {
        let x = min(1, max(-1, value))
        return mono ? (sqrt(0.5 * (1 - x)), sqrt(0.5 * (1 + x)))
                    : (min(1, 1 - x), min(1, 1 + x))
    }

    public static func mix(state: [String: Any], rate: Int, source: SampleSource,
                           first: Int, count: Int) throws -> [[Float]] {
        guard rate > 0, first >= 0, count >= 0, count <= rate * 60 else {
            throw ProjectReadError.invalid("Invalid playback block.")
        }
        let tracks = state["tracks"] as? [[String: Any]] ?? []
        let buses = state["buses"] as? [[String: Any]] ?? []
        let soloing = tracks.contains { flag($0, "solo") }
        var output = Array(repeating: Array(repeating: 0.0, count: count), count: 2)
        var busAudio: [String: [[Double]]] = [:]
        for bus in buses {
            if let id = bus["id"] as? String { busAudio[id] = output }
        }
        for track in tracks {
            if soloing ? !flag(track, "solo") : flag(track, "mute") { continue }
            var audio = Array(repeating: Array(repeating: 0.0, count: count), count: 2)
            let clips = track["clips"] as? [[String: Any]] ?? []
            for clip in clips where !flag(clip, "muted") {
                let start = integer(clip, "start"), length = integer(clip, "length")
                let offset = integer(clip, "offset")
                let end = start + length
                // Match Python's current track-level intersection test too.
                if start >= first + count || end <= first { continue }
                let crossIn = integer(clip, "xfade_in"), crossOut = integer(clip, "xfade_out")
                let heardStart = start - crossIn / 2, heardEnd = end + crossOut / 2
                let lo = max(first, heardStart), hi = min(first + count, heardEnd)
                if hi <= lo { continue }
                guard let media = clip["media"] as? String else {
                    throw ProjectReadError.invalid("Missing clip media reference.")
                }
                var samples = try source.read(media: media, first: offset + lo - start, count: hi - lo)
                guard !samples.isEmpty, samples.allSatisfy({ $0.count == hi - lo }) else {
                    throw ProjectReadError.invalid("Invalid decoded audio block.")
                }
                if flag(track, "mono"), samples.count > 1 {
                    samples = [(0..<(hi - lo)).map { index in
                        samples.reduce(0) { $0 + $1[index] } / Double(samples.count)
                    }]
                }
                var fadeIn = integer(clip, "fade_in"), fadeOut = integer(clip, "fade_out")
                let muteWidth = Int((Double(rate) * 0.030).rounded(.toNearestOrEven))
                for neighbor in clips where flag(neighbor, "muted") && neighbor["media"] as? String == media {
                    let neighborStart = integer(neighbor, "start")
                    let neighborOffset = integer(neighbor, "offset")
                    let neighborLength = integer(neighbor, "length")
                    if neighborStart + neighborLength == start && neighborOffset + neighborLength == offset {
                        fadeIn = max(fadeIn, min(muteWidth, length))
                    }
                    if end == neighborStart && offset + length == neighborOffset {
                        fadeOut = max(fadeOut, min(muteWidth, length))
                    }
                }
                let (left, right) = pan(number(clip, "pan"), mono: samples.count == 1)
                for frame in lo..<hi {
                    let src = offset + frame - start, index = frame - lo
                    var level = gain(number(clip, "gain_db") + curve(clip["envelope"], src))
                    level *= gated(clip["auto_silence"], src, rate)
                    if crossIn > 0 { level *= ramp(frame, heardStart, crossIn) }
                    else if fadeIn > 0 { level *= ramp(frame, start, fadeIn) }
                    if crossOut > 0 { level *= ramp(-frame, -heardEnd, crossOut) }
                    else if fadeOut > 0 { level *= ramp(-frame, -(end - 1), fadeOut) }
                    audio[0][frame - first] += samples[0][index] * level * left
                    audio[1][frame - first] += samples[samples.count == 1 ? 0 : 1][index] * level * right
                }
            }
            let (left, right) = pan(number(track, "pan"), mono: false)
            let bus = track["bus"] as? String
            for index in 0..<count {
                let frame = first + index
                let level = gain(number(track, "gain_db") + curve(track["automation"], frame))
                    * gated(track["gate"], frame, rate)
                let pair = [audio[0][index] * level * left, audio[1][index] * level * right]
                for channel in 0..<2 {
                    if let bus, busAudio[bus] != nil { busAudio[bus]![channel][index] += pair[channel] }
                    else { output[channel][index] += pair[channel] }
                }
            }
        }
        for bus in buses where !flag(bus, "mute") {
            guard let id = bus["id"] as? String, let audio = busAudio[id] else { continue }
            let (left, right) = pan(number(bus, "pan"), mono: false)
            let level = gain(number(bus, "gain_db"))
            for index in 0..<count {
                output[0][index] += audio[0][index] * level * left
                output[1][index] += audio[1][index] * level * right
            }
        }
        let master = gain(number(state, "master_gain_db"))
        return output.map { channel in channel.map { Float($0 * master) } }
    }
}
