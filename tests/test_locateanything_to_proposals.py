"""Contract tests for the open-vocabulary proposal front-end.

The safety property under test is the same one that protects the whole
pipeline: a proposal generator must never coerce an unmapped/ambiguous
detection into ``rice_protect`` or ``weed_target``. Unmapped prompts are
*counted drops*; ambiguous prompts map to ``unknown_vegetation``, never rice.
"""

import unittest

from agrinav.data.locateanything_to_proposals import (
    DEFAULT_PROMPT_MAP,
    ProposalError,
    build_prompt_map,
    build_proposal_doc,
    validate_model_revision,
)
from agrinav.data.sam_box_to_mask import index_proposals


def _unit(**overrides):
    unit = {
        "file_name": "a.png",
        "sha256": "a" * 64,
        "width": 100,
        "height": 100,
        "group_id": "g1",
        "capture_family": "fam1",
        "detections": [],
    }
    unit.update(overrides)
    return unit


class BuildProposalDoc(unittest.TestCase):
    def test_unmapped_prompt_is_a_counted_drop_not_rice(self):
        unit = _unit(
            detections=[
                {"prompt": "some plant", "bbox": [1, 1, 5, 5], "score": 0.99},
            ]
        )
        doc, stats = build_proposal_doc(
            image_units=[unit],
            prompt_map=dict(DEFAULT_PROMPT_MAP),
            model_id="m",
            model_revision="deadbeef",
            score_threshold=0.3,
        )
        self.assertEqual(doc["annotations"], [])
        self.assertEqual(stats["annotations"], 0)
        self.assertTrue(any(k.startswith("unmapped_prompt=") for k in stats["drops"]))
        # crucially: nothing was minted as rice or weed
        self.assertEqual(stats["per_category"], {})

    def test_ambiguous_prompt_maps_to_unknown_vegetation(self):
        unit = _unit(
            detections=[
                {
                    "prompt": "ambiguous vegetation that may not be rice",
                    "bbox": [5, 5, 30, 30],
                    "score": 0.7,
                },
            ]
        )
        doc, stats = build_proposal_doc(
            image_units=[unit],
            prompt_map=dict(DEFAULT_PROMPT_MAP),
            model_id="m",
            model_revision="deadbeef",
            score_threshold=0.3,
        )
        self.assertEqual(stats["per_category"], {"unknown_vegetation": 1})
        self.assertEqual(doc["annotations"][0]["category_id"], 3)

    def test_score_and_oob_boxes_are_dropped_and_counted(self):
        unit = _unit(
            detections=[
                {
                    "prompt": "cultivated rice plants",
                    "bbox": [10, 10, 10, 10],
                    "score": 0.1,
                },  # low score
                {
                    "prompt": "weeds growing among the rice plants",
                    "bbox": [200, 200, 5, 5],
                    "score": 0.9,
                },  # oob
                {
                    "prompt": "cultivated rice plants",
                    "bbox": [10, 10, 20, 20],
                    "score": 0.9,
                },  # kept
            ]
        )
        _doc, stats = build_proposal_doc(
            image_units=[unit],
            prompt_map=dict(DEFAULT_PROMPT_MAP),
            model_id="m",
            model_revision="deadbeef",
            score_threshold=0.5,
        )
        self.assertEqual(stats["annotations"], 1)
        self.assertEqual(stats["drops"]["below_score_threshold"], 1)
        self.assertEqual(stats["drops"]["degenerate_or_oob_box"], 1)

    def test_every_annotation_is_an_unreviewed_proposal_with_provenance(self):
        unit = _unit(
            detections=[
                {"prompt": "cultivated rice plants", "bbox": [10, 10, 20, 20], "score": 0.9},
            ]
        )
        doc, _stats = build_proposal_doc(
            image_units=[unit],
            prompt_map=dict(DEFAULT_PROMPT_MAP),
            model_id="nvidia/LocateAnything-3B",
            model_revision="deadbeef",
            score_threshold=0.3,
            generated_at="2026-07-21T00:00:00Z",
        )
        ann = doc["annotations"][0]
        self.assertEqual(ann["review_status"], "unreviewed_proposal")
        prov = ann["provenance"]
        self.assertEqual(prov["proposal_method"], "model_assisted")
        self.assertEqual(prov["human_edit_state"], "unreviewed")
        self.assertEqual(prov["proposal_model_revision"], "deadbeef")
        self.assertEqual(prov["generated_at"], "2026-07-21T00:00:00Z")

    def test_output_indexes_in_sam_step_without_normalising_to_rice(self):
        unit = _unit(
            detections=[
                {"prompt": "cultivated rice plants", "bbox": [10, 10, 20, 20], "score": 0.9},
                {
                    "prompt": "weeds growing among the rice plants",
                    "bbox": [50, 50, 10, 10],
                    "score": 0.8,
                },
                {
                    "prompt": "ambiguous vegetation that may not be rice",
                    "bbox": [5, 5, 20, 20],
                    "score": 0.9,
                },
            ]
        )
        doc, _stats = build_proposal_doc(
            image_units=[unit],
            prompt_map=dict(DEFAULT_PROMPT_MAP),
            model_id="m",
            model_revision="deadbeef",
            score_threshold=0.3,
        )
        sam_units, sam_drops = index_proposals(doc)
        refinable = sum(len(u["boxes"]) for u in sam_units)
        # only rice + weed are box-refinable; unknown_vegetation is a counted
        # drop at the SAM step, never silently refined as rice.
        self.assertEqual(refinable, 2)
        self.assertEqual(sam_drops.get("category_id=3"), 1)


class Preflight(unittest.TestCase):
    def test_revision_refuses_placeholder_and_bad_sha(self):
        with self.assertRaises(ProposalError):
            validate_model_revision("PIN_BEFORE_RUN")
        with self.assertRaises(ProposalError):
            validate_model_revision("not-a-sha!")
        self.assertEqual(validate_model_revision("DEADBEEF"), "deadbeef")

    def test_prompt_map_rejects_non_ontology_id(self):
        with self.assertRaises(ProposalError):
            build_prompt_map("weird plant=99")
        parsed = build_prompt_map("rice=1;weed=2")
        self.assertEqual(parsed, {"rice": 1, "weed": 2})


if __name__ == "__main__":
    unittest.main()
