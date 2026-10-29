import Foundation
import AVFoundation

/// Bounded streaming player: mix/decode on one worker, never in the audio
/// callback, and keep only three half-second buffers queued. Seeking starts a
/// new generation, so completions from old buffers cannot restart old audio.
/// Not enabled in the UI until native conformance has actually passed.
public final class PreviewPlayer {
    private let engine = AVAudioEngine()
    private let node = AVAudioPlayerNode()
    private let queue = DispatchQueue(label: "fi.sulopuisto.kuulas-viewer.mix")
    private let state: [String: Any]
    private let source: AudioFiles
    private let rate: Int
    private let length: Int
    private var generation = 0
    private var nextFrame = 0
    private var origin = 0
    private var playing = false
    public var onError: ((String) -> Void)?

    public init(root: URL, snapshot: ProjectSnapshot, edit: EditSnapshot) throws {
        rate = snapshot.rate
        state = edit.state
        source = try AudioFiles(root: root, snapshot: snapshot)
        length = PlaybackPosition.length(state)
        guard let format = AVAudioFormat(standardFormatWithSampleRate: Double(rate), channels: 2) else {
            throw ProjectReadError.invalid("Invalid playback sample rate.")
        }
        engine.attach(node)
        engine.connect(node, to: engine.mainMixerNode, format: format)
        engine.prepare()
    }

    deinit { node.stop(); engine.stop() }

    public func play(at frame: Int) {
        queue.async { [weak self] in
            guard let self else { return }
            self.generation += 1
            self.node.stop()
            self.origin = PlaybackPosition.start(frame, length: self.length)
            self.nextFrame = self.origin
            let token = self.generation
            do {
                if !self.engine.isRunning { try self.engine.start() }
                self.playing = true
                for _ in 0..<3 { try self.schedule(token) }
                if self.length > 0 { self.node.play() }
                else { self.playing = false }
            } catch { self.fail(error) }
        }
    }

    public func stop() {
        queue.async { [weak self] in
            guard let self else { return }
            self.generation += 1
            self.playing = false
            self.node.stop()
        }
    }

    /// Node sample clock, not a timer-derived playback estimate.
    public func position(_ completion: @escaping (Int, Bool) -> Void) {
        queue.async { [weak self] in
            guard let self else { return }
            let elapsed = self.node.lastRenderTime.flatMap { self.node.playerTime(forNodeTime: $0) }
                .map { Int(Double($0.sampleTime) * Double(self.rate) / $0.sampleRate) } ?? 0
            let frame = min(self.length, self.origin + elapsed)
            let active = self.playing && frame < self.length
            if !active { self.playing = false }
            DispatchQueue.main.async { completion(frame, active) }
        }
    }

    private func schedule(_ token: Int) throws {
        guard token == generation, playing, nextFrame < length else { return }
        let count = min(max(1, rate / 2), length - nextFrame)
        let samples = try SampleMixer.mix(state: state, rate: rate, source: source,
                                           first: nextFrame, count: count)
        guard let format = AVAudioFormat(standardFormatWithSampleRate: Double(rate), channels: 2),
              let buffer = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: AVAudioFrameCount(count)),
              let output = buffer.floatChannelData else {
            throw ProjectReadError.invalid("Cannot prepare playback audio.")
        }
        buffer.frameLength = AVAudioFrameCount(count)
        for channel in 0..<2 {
            for index in 0..<count { output[channel][index] = samples[channel][index] }
        }
        nextFrame += count
        node.scheduleBuffer(buffer, completionCallbackType: .dataPlayedBack) { [weak self] _ in
            self?.queue.async { [weak self] in
                guard let self, token == self.generation else { return }
                do { try self.schedule(token) } catch { self.fail(error) }
            }
        }
    }

    private func fail(_ error: Error) {
        playing = false
        generation += 1
        node.stop()
        let message = String(describing: error)
        DispatchQueue.main.async { [weak self] in self?.onError?(message) }
    }
}
