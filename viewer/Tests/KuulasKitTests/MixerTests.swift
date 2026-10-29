import AVFoundation
import XCTest
@testable import KuulasKit

private final class ToneSource: SampleSource {
    let samples: [Double]
    init(_ url: URL) throws {
        let file = try AVAudioFile(forReading: url)
        let buffer = try XCTUnwrap(AVAudioPCMBuffer(pcmFormat: file.processingFormat,
                                                   frameCapacity: AVAudioFrameCount(file.length)))
        try file.read(into: buffer)
        let data = try XCTUnwrap(buffer.floatChannelData)
        samples = (0..<Int(buffer.frameLength)).map { Double(data[0][$0]) }
    }
    func read(media: String, first: Int, count: Int) throws -> [[Double]] {
        [(first..<(first + count)).map { $0 >= 0 && $0 < samples.count ? samples[$0] : 0 }]
    }
}

final class MixerTests: XCTestCase {
    func testPythonMixerGoldenSampleWindows() throws {
        let root = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
            .deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent("Conformance")
        let snapshot = try ProjectReader.read(at: root.appendingPathComponent("Session.kuulas"))
        let source = try ToneSource(root.appendingPathComponent("Session.kuulas/recordings/tone.wav"))
        let expected = try XCTUnwrap(JSONSerialization.jsonObject(
            with: Data(contentsOf: root.appendingPathComponent("audio.json"))) as? [String: Any])
        let edits = try XCTUnwrap(expected["edits"] as? [[String: Any]])
        for row in edits {
            let edit = try XCTUnwrap(snapshot.edits.first { $0.id == row["id"] as? String })
            let windows = try XCTUnwrap(row["windows"] as? [[String: Any]])
            for window in windows {
                let first = try XCTUnwrap(window["first"] as? Int)
                let samples = try XCTUnwrap(window["samples"] as? [[Double]])
                let result = try SampleMixer.mix(state: edit.state, rate: snapshot.rate,
                    source: source, first: first, count: samples[0].count)
                for channel in 0..<2 {
                    for index in samples[channel].indices {
                        XCTAssertEqual(Double(result[channel][index]), samples[channel][index],
                                       accuracy: 0.000001, "\(edit.name) frame \(first + index)")
                    }
                }
            }
        }
    }
}
