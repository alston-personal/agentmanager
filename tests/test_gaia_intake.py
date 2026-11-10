import unittest

from agent_core.gaia_intake import Asset, Disposition, Proposal, review


MOBILE = Asset("project://mobile-node", "project", ("Mobile Node",))
MEDIA = Asset("capability://photo-index", "capability", capabilities=("photo.index",))


class GaiaIntakeTest(unittest.TestCase):
    def test_existing_mobile_project_is_extended_not_recreated(self):
        d = review(Proposal("Personal Device Secretary", "project",
                            related_asset_ids=("project://mobile-node",)),
                   (MOBILE, MEDIA), registry_complete=True)
        self.assertEqual(d.disposition, Disposition.EXTEND_PROJECT)
        self.assertEqual(d.canonical_parent, MOBILE.canonical_id)

    def test_existing_capability_is_reused(self):
        d = review(Proposal("Index photos", "capability",
                            required_capabilities=("photo.index",)),
                   (MOBILE, MEDIA), registry_complete=True)
        self.assertEqual(d.disposition, Disposition.USE_EXISTING)

    def test_unknown_new_project_requires_approval(self):
        d = review(Proposal("Unrelated new app", "project"), (MOBILE,),
                   registry_complete=True)
        self.assertEqual(d.disposition, Disposition.NEEDS_HUMAN_APPROVAL)

    def test_fails_closed_without_complete_registry(self):
        d = review(Proposal("Mobile Node", "project"), (MOBILE,),
                   registry_complete=False)
        self.assertEqual(d.disposition, Disposition.NEEDS_EVIDENCE)

    def test_fails_closed_on_ambiguous_or_unknown_link(self):
        a = Asset("project://other", "project", aliases=("Mobile Node",))
        d = review(Proposal("Mobile Node", "project"), (MOBILE, a),
                   registry_complete=True)
        self.assertEqual(d.disposition, Disposition.NEEDS_EVIDENCE)
        d = review(Proposal("Mobile Node", "project",
                            related_asset_ids=("project://missing",)),
                   (MOBILE,), registry_complete=True)
        self.assertEqual(d.disposition, Disposition.NEEDS_EVIDENCE)

    def test_trust_boundary_requires_explicit_approval(self):
        d = review(Proposal("Mobile Node", "project",
                            related_asset_ids=("project://mobile-node",),
                            requests_new_trust_boundary=True),
                   (MOBILE,), registry_complete=True)
        self.assertEqual(d.disposition, Disposition.NEEDS_HUMAN_APPROVAL)


if __name__ == "__main__":
    unittest.main()
