import unittest

from voice.stt.deepgram import DeepgramClient


class TranscriptMergeTests(unittest.TestCase):
    def test_segment_then_tail(self):
        self.assertEqual(
            DeepgramClient._merge_transcripts(
                "What is the profit",
                "and loss of my current portfolio?",
            ),
            "What is the profit and loss of my current portfolio?",
        )

    def test_cumulative_update_replaces_previous(self):
        self.assertEqual(
            DeepgramClient._merge_transcripts(
                "What is the profit",
                "What is the profit and loss?",
            ),
            "What is the profit and loss?",
        )

    def test_overlap_is_not_duplicated(self):
        self.assertEqual(
            DeepgramClient._merge_transcripts(
                "current portfolio",
                "portfolio value",
            ),
            "current portfolio value",
        )


if __name__ == "__main__":
    unittest.main()
