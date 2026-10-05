import unittest

from finance_agent.conversation import ConversationIdentity


class ConversationIdentityTests(unittest.TestCase):
    def test_thread_id_matches_user_id(self):
        identity = ConversationIdentity(user_id="alice")

        self.assertEqual(identity.user_id, "alice")
        self.assertEqual(identity.thread_id, "alice")

    def test_different_users_are_isolated(self):
        alice = ConversationIdentity(user_id="alice")
        bob = ConversationIdentity(user_id="bob")

        self.assertNotEqual(alice.thread_id, bob.thread_id)

    def test_same_user_produces_stable_thread_id(self):
        first = ConversationIdentity(user_id="alice")
        second = ConversationIdentity(user_id="alice")

        self.assertEqual(first.thread_id, second.thread_id)
        self.assertEqual(first.thread_id, "alice")