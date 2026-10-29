import XCTest
@testable import KuulasKit

final class ReaderTests: XCTestCase {
    private var fixtures: URL {
        URL(fileURLWithPath: #filePath).deletingLastPathComponent()
            .deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent("Conformance")
    }

    func testCurrentPythonConformanceHeadsAndStoredState() throws {
        let root = fixtures.appendingPathComponent("Session.kuulas")
        let expected = try XCTUnwrap(JSONSerialization.jsonObject(
            with: Data(contentsOf: fixtures.appendingPathComponent("expected.json")))
            as? [String: Any])
        let edits = try XCTUnwrap(expected["edits"] as? [[String: Any]])
        let actual = try ProjectReader.read(at: root)
        XCTAssertEqual(actual.rate, 48000)
        XCTAssertEqual(actual.edits.count, 3)
        for (row, edit) in zip(edits, actual.edits) {
            XCTAssertEqual(edit.id, row["id"] as? String)
            XCTAssertEqual(edit.head, row["head"] as? String)
            XCTAssertEqual(edit.name, row["name"] as? String)
            let project = try XCTUnwrap(row["project"] as? [String: Any])
            // Material lives outside the edit blob and is composed by Python.
            // Bind the actual stored edit fields, without pretending they're NHSX.
            for (key, value) in edit.state where key != "sync_groups" {
                let expectedValue = try XCTUnwrap(project[key], key)
                XCTAssertEqual(try canonical(value), try canonical(expectedValue), key)
            }
        }
        XCTAssertEqual(actual.edits.filter(\.archived).count, 1)
        XCTAssertEqual(actual.media.count, 1)
    }

    func testClosedFixtureDoesNotCreateOrChangeSourceFiles() throws {
        let root = fixtures.appendingPathComponent("Session.kuulas")
        let before = try tree(root)
        _ = try ProjectReader.read(at: root)
        XCTAssertEqual(try tree(root), before)
    }

    func testUnknownMinReaderRefusedWithoutChangingPackage() throws {
        let temporary = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString)
        try FileManager.default.copyItem(at: fixtures.appendingPathComponent("Session.kuulas"),
                                         to: temporary)
        defer { try? FileManager.default.removeItem(at: temporary) }
        let manifest = temporary.appendingPathComponent("manifest.json")
        try Data("{\"format\":\"kuulas-project\",\"min_reader\":99}".utf8).write(to: manifest)
        let before = try tree(temporary)
        XCTAssertThrowsError(try ProjectReader.read(at: temporary))
        XCTAssertEqual(try tree(temporary), before)
    }

    private func canonical(_ value: Any) throws -> Data {
        try JSONSerialization.data(withJSONObject: value,
                                  options: [.sortedKeys, .fragmentsAllowed])
    }

    private func tree(_ root: URL) throws -> [String: Data] {
        let urls = try XCTUnwrap(FileManager.default.enumerator(at: root,
                            includingPropertiesForKeys: [.isRegularFileKey]))
        var files: [String: Data] = [:]
        for case let url as URL in urls {
            if try url.resourceValues(forKeys: [.isRegularFileKey]).isRegularFile == true {
                files[url.path] = try Data(contentsOf: url)
            }
        }
        return files
    }
}

extension ReaderTests {
    func testReaderSuccessDoesNotEnableUnverifiedAudio() throws {
        let snapshot = try ProjectReader.read(at: fixtures.appendingPathComponent("Session.kuulas"))
        for edit in snapshot.edits {
            let eligibility = PlaybackEligibility.assess(edit)
            XCTAssertFalse(eligibility.allowed)
            XCTAssertFalse(eligibility.reasons.isEmpty)
        }
        let first = PlaybackEligibility.assess(snapshot.edits[0])
        XCTAssertTrue(first.reasons.contains { $0.contains("gates") })
        XCTAssertTrue(first.reasons.contains { $0.contains("auto-silence") })
    }
}

extension ReaderTests {
    func testAllDeclaredFixtureEditsArePresent() throws {
        // A missing head needs a generated mutation fixture before this case
        // can assert a native result; the source reader compares joined count
        // against declared count rather than dropping a damaged edit silently.
        let root = fixtures.appendingPathComponent("Session.kuulas")
        let snapshot = try ProjectReader.read(at: root)
        XCTAssertEqual(snapshot.edits.count, 3)
        XCTAssertEqual(Set(snapshot.edits.map(\.id)).count, 3)
    }

    func testContainedMovedLinkedMediaResolvesWithoutOldAbsolutePath() throws {
        let root = fixtures.appendingPathComponent("Session.kuulas")
        let snapshot = try ProjectReader.read(at: root)
        let audio = try AudioFiles(root: root, snapshot: snapshot)
        let media = try XCTUnwrap(snapshot.media.first?["id"] as? String)
        let sample = try audio.read(media: media, first: 100, count: 10)
        XCTAssertEqual(sample.count, 1)
        XCTAssertEqual(sample[0].count, 10)
        XCTAssertTrue(sample[0].contains { abs($0) > 0.001 })
    }
}
