import Foundation
import XCTest
@testable import KuulasKit

private struct StereoSource: SampleSource {
    let samples: [[Double]]
    func read(media: String, first: Int, count: Int) throws -> [[Double]] {
        samples.map { channel in
            (first..<(first + count)).map { index in
                index >= 0 && index < channel.count ? channel[index] : 0
            }
        }
    }
}

final class PlaybackCasesTests: XCTestCase {
    func testStereoMixAndBufferBoundariesMatchPython() throws {
        let root = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
            .deletingLastPathComponent().deletingLastPathComponent()
        let data = try Data(contentsOf: root.appendingPathComponent("Conformance/playback-cases.json"))
        let fixture = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
        let source = StereoSource(samples: try XCTUnwrap(fixture["source"] as? [[Double]]))
        for row in try XCTUnwrap(fixture["cases"] as? [[String: Any]]) {
            let state = try XCTUnwrap(row["state"] as? [String: Any])
            for window in try XCTUnwrap(row["windows"] as? [[String: Any]]) {
                let first = try XCTUnwrap(window["first"] as? Int)
                let samples = try XCTUnwrap(window["samples"] as? [[Double]])
                let result = try SampleMixer.mix(state: state, rate: 48000,
                    source: source, first: first, count: samples[0].count)
                for channel in 0..<2 {
                    for index in samples[channel].indices {
                        XCTAssertEqual(Double(result[channel][index]), samples[channel][index],
                            accuracy: 0.000001, "\(row["name"] ?? "case") frame \(first + index)")
                    }
                }
            }
        }
    }
}

extension PlaybackCasesTests {
    func testTransportBoundsIgnoreMutedTailAndRestartAtEnd() {
        let state: [String: Any] = ["tracks": [["clips": [
            ["start": 10, "length": 20, "muted": false],
            ["start": 1000, "length": 100, "muted": true]]]]]
        XCTAssertEqual(PlaybackPosition.length(state), 30)
        XCTAssertEqual(PlaybackPosition.start(-10, length: 30), 0)
        XCTAssertEqual(PlaybackPosition.start(12, length: 30), 12)
        XCTAssertEqual(PlaybackPosition.start(30, length: 30), 0)
        XCTAssertEqual(PlaybackPosition.start(40, length: 30), 0)
        XCTAssertEqual(PlaybackPosition.length([:]), 0)
    }
}
