import XCTest
@testable import AgentOSMobileCore

final class AgentOSMobileCoreTests: XCTestCase {
    func testJoinLinkParsesONEEndpoint() throws {
        let url = try XCTUnwrap(URL(string: "agentos://join?one=https%3A%2F%2Fone.example.test&v=v1"))
        let link = try AgentOSJoinLink(url: url)
        XCTAssertEqual(link.oneURL.absoluteString, "https://one.example.test")
        XCTAssertEqual(link.version, "v1")
    }

    func testJoinLinkRejectsUnsupportedVersion() throws {
        let url = try XCTUnwrap(URL(string: "agentos://join?one=https%3A%2F%2Fone.example.test&v=v2"))
        XCTAssertThrowsError(try AgentOSJoinLink(url: url))
    }

    func testIPhoneManifestUsesCanonicalNodeSchema() {
        let manifest = NodeManifest.iphone(nodeID: "iphone-test")
        XCTAssertEqual(manifest.schema, "agentos.node-manifest/v0.1")
        XCTAssertEqual(manifest.mobile.profile, "agentos.mobile-node/v0.1")
        XCTAssertEqual(manifest.mobile.transport.provider, "apns")
        XCTAssertTrue(manifest.capabilities.contains("notification.present"))
    }
}
