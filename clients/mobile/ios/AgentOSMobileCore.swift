import Foundation

struct AgentOSJoinLink {
    let oneURL: URL
    let version: String

    init(url: URL) throws {
        guard url.scheme == "agentos", url.host == "join" else {
            throw MobileNodeError.invalidJoinLink
        }
        let components = URLComponents(url: url, resolvingAgainstBaseURL: false)
        let query = Dictionary(uniqueKeysWithValues: (components?.queryItems ?? []).map { ($0.name, $0.value ?? "") })
        guard
            query["v"] == "v1",
            let raw = query["one"],
            let one = URL(string: raw),
            ["https", "http"].contains(one.scheme?.lowercased() ?? "")
        else {
            throw MobileNodeError.invalidJoinLink
        }
        self.oneURL = one
        self.version = "v1"
    }
}

enum MobileNodeError: Error {
    case invalidJoinLink
    case invalidResponse
    case enrollmentRejected(String)
}

protocol AgentOSCredentialStore {
    func saveNodeToken(_ token: String, nodeID: String) throws
    func loadNodeToken(nodeID: String) throws -> String?
}

struct MobileExecutorManifest: Codable {
    let executor_id: String
    let capabilities: [String]
    let state: String
}

struct MobileProfile: Codable {
    struct Transport: Codable {
        let mode: String
        let provider: String
    }

    let profile: String
    let transport: Transport
    let presence: String
    let executors: [MobileExecutorManifest]
}

struct NodeManifest: Codable {
    let schema: String
    let realm_id: String
    let node_id: String
    let role: String
    let hostname: String
    let platform: String
    let platform_release: String
    let capabilities: [String]
    let tool_presence: [String: Bool]
    let surface_inventory: SurfaceInventory
    let mobile: MobileProfile

    struct SurfaceInventory: Codable {
        let surface_count: Int
        let surfaces: [String]
    }

    static func iphone(nodeID: String) -> NodeManifest {
        NodeManifest(
            schema: "agentos.node-manifest/v0.1",
            realm_id: "pending",
            node_id: nodeID,
            role: "client",
            hostname: nodeID,
            platform: "ios",
            platform_release: ProcessInfo.processInfo.operatingSystemVersionString,
            capabilities: ["notification.present"],
            tool_presence: [:],
            surface_inventory: .init(surface_count: 0, surfaces: []),
            mobile: .init(
                profile: "agentos.mobile-node/v0.1",
                transport: .init(mode: "push-assisted", provider: "apns"),
                presence: "foreground",
                executors: [
                    .init(
                        executor_id: "mobile.notification",
                        capabilities: ["notification.present"],
                        state: "ready"
                    )
                ]
            )
        )
    }
}

final class AgentOSMobileAPI {
    private let session: URLSession

    init(session: URLSession = .shared) {
        self.session = session
    }

    private func post<T: Encodable>(_ base: URL, path: String, body: T) async throws -> [String: Any] {
        let url = base.appendingPathComponent(path)
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONEncoder().encode(body)
        let (data, response) = try await session.data(for: request)
        guard let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode) else {
            throw MobileNodeError.invalidResponse
        }
        guard let object = try JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            throw MobileNodeError.invalidResponse
        }
        return object
    }

    struct JoinRequestBody: Encodable {
        let manifest: NodeManifest
        let expires_minutes: Int
    }

    struct JoinStatusBody: Encodable {
        let request_id: String
        let claim_secret: String
    }

    func requestJoin(oneURL: URL, manifest: NodeManifest) async throws -> [String: Any] {
        try await post(oneURL, path: "v1/join/request", body: JoinRequestBody(manifest: manifest, expires_minutes: 10))
    }

    func joinStatus(oneURL: URL, requestID: String, claimSecret: String) async throws -> [String: Any] {
        try await post(oneURL, path: "v1/join/status", body: JoinStatusBody(request_id: requestID, claim_secret: claimSecret))
    }

    func claimJoin(oneURL: URL, requestID: String, claimSecret: String) async throws -> [String: Any] {
        try await post(oneURL, path: "v1/join/claim", body: JoinStatusBody(request_id: requestID, claim_secret: claimSecret))
    }
}
