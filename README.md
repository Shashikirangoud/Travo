# Globe Trotter – AI Travel Planner (Streamlit + Groq)

## Files
app.py · requirements.txt · .streamlit/config.toml · .streamlit/secrets.toml.example · .gitignore

## 1. Get a Groq API key
https://console.groq.com → API Keys → Create key (starts with `gsk_`).

## 2. Run locally (optional)
    pip install -r requirements.txt
    cp .streamlit/secrets.toml.example .streamlit/secrets.toml   # then edit and paste your key
    streamlit run app.py

## 3. Push to GitHub
Create a new repo on github.com and upload every file (keep the folder `.streamlit/` and its `config.toml`).
NEVER upload `.streamlit/secrets.toml` (it is in .gitignore).

## 4. Deploy on Streamlit Community Cloud (free)
1. https://share.streamlit.io → sign in with GitHub → **Create app**.
2. Pick your repo, branch `main`, main file path `app.py`.
3. **Advanced settings → Secrets**, paste:  `GROQ_API_KEY = "gsk_..."`
4. Deploy. You get a public https link that works on phones and desktops.

## Notes
- Default model `llama-3.3-70b-versatile`; change with the `GROQ_MODEL` secret.
- Groq free tier has rate limits; if you see a 429 error wait a minute.
- Free Streamlit apps sleep after inactivity; first visit wakes them (~30 s).
- Map: OpenStreetMap tiles + public OSRM routing (demo use). Globe textures from unpkg.
- Fares/timings/availability are AI estimates, not live data.
