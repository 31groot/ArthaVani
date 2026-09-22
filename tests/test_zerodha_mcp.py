import unittest
from contextlib import asynccontextmanager
from mcp.types import Tool
from finance_agent.mcp.zerodha import READ_ONLY_TOOLS, ZerodhaMCPClient

class FakeSession:
    def __init__(self, *_): self.closed = 0; self.initialized = 0
    async def __aenter__(self): return self
    async def __aexit__(self, *_): self.closed += 1
    async def initialize(self): self.initialized += 1
    async def call_tool(self, name, arguments):
        class Result:
            isError = True
            content = []
        return Result()
    async def list_tools(self, **_):
        class Result: pass
        result = Result()
        result.nextCursor = None
        result.tools = [Tool(name='get_holdings', description='holdings', inputSchema={}), Tool(name='place_order', description='trade', inputSchema={})]
        return result

@asynccontextmanager
async def fake_transport(*_): yield (object(), object(), lambda: None)



class ManualFlowSession:
    def __init__(self, is_error=False):
        self.is_error = is_error
        self.calls = []
    async def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        class Result:
            isError = self.is_error
        return Result()

class ManualFlowClient:
    def __init__(self, profile_error=False):
        self.session = ManualFlowSession(profile_error)
        self.connected_session = None
        self.closed = False
    async def connect(self):
        self.connected_session = self.session
    async def list_tools(self):
        return [Tool(name='get_profile', description='profile', inputSchema={})]
    async def authenticate(self):
        return 'https://kite.trade/authorize?request=opaque'
    async def close(self):
        self.closed = True

class ZerodhaMCPTests(unittest.IsolatedAsyncioTestCase):
    async def test_manual_flow_uses_same_session_after_login(self):
        from tests.manual_zerodha_integration import run_manual_flow
        client = ManualFlowClient()
        output = []
        await run_manual_flow(client, input_fn=lambda _: '', print_fn=lambda *args: output.append(' '.join(str(arg) for arg in args)))
        self.assertIs(client.connected_session, client.session)
        self.assertEqual([name for name, _ in client.session.calls], ['get_profile'])
        self.assertIn('MCP connection successful.', output)
        self.assertIn('Login URL generated.', output)
        self.assertIn('Authenticated get_profile succeeded.', output)

    async def test_manual_flow_reports_profile_failure_after_same_session(self):
        from tests.manual_zerodha_integration import run_manual_flow
        client = ManualFlowClient(profile_error=True)
        output = []
        await run_manual_flow(client, input_fn=lambda _: '', print_fn=lambda *args: output.append(' '.join(str(arg) for arg in args)))
        self.assertIs(client.connected_session, client.session)
        self.assertIn('Authenticated get_profile failed.', output)

    async def test_lifecycle_and_read_only_discovery(self):
        client = ZerodhaMCPClient(url='https://example.test/mcp', transport_factory=fake_transport, session_factory=FakeSession, start_server=False)
        await client.connect()
        self.assertEqual([tool.name for tool in await client.list_tools()], ['get_holdings'])
        self.assertEqual([tool.name for tool in await client.discover_tools()], ['zerodha_get_holdings'])
        await client.close(); await client.close()
    async def test_unauthenticated_state_is_reported_without_exposing_login_tool(self):
        client = ZerodhaMCPClient(url='https://example.test/mcp', transport_factory=fake_transport, session_factory=FakeSession, start_server=False)
        await client.connect()
        self.assertFalse(await client.authenticate())
        self.assertNotIn('login', {tool.name for tool in await client.list_tools()})
        await client.close()

    def test_successful_login_url_extraction(self):
        class Block: text = "Authorize at https://kite.trade/login?request=opaque"
        class Result: isError = False; content = [Block()]
        self.assertEqual(ZerodhaMCPClient.extract_login_url(Result()), "https://kite.trade/login?request=opaque")

    def test_missing_or_invalid_login_response(self):
        class Error: isError = True; content = []
        class Empty: isError = False; content = [type("Block", (), {"text": "Login unavailable"})()]
        self.assertIsNone(ZerodhaMCPClient.extract_login_url(Error()))
        self.assertIsNone(ZerodhaMCPClient.extract_login_url(Empty()))

    async def test_authenticated_profile_success_and_failure(self):
        class SuccessSession(FakeSession):
            async def call_tool(self, name, arguments):
                class Result: isError = False; content = []
                return Result()
        class FailureSession(FakeSession):
            async def call_tool(self, name, arguments):
                class Result: isError = True; content = []
                return Result()
        for session_factory, expected in ((SuccessSession, False), (FailureSession, True)):
            client = ZerodhaMCPClient(url='https://example.test/mcp', transport_factory=fake_transport, session_factory=session_factory, start_server=False)
            await client.connect()
            result = await client.session.call_tool('get_profile', {})
            self.assertEqual(result.isError, expected)
            await client.close()

    def test_allowlist_excludes_trading_and_gtt_mutations(self):
        forbidden = {'place_order', 'modify_order', 'cancel_order', 'place_gtt_order', 'modify_gtt_order', 'delete_gtt_order', 'login'}
        self.assertFalse(READ_ONLY_TOOLS & forbidden)

if __name__ == '__main__': unittest.main()
