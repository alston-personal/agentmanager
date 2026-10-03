import importlib.util, json, tempfile, unittest
from pathlib import Path

SPEC=importlib.util.spec_from_file_location("hb",Path(__file__).resolve().parents[1]/"scripts/persona_pdca_heartbeat_user.py")
hb=importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(hb)

class HeartbeatDiscoveryTests(unittest.TestCase):
    def test_discovers_all_enabled_running_personas_only(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            def seed(slug,pid,enabled=True,status="RUNNING"):
                d=root/"personas"/slug/"pdca"; d.mkdir(parents=True)
                (d/"config.json").write_text(json.dumps({"schema":"agentos.persona-pdca-config/v1","persona_id":pid,"enabled":enabled}))
                (d/"state.json").write_text(json.dumps({"schema":"agentos.persona-pdca-state/v1","persona_id":pid,"cycle":0,"status":status}))
            seed("sunlake-milkcat","sunlake-milkcat-ai-001")
            seed("oursong_alstonhuang","oursong-alstonhuang-001")
            seed("disabled","disabled-001",False)
            rows=hb.active_personas(root)
            self.assertEqual([x[0].name for x in rows],["oursong_alstonhuang","sunlake-milkcat"])
            self.assertEqual({x[2]["cycle"] for x in rows},{0})

if __name__=="__main__": unittest.main()
