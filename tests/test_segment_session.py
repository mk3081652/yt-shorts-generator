"""
test_segment_session.py - Unit tests for StoryboardSession operations & REST endpoints.
Phase 3 Segment Studio tests.
"""

import os
import unittest
from fastapi.testclient import TestClient

from app import app
from engine.visual_director.segment_session import (
    Segment,
    StoryboardSession,
    create_session,
    split_segment,
    merge_segment,
    add_segment,
    delete_segment,
    edit_segment_text,
    replan_dirty_segments,
    load_session
)


class TestSegmentSessionUnit(unittest.TestCase):

    def setUp(self):
        self.script = (
            "The mystery of deep ocean exploration began decades ago. "
            "Scientists discovered strange glowing creatures in the abyss. "
            "Pressure reaches thousands of pounds per square inch."
        )

    def test_create_session_automatic(self):
        session = create_session(self.script, manual_delimiter=False)
        self.assertIsNotNone(session.session_id)
        self.assertGreater(len(session.segments), 0)
        self.assertGreater(session.total_duration, 0)
        # Check disk persistence
        loaded = load_session(session.session_id)
        self.assertIsNotNone(loaded)
        self.assertEqual(len(loaded.segments), len(session.segments))

    def test_create_session_manual_delimiter(self):
        delimited_script = "First part of the video ||| Second part of the video ||| Third part of the video"
        session = create_session(delimited_script, manual_delimiter=True)
        self.assertEqual(len(session.segments), 3)
        self.assertEqual(session.segments[0].text, "First part of the video")
        self.assertEqual(session.segments[1].text, "Second part of the video")
        self.assertEqual(session.segments[2].text, "Third part of the video")

    def test_split_segment(self):
        session = create_session("One two three four five six seven eight nine ten", manual_delimiter=False)
        target_id = session.segments[0].segment_id
        orig_count = len(session.segments)

        # Valid split
        updated, err, code = split_segment(session.session_id, target_id, split_at_word_index=4)
        self.assertIsNone(err)
        self.assertEqual(code, 200)
        self.assertEqual(len(updated.segments), orig_count + 1)
        self.assertTrue(updated.segments[0].dirty)
        self.assertTrue(updated.segments[1].dirty)

        # Invalid split index (out of bounds)
        _, err_oob, code_oob = split_segment(session.session_id, updated.segments[0].segment_id, split_at_word_index=99)
        self.assertIsNotNone(err_oob)
        self.assertEqual(code_oob, 400)

        # Split rejected if custom override
        updated.segments[0].is_custom = True
        from engine.visual_director.segment_session import save_session
        save_session(updated)
        _, err_cust, code_cust = split_segment(session.session_id, updated.segments[0].segment_id, split_at_word_index=2)
        self.assertIsNotNone(err_cust)
        self.assertEqual(code_cust, 409)

    def test_merge_segment(self):
        delimited = "Part one narration here ||| Part two narration follows ||| Part three concluding"
        session = create_session(delimited, manual_delimiter=True)
        seg0_id = session.segments[0].segment_id
        seg1_id = session.segments[1].segment_id

        # Merge next
        updated, err, code = merge_segment(session.session_id, seg0_id, direction="next")
        self.assertIsNone(err)
        self.assertEqual(code, 200)
        self.assertEqual(len(updated.segments), 2)
        self.assertIn("Part one narration here Part two narration follows", updated.segments[0].text)
        self.assertTrue(updated.segments[0].dirty)

        # Merge next on last segment should fail
        last_id = updated.segments[-1].segment_id
        _, err_last, code_last = merge_segment(session.session_id, last_id, direction="next")
        self.assertIsNotNone(err_last)
        self.assertEqual(code_last, 400)

    def test_add_segment(self):
        session = create_session("Initial sentence for testing", manual_delimiter=False)
        target_id = session.segments[0].segment_id
        orig_dur = session.total_duration

        updated, err, code = add_segment(session.session_id, target_id, "Inserted subsequent narration words")
        self.assertIsNone(err)
        self.assertEqual(code, 200)
        self.assertEqual(len(updated.segments), 2)
        self.assertGreater(updated.total_duration, orig_dur)
        self.assertTrue(updated.segments[1].dirty)

        # Empty text rejected
        _, err_empty, code_empty = add_segment(session.session_id, target_id, "   ")
        self.assertIsNotNone(err_empty)
        self.assertEqual(code_empty, 400)

    def test_delete_segment(self):
        delimited = "First sentence to keep ||| Second sentence to delete"
        session = create_session(delimited, manual_delimiter=True)
        self.assertEqual(len(session.segments), 2)
        del_id = session.segments[1].segment_id
        orig_dur = session.total_duration

        updated, err, code = delete_segment(session.session_id, del_id)
        self.assertIsNone(err)
        self.assertEqual(code, 200)
        self.assertEqual(len(updated.segments), 1)
        self.assertLess(updated.total_duration, orig_dur)

        # Cannot delete the only remaining segment
        _, err_only, code_only = delete_segment(session.session_id, updated.segments[0].segment_id)
        self.assertIsNotNone(err_only)
        self.assertEqual(code_only, 400)

    def test_edit_segment_text(self):
        session = create_session("Original test words for segment", manual_delimiter=False)
        target = session.segments[0]

        # No change (same words, different whitespace)
        updated, err, code = edit_segment_text(session.session_id, target.segment_id, "  Original   test words for segment  ")
        self.assertIsNone(err)
        self.assertFalse(updated.segments[0].dirty)

        # Changed words -> dirty=True and duration recalculated
        updated2, err2, code2 = edit_segment_text(session.session_id, target.segment_id, "Completely new words replacing everything")
        self.assertIsNone(err2)
        self.assertTrue(updated2.segments[0].dirty)


class TestSegmentSessionAPI(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)

    def test_api_crud_workflow(self):
        # 1. Create
        res = self.client.post("/api/segments/create", json={
            "script": "The ocean depths hold countless secrets. Ancient creatures lurk unseen.",
            "manual_delimiter": False
        })
        self.assertEqual(res.status_code, 200)
        data = res.json()
        session_id = data["session_id"]
        self.assertGreater(len(data["segments"]), 0)

        # 2. Get session
        get_res = self.client.get(f"/api/segments/{session_id}")
        self.assertEqual(get_res.status_code, 200)
        self.assertEqual(get_res.json()["session_id"], session_id)

        # 3. Edit text
        seg_id = data["segments"][0]["segment_id"]
        edit_res = self.client.post(f"/api/segments/{session_id}/edit_text", json={
            "segment_id": seg_id,
            "new_text": "The ocean depths hold immense mysterious secrets that shock scientists."
        })
        self.assertEqual(edit_res.status_code, 200)
        self.assertTrue(edit_res.json()["segments"][0]["dirty"])

        # 4. Add segment
        add_res = self.client.post(f"/api/segments/{session_id}/add", json={
            "after_segment_id": seg_id,
            "text": "Submarines venture deeper into the midnight zone."
        })
        self.assertEqual(add_res.status_code, 200)

        # 5. Split segment
        added_seg_id = add_res.json()["segments"][1]["segment_id"]
        split_res = self.client.post(f"/api/segments/{session_id}/split", json={
            "segment_id": added_seg_id,
            "split_at_word_index": 3
        })
        self.assertEqual(split_res.status_code, 200)

        # 6. Replan dirty
        replan_res = self.client.post(f"/api/segments/{session_id}/replan_dirty")
        self.assertEqual(replan_res.status_code, 200)
        # Verify dirty flags are cleared
        dirty_remaining = [s for s in replan_res.json()["segments"] if s["dirty"]]
        self.assertEqual(len(dirty_remaining), 0)


if __name__ == "__main__":
    unittest.main()
