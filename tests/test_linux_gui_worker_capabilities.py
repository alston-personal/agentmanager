import json
from pathlib import Path
from unittest import mock

import agentos_node.thin_client as tc


def test_linux_gui_worker_caps_require_live_cdp_and_novnc(tmp_path):
    cap_root=tmp_path/'.local/share/agentos/gui-worker'
    cap_root.mkdir(parents=True)
    (cap_root/'capability.json').write_text(json.dumps({
        'schema':'agentos.gui-worker/v1',
        'capabilities':['browser.gui','browser.cdp','browser.persistent_profile','desktop.remote_view'],
    }),encoding='utf-8')

    fake_resp=mock.MagicMock()
    fake_resp.__enter__.return_value=fake_resp
    fake_resp.__exit__.return_value=False
    fake_resp.read.return_value=b'{}'

    class Resp:
        def __enter__(self): return self
        def __exit__(self,*a): return False
    with mock.patch.object(tc.Path,'home',return_value=tmp_path), \
         mock.patch.object(tc.platform,'system',return_value='Linux'), \
         mock.patch.object(tc.urllib.request,'urlopen') as urlopen, \
         mock.patch.object(tc.socket,'create_connection') as conn:
        r=Resp()
        urlopen.return_value=r
        with mock.patch.object(tc.json,'load',return_value={'webSocketDebuggerUrl':'ws://127.0.0.1:9222/devtools/browser/x'}):
            caps=tc._linux_gui_worker_capabilities()
    assert caps==['browser.cdp','browser.gui','browser.persistent_profile','desktop.remote_view']
    conn.assert_called_once()


def test_linux_gui_worker_caps_fail_closed_without_readiness(tmp_path):
    with mock.patch.object(tc.Path,'home',return_value=tmp_path), \
         mock.patch.object(tc.platform,'system',return_value='Linux'):
        assert tc._linux_gui_worker_capabilities()==[]
