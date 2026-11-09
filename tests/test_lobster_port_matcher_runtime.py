"""Execute the actual local port validator, not just syntactic checks."""
import ast
import pathlib
import re
import socket
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "lobster.py"

class PortMatcherRuntimeTest(unittest.TestCase):
    def test_actual_validator_dispatches_on_port_work(self):
        root = ast.parse(ROOT.read_text(encoding="utf-8"))
        func = next(n for n in root.body if isinstance(n, ast.FunctionDef)
                    and n.name == "verify_local_port_check")
        namespace = {"re": re, "socket": socket}
        exec(compile(ast.Module(body=[func], type_ignores=[]), str(ROOT), "exec"), namespace)
        verifier = namespace["verify_local_port_check"]
        self.assertIsNone(verifier("檢查報表", "✅ 任務完成"))
        self.assertEqual(verifier("檢查連接埠 65534", "✅ 任務完成")[0], False)
        self.assertEqual(verifier("檢查連接埠 99999", "✅ 任務完成")[1],
                         "BLOCKED: invalid_port")
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            sock.listen(1)
            port = sock.getsockname()[1]
            status, evidence = verifier(
                f"[WI:proof] 檢查連接埠 {port}",
                f"✅ 任務完成：檢查連接埠 {port}\n詳細結果: 連接埠 {port} 未啟用監聽"
            )
            self.assertFalse(status)
            self.assertEqual(evidence, "BLOCKED: port_is_open_on_loopback")

if __name__ == "__main__":
    unittest.main()
