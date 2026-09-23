1. Copy the new files into the repository:
   - `api/`
   - `finance_agent/user_context.py`
   - `finance_agent/persistence.py`
   - `api/groww.py`
   - `finance_agent/providers/groww.py`
   - `finance_agent/providers/watchlist.py`

2. In `config/settings.py`, add the fields shown in
   `config/api_settings_patch.txt`.

3. Append the dependencies in `requirements-api.txt` to `requirements.txt`.

4. Merge `.env.api.example` into your `.env.example`.

5. Set the two new secrets in `.env`:
   - `API_JWT_SECRET_KEY`
   - `GROWW_CREDENTIALS_ENCRYPTION_KEY`

6. Start:
   `uvicorn api.main:app --reload --host 0.0.0.0 --port 8000`
