import base64
import unittest
from unittest import mock

from agentos_node import semantic_preview as semantic_preview_module


class TestSemanticPreviewPowerShellBackend(unittest.TestCase):
    def test_capture_region_uses_bounded_dimensions(self):
        payload=b"jpeg-bytes"

        class Completed:
            returncode=0
            stdout=base64.b64encode(payload).decode("ascii")+"\n"
            stderr=""

        with mock.patch.object(semantic_preview_module.subprocess, "run", return_value=Completed()) as run:
            raw,w,h=semantic_preview_module._capture_region_powershell(
                {
                    "left":10,
                    "top":20,
                    "width":1920,
                    "height":1080,
                    "relative_left":0,
                    "relative_top":0,
                },
                max_pixels=160000,
                quality=55,
            )

        self.assertEqual(raw,payload)
        self.assertLessEqual(w*h,160000)
        kwargs=run.call_args.kwargs
        env=kwargs["env"]
        self.assertEqual(env["AGENTOS_LEFT"],"10")
        self.assertEqual(env["AGENTOS_TOP"],"20")
        self.assertEqual(env["AGENTOS_SRC_W"],"1920")
        self.assertEqual(env["AGENTOS_SRC_H"],"1080")
        self.assertEqual(kwargs["timeout"],15)

    def test_semantic_preview_returns_foreground_only_contract(self):
        session={
            "pid":1,
            "process_session_id":1,
            "active_console_session_id":1,
            "interactive":True,
            "username":"u",
            "session_name":"Console",
        }
        window={
            "hwnd":1,
            "title":"Example",
            "pid":22,
            "process_name":"example.exe",
            "bounds":{
                "left":100,"top":200,"right":900,"bottom":800,
                "width":800,"height":600,
            },
        }
        with mock.patch.object(semantic_preview_module, "_require_windows"), \
             mock.patch.object(semantic_preview_module, "_session_info", return_value=session), \
             mock.patch.object(semantic_preview_module, "_foreground_window", return_value=window), \
             mock.patch.object(semantic_preview_module, "_capture_region_powershell", return_value=(b"jpg",400,300)):
            result=semantic_preview_module.semantic_preview({"max_pixels":160000})

        self.assertTrue(result["read_only"])
        self.assertEqual(result["mode"],"foreground-window-only")
        self.assertEqual(result["capture_backend"],"powershell-system-drawing")
        self.assertEqual(result["preview"]["mime_type"],"image/jpeg")
        self.assertEqual(result["preview"]["width"],400)
        self.assertEqual(result["foreground"]["process_name"],"example.exe")
        self.assertNotIn("full-window-enumeration", result)


if __name__ == "__main__":
    unittest.main()
