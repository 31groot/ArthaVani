import unittest

from finance_agent.conversation import ConversationIdentity


class ConversationIdentityTests(unittest.TestCase):
    def test_thread_id_is_stable_and_namespaced(self):
        identity = ConversationIdentity("alice", "main")
        self.assertEqual(identity.thread_id, "user:alice:conversation:main")

    def test_different_users_are_isolated(self):
        alice = ConversationIdentity("alice", "main")
        bob = ConversationIdentity("bob", "main")
        self.assertNotEqual(alice.thread_id, bob.thread_id)

    def test_different_conversations_are_isolated(self):
        main = ConversationIdentity("alice", "main")
        research = ConversationIdentity("alice", "research")
        self.assertNotEqual(main.thread_id, research.thread_id)

    def test_blank_identifiers_are_rejected(self):
        with self.assertRaises(ValueError):
            ConversationIdentity("  ", "main")
        with self.assertRaises(ValueError):
            ConversationIdentity("alice", "  ")
