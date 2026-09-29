import unittest
from engine.beats import create_story_beats, extract_explicit_user_scenes
from engine.project import create_project


class TestExplicitUserScenes(unittest.TestCase):

    def test_paragraph_space_split_two_scenes(self):
        """Scripts separated by an empty line / space should split into exactly the intended scenes without merging."""
        script = (
            "Three men vanished from a lighthouse... and no one ever found out why.\n\n"
            "December 1900. A supply ship reaches the island. Nobody comes to greet it."
        )
        beats = create_story_beats(script, total_duration=20.0)
        self.assertEqual(len(beats), 2)
        self.assertEqual(beats[0][0], "Three men vanished from a lighthouse... and no one ever found out why.")
        self.assertEqual(beats[1][0], "December 1900. A supply ship reaches the island. Nobody comes to greet it.")
        self.assertAlmostEqual(sum(d for _, d in beats), 20.0, places=1)

    def test_explicit_scene_markers_ten_scenes(self):
        """Scripts with Scene 1: through Scene 10: split into exactly 10 scenes with clean narration."""
        script = """Scene 1: On March 4, 1991, a passenger plane disappeared from radar over the Atlantic Ocean.

Scene 2: There was no distress call, no explosion, and no warning.

Scene 3: The pilots had been flying normally when, suddenly, the aircraft stopped responding.

Scene 4: Air traffic controllers repeatedly tried to contact the crew, but the cockpit remained completely silent.

Scene 5: Rescue aircraft were sent to the last known location, searching the ocean for wreckage.

Scene 6: But they found nothing—not a single piece of debris.

Scene 7: Investigators eventually discovered something even stranger: the plane had vanished from radar at the exact moment its transponder signal disappeared.

Scene 8: With no confirmed crash site and no survivors, theories began spreading about what could have happened.

Scene 9: Some believed the aircraft suffered a catastrophic failure, while others suspected something far more unusual.

Scene 10: To this day, the disappearance remains one of aviation's most haunting unsolved mysteries."""

        beats = create_story_beats(script, total_duration=60.0)
        self.assertEqual(len(beats), 10)
        self.assertEqual(beats[0][0], "On March 4, 1991, a passenger plane disappeared from radar over the Atlantic Ocean.")
        self.assertEqual(beats[1][0], "There was no distress call, no explosion, and no warning.")
        self.assertEqual(beats[6][0], "Investigators eventually discovered something even stranger: the plane had vanished from radar at the exact moment its transponder signal disappeared.")
        self.assertEqual(beats[9][0], "To this day, the disappearance remains one of aviation's most haunting unsolved mysteries.")

    def test_line_by_line_scene_splitting(self):
        """Each non-empty line without blank lines is recognized as an explicit scene if lines are sentences."""
        script = (
            "On March 4, 1991, a passenger plane disappeared from radar over the Atlantic Ocean.\n"
            "There was no distress call, no explosion, and no warning.\n"
            "The pilots had been flying normally when, suddenly, the aircraft stopped responding."
        )
        beats = create_story_beats(script, total_duration=18.0)
        self.assertEqual(len(beats), 3)
        self.assertEqual(beats[0][0], "On March 4, 1991, a passenger plane disappeared from radar over the Atlantic Ocean.")
        self.assertEqual(beats[1][0], "There was no distress call, no explosion, and no warning.")
        self.assertEqual(beats[2][0], "The pilots had been flying normally when, suddenly, the aircraft stopped responding.")

    def test_multi_line_scene_header(self):
        """Scene header on its own line followed by narration on next line."""
        script = """Scene 1:
A lone ship sailed through the dense fog.

Scene 2:
The fog horn sounded once, then went silent forever."""

        beats = create_story_beats(script, total_duration=15.0)
        self.assertEqual(len(beats), 2)
        self.assertEqual(beats[0][0], "A lone ship sailed through the dense fog.")
        self.assertEqual(beats[1][0], "The fog horn sounded once, then went silent forever.")

    def test_create_project_with_explicit_scenes(self):
        """create_project generates exact scenes and clean narration without Scene 1: in TTS script."""
        script = (
            "Scene 1: Three men vanished from a lighthouse... and no one ever found out why.\n\n"
            "Scene 2: December 1900. A supply ship reaches the island. Nobody comes to greet it."
        )
        project = create_project(script=script, start="manual")
        self.assertEqual(len(project.scenes), 2)
        self.assertEqual(project.scenes[0].text, "Three men vanished from a lighthouse... and no one ever found out why.")
        self.assertEqual(project.scenes[1].text, "December 1900. A supply ship reaches the island. Nobody comes to greet it.")
        self.assertNotIn("Scene 1:", project.script)
        self.assertNotIn("Scene 2:", project.script)
        self.assertIn("Three men vanished", project.script)
        self.assertIn("December 1900", project.script)


if __name__ == "__main__":
    unittest.main()
