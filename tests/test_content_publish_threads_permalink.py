from agentos_node.social.contracts import SocialRequest
from agentos_node.social.credentials import AccountBinding, EphemeralCredentialVault
from agentos_node.social.governance import RuntimeWriteAcceptance
from agentos_node.social.threads import ThreadsCapability, ThreadsProviderConfig


class Transport:
    def __init__(self):
        self.calls=[]

    def config(self):
        return ThreadsProviderConfig("app","secret","https://example.test/callback")

    def api(self,path,*,token,method="GET",params=None):
        assert token=="TOKEN"
        self.calls.append((path,method,dict(params or {})))
        if path=="me/threads":
            return {"id":"thread-1"}
        if path=="thread-1":
            return {"permalink":"https://www.threads.net/@oursong_alstonhuang/post/thread-1"}
        raise AssertionError(path)


def test_threads_success_receipt_reads_permalink_without_changing_write_result():
    vault=EphemeralCredentialVault()
    binding="content-publish:threads:persona:123"
    vault.bind(AccountBinding(binding,"content-publish","threads","123","oursong_alstonhuang"),"TOKEN")
    transport=Transport()
    capability=ThreadsCapability(vault,transport)
    req=SocialRequest(
        product_id="content-publish",
        platform="threads",
        operation="publish",
        account_binding_id=binding,
        target_account_id="123",
        primary_text="hello",
        write_intent_id="zeus-1234567890abcdef12345678",
    )
    acceptance=RuntimeWriteAcceptance(
        "accept-1","content-publish","threads",frozenset({"publish"}),frozenset({binding})
    )
    receipt=capability.publish(req,acceptance=acceptance)
    assert receipt["ok"] is True
    assert receipt["platform_object_id"]=="thread-1"
    assert receipt["permalink"]=="https://www.threads.net/@oursong_alstonhuang/post/thread-1"
    assert transport.calls[0][0]=="me/threads"
    assert transport.calls[-1]==("thread-1","GET",{"fields":"permalink"})
