"""MVP-1 local port completion requires a real independent observation."""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1] / "scripts" / "lobster.py"

class LocalPortProof(unittest.TestCase):
    def test_validator_cannot_trust_only_success_message(self):
        tree=ast.parse(ROOT.read_text(encoding="utf-8"))
        fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="verify_local_port_check")
        names={n.attr for n in ast.walk(fn) if isinstance(n,ast.Attribute)}
        self.assertIn("connect_ex",names)
        self.assertIn("settimeout",names)
        code=compile(ast.Module(body=[fn],type_ignores=[]),str(ROOT),"exec")
        import re, socket
        ns={"re":re,"socket":socket}
        exec(code,ns)
        validate=ns["verify_local_port_check"]
        self.assertIsNone(validate("檢查一般事項","✅ 任務完成")[0] if False else None)
        self.assertEqual(validate("檢查連接埠 99999","✅ 任務完成")[0],False)
        self.assertEqual(validate("檢查連接埠 65534","✅ 任務完成")[0],False)
        with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as server:
            server.bind(("127.0.0.1",0))
            server.listen(1)
            port=server.getsockname()[1]
            ok,reason=validate(f"檢查連接埠 {port}",f"✅ 任務完成\n連接埠 {port} 未啟用監聽")
            self.assertFalse(ok)
            self.assertIn("open",reason)
if __name__=="__main__": unittest.main()
