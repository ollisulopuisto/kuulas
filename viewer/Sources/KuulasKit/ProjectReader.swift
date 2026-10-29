import Foundation
import Darwin
import CSQLite
import CZlib

public enum ProjectReadError: Error, CustomStringConvertible {
    case invalid(String)
    case changed
    case tooLarge

    public var description: String {
        switch self {
        case .invalid(let reason): return reason
        case .changed: return "The project changed while reading. Open it again."
        case .tooLarge: return "This project exceeds the viewer's safe read limit."
        }
    }
}

public struct EditSnapshot {
    public let id: String
    public let name: String
    public let head: String
    public let archived: Bool
    /// Exact decompressed stored edit, not an NHSX conversion or guessed mix.
    public let state: [String: Any]
}

public struct ProjectSnapshot {
    public let name: String
    public let rate: Int
    public let edits: [EditSnapshot]
    public let media: [[String: Any]]
    public let manifest: [String: Any]
}

private struct FileIdentity: Equatable {
    let file: UInt64
    let size: UInt64
    let modified: Date
    let changedSeconds: Int
    let changedNanos: Int
}

/// The only source operations are stat and byte-copy. SQLite never opens the
/// source: even SQLITE_OPEN_READONLY can create WAL/SHM in a closed package.
public enum ProjectReader {
    public static let maxDatabaseBytes: UInt64 = 512 * 1024 * 1024
    public static let maxDecodedBlobBytes = 64 * 1024 * 1024

    private static func identity(_ url: URL) throws -> FileIdentity? {
        guard FileManager.default.fileExists(atPath: url.path) else { return nil }
        var info = stat()
        guard lstat(url.path, &info) == 0, (info.st_mode & S_IFMT) == S_IFREG else {
            throw ProjectReadError.invalid("Invalid database file.")
        }
        let values = try FileManager.default.attributesOfItem(atPath: url.path)
        guard values[.type] as? FileAttributeType == .typeRegular,
              let inode = values[.systemFileNumber] as? NSNumber,
              let size = values[.size] as? NSNumber,
              let modified = values[.modificationDate] as? Date else {
            throw ProjectReadError.invalid("Invalid database file.")
        }
        return FileIdentity(file: inode.uint64Value, size: size.uint64Value,
                            modified: modified, changedSeconds: info.st_ctimespec.tv_sec,
                            changedNanos: info.st_ctimespec.tv_nsec)
    }

    public static func read(at root: URL) throws -> ProjectSnapshot {
        let manifestURL = root.appendingPathComponent("manifest.json")
        guard let manifestIdentity = try identity(manifestURL),
              manifestIdentity.size <= 1024 * 1024 else {
            throw ProjectReadError.invalid("Invalid project manifest.")
        }
        let manifestData = try Data(contentsOf: manifestURL)
        guard manifestData.count <= 1024 * 1024,
              let manifest = try JSONSerialization.jsonObject(with: manifestData)
                as? [String: Any],
              manifest["format"] as? String == "kuulas-project",
              let minimum = manifest["min_reader"] as? Int,
              minimum >= 1, minimum <= 4 else {
            throw ProjectReadError.invalid("Not a supported Kuulas project.")
        }
        let names = ["project.sqlite", "project.sqlite-wal"]
        let before = try names.map { try identity(root.appendingPathComponent($0)) }
        guard before[0] != nil else {
            throw ProjectReadError.invalid("The project database is missing.")
        }
        guard before.compactMap({ $0 }).reduce(UInt64(0), { $0 + $1.size })
                <= maxDatabaseBytes else { throw ProjectReadError.tooLarge }
        let temporary = FileManager.default.temporaryDirectory
            .appendingPathComponent("kuulas-viewer-" + UUID().uuidString, isDirectory: true)
        try FileManager.default.createDirectory(at: temporary,
                    withIntermediateDirectories: false, attributes: [.posixPermissions: 0o700])
        defer { try? FileManager.default.removeItem(at: temporary) }
        for (index, name) in names.enumerated() where before[index] != nil {
            try FileManager.default.copyItem(at: root.appendingPathComponent(name),
                                             to: temporary.appendingPathComponent(name))
        }
        let after = try names.map { try identity(root.appendingPathComponent($0)) }
        guard before == after,
              try Data(contentsOf: manifestURL) == manifestData else {
            throw ProjectReadError.changed
        }
        let copied = try names.map { try identity(temporary.appendingPathComponent($0)) }
        guard zip(before, copied).allSatisfy({ pair in pair.0?.size == pair.1?.size }) else {
            throw ProjectReadError.changed
        }
        let db = try Database(temporary.appendingPathComponent(names[0]))
        try db.execute("PRAGMA query_only=ON")
        try db.execute("BEGIN")
        guard try db.rows("PRAGMA quick_check").first?["quick_check"] as? String == "ok",
              let rateText = try db.rows("SELECT value FROM meta WHERE key='project_rate'")
                .first?["value"] as? String,
              let rate = Int(rateText), rate > 0 else {
            throw ProjectReadError.invalid("Invalid project database.")
        }
        let declaredEdits = try db.rows("SELECT count(*) AS count FROM edits").first?["count"] as? Int64
        let rows = try db.rows("SELECT e.id,e.name,e.archived,e.head,b.data FROM edits e "
            + "JOIN nodes n ON n.id=e.head AND n.edit=e.id "
            + "JOIN blobs b ON b.hash=n.state ORDER BY e.created_utc,e.rowid")
        let edits = try rows.map { row -> EditSnapshot in
            guard let id = row["id"] as? String, let name = row["name"] as? String,
                  let head = row["head"] as? String, let bytes = row["data"] as? Data,
                  let state = try JSONSerialization.jsonObject(with: inflate(bytes))
                    as? [String: Any] else {
                throw ProjectReadError.invalid("Invalid edit state.")
            }
            return EditSnapshot(id: id, name: name, head: head,
                                archived: (row["archived"] as? Int64 ?? 0) != 0, state: state)
        }
        guard !edits.isEmpty, Int64(edits.count) == declaredEdits else {
            throw ProjectReadError.invalid("Missing or damaged edit heads.")
        }
        return ProjectSnapshot(name: root.deletingPathExtension().lastPathComponent,
            rate: rate, edits: edits,
            media: try db.rows("SELECT * FROM media ORDER BY added_utc,id"), manifest: manifest)
    }

    private static func inflate(_ data: Data) throws -> Data {
        var capacity = max(1024, data.count * 4)
        while capacity <= maxDecodedBlobBytes {
            var result = Data(count: capacity)
            var size = uLongf(capacity)
            let status = result.withUnsafeMutableBytes { output in
                data.withUnsafeBytes { input in
                    uncompress(output.bindMemory(to: Bytef.self).baseAddress, &size,
                               input.bindMemory(to: Bytef.self).baseAddress, uLong(data.count))
                }
            }
            if status == Z_OK { result.count = Int(size); return result }
            guard status == Z_BUF_ERROR else {
                throw ProjectReadError.invalid("Damaged compressed edit state.")
            }
            capacity *= 2
        }
        throw ProjectReadError.tooLarge
    }
}

private final class Database {
    private var handle: OpaquePointer?

    init(_ url: URL) throws {
        // Only the private copy may create sidecars or recover a copied WAL.
        let status = sqlite3_open_v2(url.path, &handle, SQLITE_OPEN_READWRITE, nil)
        guard status == SQLITE_OK else {
            if let handle { sqlite3_close(handle) }
            handle = nil
            throw ProjectReadError.invalid("Cannot open project snapshot.")
        }
        sqlite3_busy_timeout(handle, 1000)
    }

    deinit { sqlite3_close(handle) }

    func execute(_ sql: String) throws {
        guard sqlite3_exec(handle, sql, nil, nil, nil) == SQLITE_OK else {
            throw ProjectReadError.invalid("Invalid project database transaction.")
        }
    }

    func rows(_ sql: String) throws -> [[String: Any]] {
        var statement: OpaquePointer?
        guard sqlite3_prepare_v2(handle, sql, -1, &statement, nil) == SQLITE_OK else {
            throw ProjectReadError.invalid("Unsupported project database schema.")
        }
        defer { sqlite3_finalize(statement) }
        var result: [[String: Any]] = []
        var status = sqlite3_step(statement)
        while status == SQLITE_ROW {
            var row: [String: Any] = [:]
            for column in 0..<sqlite3_column_count(statement) {
                let name = String(cString: sqlite3_column_name(statement, column))
                switch sqlite3_column_type(statement, column) {
                case SQLITE_INTEGER: row[name] = sqlite3_column_int64(statement, column)
                case SQLITE_FLOAT: row[name] = sqlite3_column_double(statement, column)
                case SQLITE_TEXT:
                    if let text = sqlite3_column_text(statement, column) {
                        row[name] = String(cString: text)
                    }
                case SQLITE_BLOB:
                    let count = Int(sqlite3_column_bytes(statement, column))
                    if let bytes = sqlite3_column_blob(statement, column) {
                        row[name] = Data(bytes: bytes, count: count)
                    }
                default: break
                }
            }
            result.append(row)
            status = sqlite3_step(statement)
        }
        guard status == SQLITE_DONE else {
            throw ProjectReadError.invalid("Cannot read database snapshot.")
        }
        return result
    }
}
