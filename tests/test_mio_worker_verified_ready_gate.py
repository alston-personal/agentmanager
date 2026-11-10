"""Regression: a missing or negative quality result must never yield ready."""
import ast
import pathlib
import unittest


class ReviewAdmissionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source=pathlib.Path(__file__).resolve().parents[1]/"scripts/tryon_render_worker.py"
        tree=ast.parse(source.read_text(encoding="utf-8"))
        fun=next(node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name=="visual_review_accepted")
        module=ast.Module(body=[fun],type_ignores=[])
        namespace={"Any":object}
        exec(compile(ast.fix_missing_locations(module),str(source),"exec"),namespace)
        cls.accept=namespace["visual_review_accepted"]

    def test_only_explicit_verified_true(self):
        for payload in ({},{"state":"verified"},{"state":"candidate","accepted":True},
                        {"state":"rejected","accepted":True},{"state":"verified","accepted":"true"},
                        {"state":"verified","accepted":False}):
            self.assertFalse(self.accept(payload),payload)
        self.assertTrue(self.accept({"state":"verified","accepted":True}))


if __name__=="__main__":
    unittest.main()
