from config.settings import settings

from dotenv import load_dotenv
from growwapi import GrowwAPI

load_dotenv()

api_key = settings.GROWW_API_KEY
api_secret = settings.GROWW_API_SECRET

print("Generating Groww access token...")

access_token = GrowwAPI.get_access_token(
    api_key=api_key,
    secret=api_secret,
)

print("Access token generated successfully.")

groww = GrowwAPI(access_token)

print("\nUser profile:")
print(groww.get_user_profile())

print("\nHoldings:")
print(groww.get_holdings_for_user())

print("\nPositions:")
print(groww.get_positions_for_user())