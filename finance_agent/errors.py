class FinanceAgentError(RuntimeError):
    pass


class PostgresPersistenceError(FinanceAgentError):
    pass


class LLMProviderError(FinanceAgentError):
    pass


class LLMRateLimitError(LLMProviderError):
    """Raised when the LLM provider rejects a request for exceeding a
    rate/usage limit (e.g. tokens-per-minute), after retries are exhausted.

    """

    pass