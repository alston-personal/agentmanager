#!/usr/bin/env python3
from pathlib import Path

path = Path('agent_core/realm_server.py')
text = path.read_text(encoding='utf-8')
marker = "'/v1/controller/dispatch'"
if marker in text:
    print('realm_controller_dispatch_patch=ALREADY_PRESENT')
    raise SystemExit(0)

import_anchor = 'from agent_core.node_bootstrap import bootstrap_snapshot, record_join_regression\n'
if import_anchor not in text:
    raise SystemExit('controller import anchor missing')
text = text.replace(import_anchor, 'from agent_core.controller_service import ControllerService\n' + import_anchor, 1)

route_anchor = "            if self.path == '/v1/resolve':\n"
route = """            if self.path == '/v1/controller/dispatch':\n                body = self._json_body()\n                result = ControllerService(self.fabric).dispatch(body)\n                self._send(200, result)\n                return\n"""
if route_anchor not in text:
    raise SystemExit('controller route anchor missing')
text = text.replace(route_anchor, route + route_anchor, 1)
compile(text, str(path), 'exec')
path.write_text(text, encoding='utf-8')
print('realm_controller_dispatch_patch=PASS')
