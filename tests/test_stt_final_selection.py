import unittest

from voice.stt.deepgram import DeepgramClient


class STTFinalSelectionTests(unittest.TestCase):
    def test_newer_longer_interim_wins(self):
        result = DeepgramClient._select_final_transcript(
            "What is the current value of my",
            "What is the current value of my portfolio?",
        )
        self.assertEqual(
            result,
            "What is the current value of my portfolio?",
        )

    def test_unrelated_interim_is_not_appended(self):
        result = DeepgramClient._select_final_transcript(
            "What is the current value of my code?",
            "What is the current value of",
        )
        self.assertEqual(
            result,
            "What is the current value of my code?",
        )

    def test_missing_final_uses_interim(self):
        result = DeepgramClient._select_final_transcript(
            "",
            "What is the current price of Infosys?",
        )
        self.assertEqual(
            result,
            "What is the current price of Infosys?",
        )

    def test_missing_interim_uses_final(self):
        result = DeepgramClient._select_final_transcript(
            "What is my portfolio value?",
            "",
        )
        self.assertEqual(
            result,
            "What is my portfolio value?",
        )


if __name__ == "__main__":
    unittest.main()
