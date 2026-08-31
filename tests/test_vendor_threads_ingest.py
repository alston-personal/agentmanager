from types import SimpleNamespace

from agentos_node.social import vendor_ingest


class FakeThreadsCapability:
    def __init__(self, credential_ref='threads/default'):
        self.credential_ref = credential_ref

    def replies_read(self, thread_id, limit=100):
        return SimpleNamespace(
            ok=True,
            permalink='https://www.threads.com/example/post/demo',
            result={'replies': [
                {'id': 'r1', 'text': '推薦某某水電', 'timestamp': '2026-08-30T01:00:00Z', 'username': 'alice', 'permalink': 'https://threads/r1'},
                {'id': 'r2', 'text': '有人用過另一家嗎？', 'timestamp': '2026-08-30T02:00:00Z', 'username': 'bob', 'permalink': 'https://threads/r2'},
            ]},
            to_dict=lambda: {'schema': 'agentos.social-receipt/v0.1', 'ok': True},
        )


def test_vendor_ingest_preserves_raw_evidence_without_scoring(monkeypatch):
    monkeypatch.setattr(vendor_ingest, 'ThreadsCapability', FakeThreadsCapability)
    batch = vendor_ingest.collect_thread_replies('thread-1', source_url='https://threads/source')
    assert batch['ok'] is True
    assert batch['evidence_count'] == 2
    assert batch['evidence'][0]['text'] == '推薦某某水電'
    assert batch['evidence'][0]['status'] == 'unreviewed'
    assert 'score' not in batch['evidence'][0]
    assert batch['evidence'][1]['text'] == '有人用過另一家嗎？'
