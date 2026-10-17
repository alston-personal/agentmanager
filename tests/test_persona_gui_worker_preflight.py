import io
import json
import unittest
from unittest.mock import patch
from scripts.persona_gui_worker_preflight import inspect

class Response:
    def __init__(self, obj):
        self.obj=obj
    def __enter__(self): return self
    def __exit__(self,*a): pass
    def read(self,n): return json.dumps(self.obj).encode()

class TestGuiPreflight(unittest.TestCase):
    def test_all_unreachable(self):
        def unreachable(*a,**kw): raise OSError("offline")
        d=inspect(unreachable)
        self.assertEqual(d["status"],"BLOCKED")
        self.assertFalse(d["identity_verified"])
        self.assertFalse(d["write_performed"])
    def test_browser_is_not_identity(self):
        def browser(*a,**kw): return Response({"Browser":"Chrome/120","Protocol-Version":"1.3"})
        d=inspect(browser)
        self.assertEqual(d["status"],"TRANSPORT_ONLY")
        self.assertEqual(d["reason"],"IDENTITY_NOT_VERIFIED")
        self.assertFalse(d["for_you_read_verified"])
        self.assertEqual(d["candidate_count"],0)
if __name__=="__main__": unittest.main()
