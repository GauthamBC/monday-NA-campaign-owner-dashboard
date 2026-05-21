# Monday Campaign Owner Dashboard

A Streamlit dashboard that pulls live campaign items from Monday.com and shows what each person has assigned across:

- Action Network
- VegasInsider
- Canada Sports Betting
- RotoGrinders

## Files

- `app.py` — main Streamlit app
- `requirements.txt` — packages for Streamlit Cloud
- `.streamlit/secrets.toml.example` — copy this into Streamlit secrets
- `.gitignore` — keeps real secrets out of GitHub

## Local setup

```bash
pip install -r requirements.txt
mkdir -p .streamlit
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
streamlit run app.py
```

Then add your real Monday token and board IDs to `.streamlit/secrets.toml`.

## Streamlit Cloud setup

1. Push this folder to GitHub.
2. Create a new Streamlit Cloud app from the repo.
3. Set `app.py` as the entry file.
4. Add the contents of `.streamlit/secrets.toml.example` to Streamlit Cloud secrets.
5. Replace the placeholders with your Monday API key and board IDs.
6. Run the app.
7. Open **Column Debug** at the bottom and copy the correct Monday column IDs into secrets.
