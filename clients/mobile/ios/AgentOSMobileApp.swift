import SwiftUI

@main
struct AgentOSMobileApp: App {
    @StateObject private var model = EnrollmentModel()

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(model)
                .onOpenURL { url in
                    model.acceptJoinLink(url)
                }
        }
    }
}

@MainActor
final class EnrollmentModel: ObservableObject {
    @Published var nodeID = "iphone-alston"
    @Published var oneURLText = ""
    @Published var userCode = ""
    @Published var status = "Not connected"
    @Published var enrolled = false

    private let api = AgentOSMobileAPI()
    private let credentialStore = AgentOSKeychain()
    private var requestID: String?
    private var claimSecret: String?

    func acceptJoinLink(_ url: URL) {
        do {
            let link = try AgentOSJoinLink(url: url)
            oneURLText = link.oneURL.absoluteString
            status = "ONE endpoint loaded"
        } catch {
            status = "Invalid AgentOS join link"
        }
    }

    func requestJoin() async {
        do {
            guard let oneURL = URL(string: oneURLText), !nodeID.isEmpty else {
                status = "ONE URL and Node ID are required"
                return
            }
            let result = try await api.requestJoin(
                oneURL: oneURL,
                manifest: .iphone(nodeID: nodeID)
            )
            guard
                let request = result["request_id"] as? String,
                let secret = result["claim_secret"] as? String,
                let code = result["user_code"] as? String
            else {
                status = "ONE returned an invalid join response"
                return
            }
            requestID = request
            claimSecret = secret
            userCode = code
            status = "Pending approval"
        } catch {
            status = "Join request failed"
        }
    }

    func checkApprovalAndClaim() async {
        do {
            guard
                let oneURL = URL(string: oneURLText),
                let requestID,
                let claimSecret
            else {
                status = "No pending join request"
                return
            }
            let state = try await api.joinStatus(
                oneURL: oneURL,
                requestID: requestID,
                claimSecret: claimSecret
            )
            let current = state["status"] as? String ?? "unknown"
            guard current == "approved" else {
                status = "Approval status: \(current)"
                return
            }
            let claimed = try await api.claimJoin(
                oneURL: oneURL,
                requestID: requestID,
                claimSecret: claimSecret
            )
            let identity = try api.completeClaim(
                response: claimed,
                credentialStore: credentialStore
            )
            enrolled = true
            userCode = ""
            status = "Enrolled as \(identity.nodeID)"
            self.requestID = nil
            self.claimSecret = nil
        } catch {
            status = "Claim failed"
        }
    }
}
