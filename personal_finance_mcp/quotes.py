from datetime import datetime, timezone
from typing import Any

import yfinance as yf


class QuoteLookupError(RuntimeError):
    """
    Custom exception used when Yahoo Finance fails to provide
    a stock quote.
    """


class YahooFinanceQuoteProvider:
    """
    Retrieves stock market quotes from Yahoo Finance.
    """

    def get_quote(
        self,
        ticker: str,
    ) -> dict[str, object]:

        # First normalize and validate the ticker symbol.
        
        symbol = self._normalize_ticker(ticker)

        try:

            # Create a yfinance Ticker object for the requested symbol.
    
            instrument = yf.Ticker(symbol)

            # Request the last five days of daily price history.
            #
            # period="5d"
            #     → ask for approximately the last five trading days
            #
            # interval="1d"
            #     → one row per trading day
            #
            # auto_adjust=False
            #     → keep the historical prices unadjusted
            #
            # raise_errors=True
            #     → ask yfinance to raise an error when the request fails
            history = instrument.history(
                period="5d",
                interval="1d",
                auto_adjust=False,
                raise_errors=True,
            )

            # Make sure Yahoo actually returned usable data.

            if (
                history is None
                or history.empty
                or "Close" not in history
            ):

                raise ValueError(
                    f"No Yahoo Finance price data is available for '{symbol}'."
                )

            # Extract the closing prices and remove missing values.
    
            closes = history["Close"].dropna()

            # It is possible that the Close column existed
            # but contained no usable values.
            if closes.empty:

                raise ValueError(
                    f"No usable Yahoo Finance close price is available for '{symbol}'."
                )

            # Get the most recent closing price.
            #
            # iloc[-1] means:
            #
            #     "take the last value in the series"
            #
            # float() converts the returned numerical value
            # into a normal Python float.
            latest_price = float(
                closes.iloc[-1]
            )

            # Get the previous closing price.
            #
            # iloc[-2] means:
            #
            #     "take the second-to-last value"
            #
            # If only one closing price exists, we use
            # latest_price as the previous close.

            previous_close = (
                float(closes.iloc[-2])
                if len(closes) > 1
                else latest_price
            )

            # Ask Yahoo Finance for additional information
            # about the instrument's trading history.

            metadata = (
                instrument.get_history_metadata()
                or {}
            )

            # Ask Yahoo Finance for general company information.
  
            # We use this mainly to get the company name and currency.
            info = (
                instrument.get_info()
                or {}
            )

        # Re-raise QuoteLookupError without changing it.

        except QuoteLookupError:
            raise

        # Re-raise ValueError directly.

        except ValueError:
            raise

        # Catch unexpected errors from yfinance/network/etc.

        except Exception as error:

            raise QuoteLookupError(
                self._provider_error(
                    symbol,
                    error,
                )
            ) from error

        # Try several possible places to obtain a human-readable
        # company name.
        
        company_name = (
            info.get("longName")
            or info.get("shortName")
            or metadata.get("longName")
            or metadata.get("shortName")
            or symbol
        )

        # Try to get the currency from company information first,
        # and history metadata second.
        currency = (
            info.get("currency")
            or metadata.get("currency")
        )

        if not currency:

            raise ValueError(
                f"Yahoo Finance did not return a currency for '{symbol}'."
            )

        # Determine the timestamp associated with the quote.
        timestamp = self._timestamp(
            metadata,
            closes.index[-1],
        )

        # Calculate the absolute price change.
        change = (
            latest_price
            - previous_close
        )

        # Build the final clean dictionary returned to
        # the rest of the application.
        return {
            # Normalized ticker symbol.
            "ticker": symbol,

            # Human-readable company name.
            "company_name": company_name,

            # Current/latest price rounded to four decimal places.
            "latest_price": round(
                latest_price,
                4,
            ),

            # Previous trading day's closing price.
            "previous_close": round(
                previous_close,
                4,
            ),

            # Currency code such as USD or INR.
            "currency": currency,

            # Absolute price change.
            "change": round(
                change,
                4,
            ),

            # If previous_close is zero, percentage change
            # is undefined, so return None instead.
            "change_percentage": (
                round(
                    (change / previous_close) * 100,
                    4,
                )
                if previous_close
                else None
            ),

            # Timestamp describing when the price data came from.
            "data_timestamp": timestamp,
        }

    @staticmethod
    def _normalize_ticker(
        ticker: str,
    ) -> str:

        # Make sure the caller actually supplied a string.        

        if not isinstance(ticker, str):

            raise ValueError(
                "ticker must be a string"
            )

        # Remove leading/trailing whitespace and convert to uppercase.
        
        symbol = ticker.strip().upper()

        # Validate the ticker symbol.
        if (
            not symbol
            or len(symbol) > 20
            or not all(
                character.isalnum()
                or character in ".-^="
                for character in symbol
            )
        ):

            raise ValueError(
                "ticker must be a valid Yahoo Finance symbol "
            )

        # Return the cleaned/validated ticker.
        return symbol

    @staticmethod
    def _timestamp(
        metadata: dict[str, Any],
        latest_index: Any,
    ) -> str:

        # Yahoo may provide the market timestamp as
        # Unix time in seconds.
        
        # We try to use that value first.
        market_time = metadata.get(
            "regularMarketTime"
        )

        # Check whether the timestamp is numeric.

        if isinstance(
            market_time,
            (int, float),
        ):

            # Convert Unix timestamp into a timezone-aware
            # UTC datetime.
            
            return datetime.fromtimestamp(
                market_time,
                tz=timezone.utc,
            ).isoformat()

        # If Yahoo did not provide regularMarketTime,
        # try the timestamp/index attached to the historical
        # price data.
        #
        # Pandas timestamps support isoformat().
        if hasattr(
            latest_index,
            "isoformat",
        ):

            return latest_index.isoformat()

        # Final fallback:
        #
        # Convert whatever timestamp/index we received
        # into a string.
        return str(latest_index)

    @staticmethod
    def _provider_error(
        symbol: str,
        error: Exception,
    ) -> str:

        # Convert the original exception into clean text.
        
        # strip() removes unwanted leading/trailing whitespace.
        message = str(error).strip()

        # Detect common Yahoo Finance rate-limit errors.

        
        if (
            "429" in message
            or "rate limit" in message.lower()
        ):

            return (
                f"Yahoo Finance rate limited quote requests for '{symbol}'. "
                "Please try again shortly."
            )

        # Detect ticker-not-found/delisted situations.
        #
        # Again, convert the low-level provider error into
        # a user-friendly application message.
        if (
            "not found" in message.lower()
            or "delisted" in message.lower()
        ):

            return (
                f"Yahoo Finance could not find ticker '{symbol}'."
            )

        # Generic fallback for any other provider failure.
        return (
            f"Yahoo Finance quote lookup failed for '{symbol}'. "
            "Please try again later."
        )