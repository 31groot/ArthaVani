class FinanceAgentError(RuntimeError):
    pass


class PostgresPersistenceError(FinanceAgentError):
    pass


class LLMProviderError(FinanceAgentError):
    pass
