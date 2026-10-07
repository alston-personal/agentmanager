import SwiftUI

struct ContentView: View {
    @EnvironmentObject var model: EnrollmentModel

    var body: some View {
        NavigationStack {
            Form {
                Section("AgentOS ONE") {
                    TextField("ONE URL", text: $model.oneURLText)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                    TextField("Node ID", text: $model.nodeID)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                }

                Section("Enrollment") {
                    if !model.userCode.isEmpty {
                        LabeledContent("Approval code", value: model.userCode)
                    }
                    Text(model.status)
                    Button("Request join") {
                        Task { await model.requestJoin() }
                    }
                    Button("Check approval and claim") {
                        Task { await model.checkApprovalAndClaim() }
                    }
                    .disabled(model.userCode.isEmpty)
                }

                if model.enrolled {
                    Section("Node") {
                        Label("Enrolled", systemImage: "checkmark.circle.fill")
                        Text("Next: heartbeat, push wake, and executors")
                            .font(.footnote)
                    }
                }
            }
            .navigationTitle("AgentOS Mobile")
        }
    }
}
