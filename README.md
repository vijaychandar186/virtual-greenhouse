# Virtual-Greenhouse

## Quickstart (SQLite, no external DB)
1. Install dependencies:
   `pip install -r requirements.txt`
2. Run the app:
   `python -m src.app`

You can also use the root launcher:
`./start.sh`
3. Open `http://127.0.0.1:5000`

SQLite is the default and only DB. It will create `instance/virtual_greenhouse.db` on first run.

## Environment
Copy `.env.example` to `.env` and update values as needed. `config.py` reads all settings.

The app expects these tables:
- `users(userid, username, password, email)`
- `greenhouses(id, location, greenhouse_name, sensors, length, width, userid)`
- `sensor_status(id, temperature, humidity, light, co2)`

## Notifications (optional)
`notify.py` sends Twilio alerts based on latest sensor readings.

Required env vars:
```
export TWILIO_ACCOUNT_SID=...
export TWILIO_AUTH_TOKEN=...
export TWILIO_NUMBER=...
export TWILIO_RECIPIENT=...
```

Run with:
`python -m src.notify`

## Testing
Run the test suite:
`./.venv/bin/python -m unittest discover -s test -p "test_*.py"`