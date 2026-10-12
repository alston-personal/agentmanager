from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from scripts.gpt_web_response_bridge import (
    _chatgpt_target,
    _focus_composer,
    _click_send,
    _confirm_submit,
    _open_target_connection,
    _responsive_chatgpt_target,
    _validate_request,
    atomic_json,
)


class GptWebResponseBridgeTests(unittest.TestCase):
    def request(self):
        return {
            "schema": "agentos.session-request/v0.1",
            "request_id": "session-1",
            "provider": "gpt-web",
            "operation": "harvest",
            "session_id": "chatgpt-web:1",
            "payload": {
                "schema": "agentos.gpt-web-response-harvest/v0.1",
                "selector": "assistant.response_by_request_id",
                "request_id": "invoice:req:12345678",
                "max_characters": 65536,
            },
        }

    def test_accepts_only_scoped_harvest(self):
        session_id, request_id, inner = _validate_request(self.request())
        self.assertEqual((session_id, request_id), ("chatgpt-web:1", "invoice:req:12345678"))
        self.assertEqual(inner["selector"], "assistant.response_by_request_id")

    def test_rejects_arbitrary_selector(self):
        payload = self.request()
        payload["payload"]["selector"] = "body.innerText"
        with self.assertRaises(ValueError):
            _validate_request(payload)

    def test_atomic_json_round_trip(self):
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "x.json"
            atomic_json(target, {"ok": True})
            self.assertIn('"ok": true', target.read_text())

    def test_accepts_scoped_vision_invoke(self):
        payload = self.request()
        payload["operation"] = "invoke"
        payload["payload"] = {
            "schema":"agentos.gpt-web-vision-invoke/v0.1",
            "request_id":"invoice:req:12345678",
            "capability":"vision.invoice.extract",
            "image_path":"/home/ubuntu/agentmanager/benchmarks/invoice_handwriting/fixtures/x.png",
            "prompt":"return json with invoice:req:12345678",
        }
        session_id, request_id, inner = _validate_request(payload)
        self.assertEqual(session_id, "chatgpt-web:1")
        self.assertEqual(request_id, "invoice:req:12345678")
        self.assertEqual(inner["capability"], "vision.invoice.extract")

    def test_chatgpt_target_prefers_page_with_websocket(self):
        targets = [
            {"type":"page","url":"https://example.com/","webSocketDebuggerUrl":"ws://x"},
            {"type":"page","url":"https://chatgpt.com/c/123","webSocketDebuggerUrl":"ws://chat"},
        ]
        with patch("scripts.gpt_web_response_bridge._targets", return_value=targets):
            target = _chatgpt_target("http://127.0.0.1:9222")
        self.assertEqual(target["webSocketDebuggerUrl"], "ws://chat")

    def test_missing_chatgpt_target_can_bootstrap(self):
        created = {"id":"p1","type":"page","url":"https://chatgpt.com/","webSocketDebuggerUrl":"ws://chat"}
        with patch("scripts.gpt_web_response_bridge._targets", return_value=[]), \
             patch("scripts.gpt_web_response_bridge._create_target", return_value=created):
            target = _chatgpt_target("http://127.0.0.1:9222", create_if_missing=True)
        self.assertEqual(target["id"], "p1")

    def test_responsive_target_rejects_when_existing_and_fresh_are_unresponsive(self):
        stale={"id":"p1","type":"page","url":"https://chatgpt.com/","webSocketDebuggerUrl":"ws://dead"}
        fresh={"id":"p2","type":"page","url":"https://chatgpt.com/","webSocketDebuggerUrl":"ws://fresh"}
        with patch("scripts.gpt_web_response_bridge._chatgpt_target", return_value=stale), \
             patch("scripts.gpt_web_response_bridge._targets", return_value=[stale, fresh]), \
             patch("scripts.gpt_web_response_bridge._create_target", return_value=fresh), \
             patch("scripts.gpt_web_response_bridge._open_target_connection", side_effect=TimeoutError("CDP_WS_CONNECT_TIMEOUT")), \
             patch("scripts.gpt_web_response_bridge.time.sleep"):
            with self.assertRaisesRegex(RuntimeError, "CHATGPT_CDP_TARGET_UNRESPONSIVE"):
                _responsive_chatgpt_target("http://127.0.0.1:9222")

    def test_browser_session_fallback_when_page_socket_stalls(self):
        target={"id":"p1","type":"page","url":"https://chatgpt.com/","webSocketDebuggerUrl":"ws://page"}
        direct = Mock()
        direct.evaluate.side_effect = TimeoutError("CDP_COMMAND_RECV_TIMEOUT:Runtime.evaluate")
        browser = Mock()
        browser.call.side_effect = [
            {"product":"Chrome/1"},
            {"sessionId":"sid-1"},
        ]
        browser.evaluate.return_value = "https://chatgpt.com/c/abc"

        calls=[direct,browser]
        with patch("scripts.gpt_web_response_bridge.CdpPage", side_effect=calls), \
             patch("scripts.gpt_web_response_bridge._browser_ws_url", return_value="ws://browser"):
            endpoint = _open_target_connection("http://127.0.0.1:9222", target)

        self.assertEqual(endpoint.mode, "browser-session")
        self.assertEqual(endpoint.session_id, "sid-1")
        direct.close.assert_called_once()
        endpoint.close()


    def test_unresponsive_existing_target_bootstraps_fresh_target(self):
        from unittest.mock import patch
        stale = {"id":"stale","type":"page","url":"https://chatgpt.com/","webSocketDebuggerUrl":"ws://stale"}
        fresh = {"id":"fresh","type":"page","url":"https://chatgpt.com/","webSocketDebuggerUrl":"ws://fresh"}
    
        class Endpoint:
            mode="page-ws"
            def __init__(self, href): self.href=href
            def evaluate(self, expr): return self.href
            def close(self): pass
    
        attempts=[]
        def open_target(_cdp,item):
            attempts.append(item["id"])
            if item["id"]=="stale":
                raise TimeoutError("stale")
            return Endpoint("https://chatgpt.com/")
    
        with patch("scripts.gpt_web_response_bridge._chatgpt_target", return_value=stale), \
             patch("scripts.gpt_web_response_bridge._targets", side_effect=[
                 [stale],
                 [stale, fresh],
             ]), \
             patch("scripts.gpt_web_response_bridge._create_target", return_value=fresh), \
             patch("scripts.gpt_web_response_bridge._open_target_connection", side_effect=open_target):
            from scripts.gpt_web_response_bridge import _responsive_chatgpt_target
            target, href, mode = _responsive_chatgpt_target("http://127.0.0.1:9222")
        self.assertEqual(target["id"], "fresh")
        self.assertEqual(href, "https://chatgpt.com/")
        self.assertEqual(mode, "page-ws")
        self.assertIn("stale", attempts)
        self.assertIn("fresh", attempts)
    

if __name__ == "__main__":
    unittest.main()


class GptWebComposerDiscoveryTests(unittest.TestCase):
    def test_focus_composer_accepts_current_selector(self):
        page=Mock()
        page.evaluate.return_value={
            "ok":True,
            "selector":"[data-testid=\"composer-text-input\"]",
            "tag":"DIV",
            "contenteditable":"true",
            "role":"textbox",
            "testid":"composer-text-input",
        }
        found=_focus_composer(page,timeout_seconds=0.2)
        self.assertTrue(found["ok"])
        self.assertEqual(found["testid"],"composer-text-input")

    def test_focus_composer_stops_on_login_required(self):
        page=Mock()
        page.evaluate.side_effect=[
            {"ok":False},
            {
                "href":"https://chatgpt.com/",
                "title":"ChatGPT",
                "readyState":"complete",
                "fileInputs":0,
                "loginRequired":True,
                "candidates":[],
            },
        ]
        with self.assertRaisesRegex(RuntimeError,"GPT_WEB_LOGIN_REQUIRED"):
            _focus_composer(page,timeout_seconds=0.2)


class GptWebSubmitVerificationTests(unittest.TestCase):
    def test_click_send_uses_ready_control(self):
        page=Mock()
        page.evaluate.return_value={"ok":True,"selector":"[data-testid=\"send-button\"]"}
        result=_click_send(page,request_id="invoice:req:12345678",timeout_seconds=0.2)
        self.assertTrue(result["ok"])
        self.assertEqual(result["selector"],'[data-testid="send-button"]')

    def test_confirm_submit_accepts_generation_start(self):
        page=Mock()
        page.evaluate.return_value={
            "composerHasRequest":False,
            "composerChars":0,
            "send":[],
            "assistantCount":0,
            "lastAssistantChars":0,
            "lastAssistantHasRequest":False,
            "generating":True,
        }
        result=_confirm_submit(
            page,
            request_id="invoice:req:12345678",
            baseline_assistants=0,
            timeout_seconds=0.2,
        )
        self.assertTrue(result["generating"])

    def test_confirm_submit_times_out_when_nothing_changes(self):
        page=Mock()
        page.evaluate.return_value={
            "composerHasRequest":True,
            "composerChars":42,
            "send":[],
            "assistantCount":0,
            "lastAssistantChars":0,
            "lastAssistantHasRequest":False,
            "generating":False,
        }
        with patch("scripts.gpt_web_response_bridge.time.sleep"):
            with self.assertRaisesRegex(RuntimeError,"GPT_WEB_SUBMIT_NOT_CONFIRMED"):
                _confirm_submit(
                    page,
                    request_id="invoice:req:12345678",
                    baseline_assistants=0,
                    timeout_seconds=0.001,
                )

    
class GptWebFalseSubmitRegressionTests(unittest.TestCase):
    def test_blank_composer_without_user_or_generation_is_not_submission(self):
        page = Mock()
        page.evaluate.return_value = {
            "composerHasRequest": False, "composerChars": 0,
            "assistantCount": 0, "userCount": 0, "correlatedUserCount": 0,
            "generating": False, "send": [],
        }
        with patch("scripts.gpt_web_response_bridge.time.sleep"):
            with self.assertRaisesRegex(RuntimeError, "GPT_WEB_SUBMIT_NOT_CONFIRMED"):
                _confirm_submit(page, request_id="invoice:req:12345678",
                                baseline_assistants=0, baseline_users=0,
                                timeout_seconds=0.001)

    def test_correlated_user_message_confirms_submission(self):
        page = Mock()
        page.evaluate.return_value = {
            "composerHasRequest": False, "composerChars": 0,
            "assistantCount": 0, "userCount": 1, "correlatedUserCount": 1,
            "generating": False, "send": [],
        }
        result = _confirm_submit(page, request_id="invoice:req:12345678",
                                 baseline_assistants=0, baseline_users=0,
                                 timeout_seconds=0.2)
        self.assertEqual(result["correlatedUserCount"], 1)

class GptWebStructuralDiagnosticsTests(unittest.TestCase):
    def test_submission_snapshot_queries_only_structural_dom(self):
        from scripts.gpt_web_response_bridge import _submission_snapshot
        page = Mock()
        page.evaluate.return_value = {
            "pagePath": "/c/test", "roleCounts": {"user": 1},
            "messageNodes": 1, "userCount": 1,
        }
        result = _submission_snapshot(page, "invoice:req:12345678")
        self.assertEqual(result["messageNodes"], 1)
        script = page.evaluate.call_args.args[0]
        self.assertIn("data-message-author-role", script)
        self.assertIn("location.pathname", script)
        self.assertNotIn("console.log", script)


class GptWebRouteCompatibilityTests(unittest.TestCase):
    def test_uc_route_does_not_count_as_verified_reply(self):
        # The bridge must not consider a temporary-chat route successful merely
        # because the send control disappeared and a stop button was once shown.
        from scripts.gpt_web_response_bridge import _confirm_submit
        page = Mock()
        page.evaluate.return_value = {
            "pagePath": "/uc/temporary", "messageNodes": 0,
            "composerChars": 0, "composerHasRequest": False,
            "assistantCount": 0, "userCount": 0,
            "correlatedUserCount": 0, "generating": False,
        }
        with patch("scripts.gpt_web_response_bridge.time.sleep"):
            with self.assertRaisesRegex(RuntimeError, "GPT_WEB_SUBMIT_NOT_CONFIRMED"):
                _confirm_submit(page, request_id="invoice:req:12345678",
                                baseline_assistants=0, baseline_users=0,
                                timeout_seconds=0.001)


class GptWebTargetRoutingTests(unittest.TestCase):
    def test_excludes_uc_target_and_reuses_normal_chat(self):
        from scripts.gpt_web_response_bridge import _page
        normal = {"type": "page", "url": "https://chatgpt.com/c/abc", "webSocketDebuggerUrl": "ws://normal"}
        uc = {"type": "page", "url": "https://chatgpt.com/uc/temp", "webSocketDebuggerUrl": "ws://uc"}
        endpoint = Mock()
        endpoint.evaluate.return_value = normal["url"]
        with patch("scripts.gpt_web_response_bridge._targets", return_value=[normal, uc]), \
             patch("scripts.gpt_web_response_bridge._open_target_connection", return_value=endpoint) as opened:
            self.assertIs(_page("http://127.0.0.1:9222"), endpoint)
        opened.assert_called_once_with("http://127.0.0.1:9222", normal)

    def test_fails_closed_when_fresh_target_redirects_to_uc(self):
        from scripts.gpt_web_response_bridge import _page
        endpoint = Mock()
        endpoint.evaluate.return_value = "https://chatgpt.com/uc/temp"
        fresh = {"type": "page", "url": "https://chatgpt.com/", "webSocketDebuggerUrl": "ws://fresh"}
        with patch("scripts.gpt_web_response_bridge._targets", return_value=[]), \
             patch("scripts.gpt_web_response_bridge._create_target", return_value=fresh), \
             patch("scripts.gpt_web_response_bridge._open_target_connection", return_value=endpoint):
            with self.assertRaisesRegex(RuntimeError, "GPT_WEB_UNSUPPORTED_CONVERSATION_ROUTE"):
                _page("http://127.0.0.1:9222")
        endpoint.close.assert_called_once()


class GptWebAttachmentDiagnosticsTests(unittest.TestCase):
    def test_snapshot_includes_attachment_and_frame_structure_without_contents(self):
        from scripts.gpt_web_response_bridge import _submission_snapshot
        page = Mock()
        page.evaluate.return_value = {
            "frameSummary": [{"visible": True, "sameOrigin": False}],
            "attachmentSummary": {"fileInputs": 1, "imagePreviewCount": 1, "imageElements": 3, "pendingIndicators": 0},
        }
        result = _submission_snapshot(page, "invoice:req:12345678")
        self.assertEqual(result["attachmentSummary"]["imagePreviewCount"], 1)
        script = page.evaluate.call_args.args[0]
        self.assertIn("frameSummary", script)
        self.assertIn("attachmentSummary", script)
        self.assertIn("inputContext", script)
        self.assertIn("errorIndicators", script)
        from scripts.gpt_web_response_bridge import invoke
        import inspect
        self.assertIn("baselineAlertCounts", inspect.getsource(invoke))
        self.assertNotIn("outerHTML", script)
        self.assertNotIn("img.src", script)


class GptWebImageInputContractTests(unittest.TestCase):
    def test_invoke_uses_image_accept_input_and_confirms_file_selection(self):
        from scripts import gpt_web_response_bridge as bridge
        import inspect
        source = inspect.getsource(bridge.invoke)
        self.assertIn("includes('image')", source)
        self.assertIn("Runtime.callFunctionOn", source)
        self.assertIn("GPT_WEB_FILE_SELECTION_UNVERIFIED", source)


class GptWebFileSelectionClassificationTests(unittest.TestCase):
    def test_file_selection_distinguishes_unverified_from_confirmed(self):
        import inspect
        from scripts.gpt_web_response_bridge import invoke
        source = inspect.getsource(invoke)
        self.assertIn("GPT_WEB_FILE_SELECTION_UNVERIFIED", source)
        self.assertIn("imagePreviewCount", source)


class GptWebUploadSettlementTests(unittest.TestCase):
    def test_upload_settle_has_bounded_poll_and_safe_file_state(self):
        import inspect
        from scripts.gpt_web_response_bridge import invoke, _submission_snapshot
        source = inspect.getsource(invoke)
        self.assertIn("upload_deadline = time.monotonic() + 8.0", source)
        self.assertIn("GPT_WEB_FILE_SELECTION_UNVERIFIED", source)
        page = Mock()
        page.evaluate.return_value = {"attachmentSummary": {"fileInputStates": [{"acceptsImage": True, "selectedCount": 1}]}}
        state = _submission_snapshot(page, "invoice:req:12345678")
        self.assertEqual(state["attachmentSummary"]["fileInputStates"][0]["selectedCount"], 1)
        self.assertIn("fileInputStates", page.evaluate.call_args.args[0])


class GptWebActiveImageInputTests(unittest.TestCase):
    def test_image_input_prefers_last_connected_matching_candidate(self):
        import inspect
        from scripts.gpt_web_response_bridge import invoke
        source = inspect.getsource(invoke)
        self.assertIn("el.isConnected", source)
        self.assertIn(".at(-1)", source)


class GptWebNativeFileEventEvidenceTests(unittest.TestCase):
    def test_native_file_event_probe_is_installed_before_cdp_selection(self):
        import inspect
        from scripts.gpt_web_response_bridge import invoke
        body = inspect.getsource(invoke)
        self.assertLess(body.index("__agentosUploadProbe ="), body.index('DOM.setFileInputFiles'))
        self.assertIn("selectedCountAtEvent", body)
        self.assertIn("event.isTrusted", body)
        self.assertNotIn("FileReader", body)


class GptWebUploadNetworkProbeTests(unittest.TestCase):
    def test_network_probe_never_exposes_urls_or_headers(self):
        from scripts.gpt_web_response_bridge import CdpPage
        page = CdpPage.__new__(CdpPage)
        page.upload_network_probe = None
        page._upload_request_ids = set()
        page.begin_upload_network_probe()
        page.observe_upload_event({"method": "Network.requestWillBeSent", "params": {
            "requestId": "r1", "request": {"method": "POST", "url": "https://chatgpt.com/backend-api/files?secret=bad", "headers": {"Authorization": "secret"}, "postData": "invoice"}}})
        page.observe_upload_event({"method": "Network.responseReceived", "params": {"requestId": "r1", "response": {"status": 403, "url": "https://chatgpt.com/private"}}})
        self.assertEqual(page.upload_network_probe["postRequests"], 1)
        self.assertEqual(page.upload_network_probe["responseStatuses"]["403"], 1)
        self.assertNotIn("secret", str(page.upload_network_probe))
        self.assertNotIn("invoice", str(page.upload_network_probe))
        page.observe_upload_event({"method": "Network.requestWillBeSent", "params": {
            "requestId": "r2", "request": {"method": "POST",
            "url": "https://uploads.example.invalid/file?token=private",
            "headers": {"Cookie": "private"}, "postData": "raw-invoice-image"}}})
        page.observe_upload_event({"method": "Network.responseReceived", "params": {
            "requestId": "r2", "response": {"status": 201}}})
        self.assertEqual(page.upload_network_probe["postRequests"], 2)
        self.assertEqual(page.upload_network_probe["postHostFamilies"], {"chatgpt": 1, "other": 1})
        self.assertEqual(page.upload_network_probe["responseStatuses"]["2xx"], 1)
        self.assertNotIn("uploads.example.invalid", str(page.upload_network_probe))
        self.assertNotIn("private", str(page.upload_network_probe))


class UploadCorrelationTests(unittest.TestCase):
    def test_request_class_uses_private_ids_only(self):
        from scripts.gpt_web_response_bridge import CdpPage
        page = CdpPage.__new__(CdpPage)
        page.upload_network_probe = None
        page.begin_upload_network_probe()
        page.observe_upload_event({"method": "Network.requestWillBeSent", "params": {"requestId": "alpha", "request": {"method": "POST", "url": "https://chatgpt.com/backend-api/files?token=secret"}}})
        page.observe_upload_event({"method": "Network.responseReceived", "params": {"requestId": "alpha", "response": {"status": 201}}})
        page.observe_upload_event({"method": "Network.loadingFailed", "params": {"requestId": "alpha"}})
        self.assertEqual(page.upload_network_probe["categories"]["file"]["requests"], 1)
        self.assertEqual(page.upload_network_probe["categories"]["file"]["statuses"]["2xx"], 1)
        self.assertEqual(page.upload_network_probe["categories"]["file"]["failures"], 1)
        self.assertNotIn("secret", str(page.upload_network_probe))


class NativeGuiUploadProbeContractTests(unittest.TestCase):
    def test_probe_never_sends_user_message(self):
        from pathlib import Path
        src=Path("scripts/gpt_web_gui_upload_probe.py").read_text(encoding="utf-8")
        self.assertIn("Page.setInterceptFileChooserDialog",src)
        self.assertIn("DOM.setFileInputFiles",src)
        self.assertIn("Input.dispatchMouseEvent",src)
        self.assertNotIn("Input.insertText",src)
        self.assertNotIn("_click_send(",src)
        self.assertNotIn("conversation.submit",src)
        self.assertIn("Target.closeTarget",src)
        self.assertIn("_create_target(",src)

    def test_native_chooser_event_handled_structurally(self):
        import inspect
        from scripts.gpt_web_response_bridge import CdpPage
        src=inspect.getsource(CdpPage.call)
        self.assertIn("Page.fileChooserOpened",src)
        self.assertIn("backendNodeId",src)


class NativeChooserMenuContractTests(unittest.TestCase):
    def test_probe_supports_scoped_second_click_and_no_submit(self):
        from pathlib import Path
        src=Path("scripts/gpt_web_gui_upload_probe.py").read_text(encoding="utf-8")
        self.assertIn("ATTACH_MENU_UPLOAD_ITEM_NOT_FOUND",src)
        self.assertIn("FILE_CHOOSER_NOT_OPENED_AFTER_MENU",src)
        self.assertIn("'[role=\"menuitem\"]",src)
        self.assertNotIn("Input.insertText",src)
        self.assertNotIn("_click_send(",src)


class NativeChooserTriggerExclusionContractTests(unittest.TestCase):
    def test_second_click_cannot_reclick_attachment_trigger(self):
        from pathlib import Path
        code=Path("scripts/gpt_web_gui_upload_probe.py").read_text(encoding="utf-8")
        self.assertIn("centerX-triggerX",code)
        self.assertIn("centerY-triggerY",code)
        self.assertIn("json.dumps(x)",code)
        self.assertNotIn("Input.insertText",code)


class ImageStructureWithoutContentTests(unittest.TestCase):
    def test_snapshot_captures_form_image_context_without_urls(self):
        from unittest.mock import Mock
        from scripts.gpt_web_response_bridge import _submission_snapshot
        page=Mock()
        page.evaluate.return_value={"attachmentSummary":{}}
        _submission_snapshot(page,"safe-id")
        code=page.evaluate.call_args.args[0]
        self.assertIn("imageStructure",code)
        self.assertIn("inFormBlob",code)
        self.assertIn("attachmentControlCount",code)
        self.assertNotIn("img.src",code)


class AttachmentGrowthTests(unittest.TestCase):
    def test_requires_new_blob_and_new_remove_control(self):
        from scripts.gpt_web_response_bridge import _attachment_growth
        def shot(blob, remove):
            return {"attachmentSummary": {"imageStructure": {"inFormBlob": blob}, "attachmentControlCount":remove}}
        self.assertTrue(_attachment_growth(shot(0,0),shot(1,1)))
        self.assertFalse(_attachment_growth(shot(4,4),shot(4,4)))
        self.assertFalse(_attachment_growth(shot(0,0),shot(1,0)))
        self.assertFalse(_attachment_growth(shot(0,0),shot(0,1)))
        self.assertFalse(_attachment_growth({},shot(0,0)))
