import Foundation
import AVFoundation

/// Contained-media access only. A linked file outside the opened package needs
/// separate user-granted access; do not copy the NHSX broad sandbox exception.
public final class AudioFiles: SampleSource {
    private var files: [String: AVAudioFile] = [:]
    private let rate: Int

    public init(root: URL, snapshot: ProjectSnapshot) throws {
        rate = snapshot.rate
        let resolvedRoot = root.resolvingSymlinksInPath().standardizedFileURL.path + "/"
        for row in snapshot.media {
            guard let id = row["id"] as? String, !id.contains("/"), !id.contains(".."),
                  let storage = row["storage"] as? String else {
                throw ProjectReadError.invalid("Invalid media reference.")
            }
            let candidate: URL
            if storage == "linked" {
                guard let relative = row["linked_package_rel"] as? String,
                      !relative.hasPrefix("/"), !relative.split(separator: "/").contains("..") else {
                    throw ProjectReadError.invalid("This project uses external linked audio. Access is not granted.")
                }
                candidate = root.appendingPathComponent(relative)
            } else {
                candidate = root.appendingPathComponent("media/\(id).flac")
            }
            let url = candidate.resolvingSymlinksInPath().standardizedFileURL
            guard url.path.hasPrefix(resolvedRoot) else {
                throw ProjectReadError.invalid("Audio points outside this project package.")
            }
            let file = try AVAudioFile(forReading: url)
            guard Int(file.processingFormat.sampleRate) == rate,
                  file.processingFormat.channelCount >= 1,
                  file.processingFormat.channelCount <= 2 else {
                throw ProjectReadError.invalid("Audio needs sample-rate conversion or multichannel support.")
            }
            files[id] = file
        }
    }

    public func read(media: String, first: Int, count: Int) throws -> [[Double]] {
        guard let file = files[media], count >= 0, count <= rate * 2 else {
            throw ProjectReadError.invalid("Missing audio or invalid playback block.")
        }
        var result = Array(repeating: Array(repeating: 0.0, count: count),
                           count: Int(file.processingFormat.channelCount))
        let lo = max(0, first), hi = min(Int(file.length), first + count)
        guard hi > lo else { return result }
        file.framePosition = AVAudioFramePosition(lo)
        guard let buffer = AVAudioPCMBuffer(pcmFormat: file.processingFormat,
                                            frameCapacity: AVAudioFrameCount(hi - lo)) else {
            throw ProjectReadError.invalid("Cannot allocate audio block.")
        }
        try file.read(into: buffer, frameCount: AVAudioFrameCount(hi - lo))
        guard let samples = buffer.floatChannelData else {
            throw ProjectReadError.invalid("Cannot decode this audio format.")
        }
        for channel in result.indices {
            for index in 0..<Int(buffer.frameLength) {
                result[channel][lo - first + index] = Double(samples[channel][index])
            }
        }
        return result
    }
}
