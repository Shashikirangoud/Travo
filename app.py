import json, os, requests
import streamlit as st
import streamlit.components.v1 as components
from fpdf import FPDF

BASE = os.path.dirname(os.path.abspath(__file__))
def read(rel):
    """Load a front-end file (HTML/CSS) that lives next to app.py."""
    with open(os.path.join(BASE, rel), encoding="utf-8") as f:
        return f.read()

st.set_page_config(page_title="Travo – AI Travel Planner", page_icon="🌍", layout="wide")

MODES = {
    "train": ("🚆", "Train", "Train: nearest railway station to nearest railway station. Real train names/numbers, typical departure times, classes, fare range, availability tips."),
    "pbus": ("🚌", "Public bus", "Public/government bus: nearest bus stand to bus stand, operator/service names, frequency, fares."),
    "prbus": ("🚍", "Private bus", "Private AC/sleeper bus: operators, boarding points, typical times, fares."),
    "flight": ("✈️", "Flight", "Flight: nearest airports, airlines, typical schedule, duration, fare range, plus airport-to-city transfers at both ends."),
    "bike": ("🏍️", "Own bike", "Own bike ride: best road, fuel/rest breaks, riding time."),
    "car": ("🚗", "Own car", "Own car drive: best road, tolls, rest breaks, driving time."),
}

# ---------- secrets ----------
def secret(name, default=None):
    # 1) Streamlit secrets (cwd/.streamlit or ~/.streamlit, or Cloud "Secrets")
    try:
        v = st.secrets[name]
        if v: return str(v).strip().strip('"').strip("'")
    except Exception:
        pass
    # 2) environment variable
    v = os.environ.get(name)
    if v: return v.strip().strip('"').strip("'")
    # 3) secrets file next to app.py, whatever folder Streamlit was started from
    try:
        import re
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".streamlit", "secrets.toml")
        m = re.search(r'^\s*' + name + r'\s*=\s*["\']?([^"\'\r\n]+)["\']?', open(path, encoding="utf-8-sig").read(), re.M)
        if m: return m.group(1).strip()
    except Exception:
        pass
    return default

def groq(messages, json_mode=False):
    key = secret("GROQ_API_KEY")
    if not key:
        raise RuntimeError("GROQ_API_KEY not found. Local: create .streamlit/secrets.toml (NOT .example) next to app.py containing GROQ_API_KEY = \"gsk_...\" and restart. Cloud: App > Settings > Secrets, then Reboot.")
    # Groq retires models often; try the configured one first, then current production models.
    models = []
    for m in [secret("GROQ_MODEL"), "openai/gpt-oss-120b", "openai/gpt-oss-20b"]:
        if m and m not in models: models.append(m)
    last = "no model available"
    for model in models:
        body = {"model": model, "messages": messages, "temperature": 0.4,
                "max_tokens": 6000 if json_mode else 1500}
        if model.startswith("openai/gpt-oss"):
            body["reasoning_effort"] = "low"
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        r = requests.post("https://api.groq.com/openai/v1/chat/completions",
                          headers={"Authorization": f"Bearer {key}"}, json=body, timeout=120)
        if r.status_code == 200:
            return r.json()["choices"][0]["message"]["content"] or ""
        try: msg = r.json()["error"]["message"]
        except Exception: msg = r.text[:200]
        last = f"Groq error {r.status_code}: {msg}"
        if r.status_code == 429:
            last = "Groq's free-tier rate limit was reached. Please wait about a minute and press Plan again."
            break
        if r.status_code in (400, 404) and "model" in msg.lower():
            continue  # model retired / unsupported -> try the next one
        break
    raise RuntimeError(last)

# ---------- styling ----------
st.markdown(f"<style>{read('static/style.css')}</style>", unsafe_allow_html=True)

# ---------- rotating Earth (hero banner, rendered in its own safe iframe) ----------
GLOBE_HTML = read("templates/globe.html")
plan = st.session_state.get("plan")
arc = None
if plan:
    arc = {"startLat": plan["from"]["lat"], "startLng": plan["from"]["lon"], "endLat": plan["to"]["lat"], "endLng": plan["to"]["lon"]}

# ---------- header + inputs ----------
st.markdown('<div class="gt-bar"><span>🌍 Travo</span></div>', unsafe_allow_html=True)
with st.container(key="globe"):
    components.html(GLOBE_HTML.replace("__ARC__", json.dumps(arc)), height=1)
with st.container(key="panel"):
  with st.form("trip", clear_on_submit=False):   # Enter key submits; no "press Enter to apply" hint
    c1, c2 = st.columns(2)
    src = c1.text_input("From", placeholder="From (city)", label_visibility="collapsed")
    dst = c2.text_input("To", placeholder="To (city)", label_visibility="collapsed")
    d1, d2 = st.columns([1, 2.5], vertical_alignment="bottom")
    days = d1.number_input("Days (0 = flexible)", min_value=0, max_value=30, value=0)
    inc = d2.checkbox("Include travel time in these days", value=False)
    go = st.form_submit_button("✨ Plan", type="primary", use_container_width=True)
    st.pills("Transport", options=list(MODES), format_func=lambda k: f"{MODES[k][0]} {MODES[k][1]}",
             selection_mode="single", default="train", key="mode", label_visibility="collapsed")

mode = st.session_state.get("mode") or "train"

def build_prompt(f, t, mode, nd, inc):
    if nd:
        rule = (f"TOTAL TRIP = exactly {nd} days INCLUDING travel. Count the outbound and return journeys inside these {nd} days "
                "(a long or overnight trip uses most of day 1 and the last day). Only plan sightseeing in the time that remains, "
                "and choose only as many places as realistically fit.") if inc else \
               f"Traveller has exactly {nd} full days AT the destination; travel time is extra and NOT counted. Fit sightseeing in {nd} days."
        itin = f'"itinerary":[{{"day":1,"title":"","covers":"place names/travel","plan":"short plan with rough timings"}}] (ONE entry for each of the {nd} days, with travel legs on the right days if included),'
    else:
        rule = "No fixed number of days given."
        itin = '"itinerary":[{"days":1,"covers":"places 1-3","plan":"short day-wise plan"}] (options for 1,2,3,4 and 5 days),'
    return f'''You are a travel API. Plan a trip from "{f}" to "{t}". Reply with ONE valid JSON object only.
Transport mode: {MODES[mode][2]}
Days: {rule}
Shape (keep strings short):
{{"from":{{"name":"","lat":0,"lon":0}},"to":{{"name":"","lat":0,"lon":0}},"distanceKm":0,"duration":"","summary":"",
"legs":[{{"title":"","detail":"specific station/stand/airport names, service name/number, typical times","duration":"","fare":"","availability":""}}],
"route":[{{"lat":0,"lon":0}}] (8-14 waypoints following the real rail/road path, start to end; for flight just start,end),
"stops":[{{"name":"","lat":0,"lon":0,"why":"","detourMin":0}}] (ONLY for own bike/car: 3-5 worthwhile stops directly on the route with detour under 15 min; else []),
"places":[{{"name":"","lat":0,"lon":0,"why":"","timeNeeded":""}}] (8 must-visit places at the destination, by priority),
{itin}
"stays":[{{"tier":"Budget|Standard|Comfort|Premium|Luxury","name":"","area":"","normal":"price per night","peak":"price per night"}}] (5 real hotels near the destination's main areas, low to high, local currency e.g. ₹ for India)}}
Use accurate coordinates. Be realistic; if unsure about availability say "check live".'''

def num(v):
    try: return float(v)
    except (TypeError, ValueError): return None

def clean_points(items):
    """Keep only entries with valid coordinates so the map can never crash."""
    out = []
    for x in items or []:
        if not isinstance(x, dict): continue
        la, lo = num(x.get("lat")), num(x.get("lon"))
        if la is None or lo is None or not (-90 <= la <= 90 and -180 <= lo <= 180): continue
        x["lat"], x["lon"] = la, lo
        out.append(x)
    return out

def normalize(p):
    for k in ("from", "to"):
        pt = p.get(k)
        if not isinstance(pt, dict) or clean_points([pt]) == []:
            raise ValueError(f"The AI did not return a valid '{k}' location. Try a more specific city name (e.g. 'Hyderabad, India').")
    p["route"] = clean_points(p.get("route"))
    if len(p["route"]) < 2: p["route"] = [p["from"], p["to"]]
    p["places"], p["stops"] = clean_points(p.get("places")), clean_points(p.get("stops"))
    for k in ("legs", "itinerary", "stays"):
        p[k] = [x for x in (p.get(k) or []) if isinstance(x, dict)]
    return p

def parse_json(raw):
    raw = raw.strip().replace("```json", "").replace("```", "")
    return json.loads(raw[raw.index("{"): raw.rindex("}") + 1])

@st.cache_data(ttl=3600, show_spinner=False)  # same trip within 1 hour = instant, no API call
def generate_plan(f, t, mode, nd, inc):
    last = None
    for _ in range(2):  # one automatic retry if the AI returns broken JSON
        raw = groq([{"role": "user", "content": build_prompt(f, t, mode, nd, inc)}], True)
        try:
            return normalize(parse_json(raw))
        except (ValueError, KeyError) as e:  # JSONDecodeError is a ValueError
            last = e
    raise RuntimeError(f"The AI returned an unusable plan twice ({last}). Please press Plan again.")

if go:
    if not src.strip() or not dst.strip():
        st.warning("Please enter both From and To.")
    elif src.strip().lower() == dst.strip().lower():
        st.warning("From and To are the same place. Pick two different cities.")
    else:
        with st.spinner("🌐 Planning your trip… (10–30 s)"):
            try:
                p = dict(generate_plan(src.strip(), dst.strip(), mode, int(days), inc))
                p.update(_mode=mode, _days=int(days), _inc=inc)
                st.session_state.plan, st.session_state.chat = p, []
                st.rerun()
            except Exception as e:
                st.error(f"Could not generate the plan: {e}")

# ---------- map ----------
MAP_HTML = read("templates/map.html")

def day_label(i):
    if i.get("day"):
        return f"Day {i['day']}" + (f" – {i['title']}" if i.get("title") else "")
    n = i.get("days", 1)
    return f"{n} day{'s' if n != 1 else ''}"

def make_pdf(p):
    def clean(s):
        return str(s if s is not None else "").replace("₹", "Rs. ").encode("ascii", "ignore").decode()
    pdf = FPDF(); pdf.set_auto_page_break(True, 15); pdf.add_page()
    def line(t, size=10, bold=False, color=(30, 30, 30)):
        pdf.set_font("Helvetica", "B" if bold else "", size); pdf.set_text_color(*color)
        pdf.multi_cell(0, size * 0.5 + 1.5, clean(t), new_x="LMARGIN", new_y="NEXT")
    def head(t):
        pdf.ln(3); line(t, 13, True, (20, 90, 170))
    m = MODES[p["_mode"]][1]
    line(f"Trip Plan: {p['from']['name']} to {p['to']['name']}", 18, True, (20, 60, 140))
    line(f"Mode: {m}  |  Distance: {p.get('distanceKm')} km  |  Duration: {p.get('duration')}"); line(p.get("summary", ""))
    head("Transport")
    for l in p.get("legs", []):
        line(l.get("title", ""), 10, True); line(f"{l.get('detail','')} | {l.get('duration','')} | {l.get('fare','')}"); line("Availability: " + str(l.get("availability", "")))
    if p.get("stops"):
        head("On-the-way stops")
        for s in p["stops"]: line(f"- {s['name']} (+{s.get('detourMin')} min): {s.get('why','')}")
    head("Must-visit places")
    for i, s in enumerate(p.get("places", []), 1): line(f"{i}. {s['name']} [{s.get('timeNeeded','')}] - {s.get('why','')}")
    head("Stay plan" + (f" ({p['_days']} days, travel {'included' if p['_inc'] else 'not included'})" if p.get("_days") else ""))
    for i in p.get("itinerary", []): line(f"{day_label(i)}: {i.get('covers','')} - {i.get('plan','')}")
    head("Hotels (low to high)")
    for s in p.get("stays", []): line(f"{s['tier']} - {s['name']} ({s.get('area','')}) | Normal: {s.get('normal','')} | Peak: {s.get('peak','')}")
    pdf.ln(6); line("Estimates only - confirm schedules, fares and availability before booking.", 9, False, (110, 110, 110))
    line("Enjoy your trip!", 16, True, (20, 140, 90))
    return bytes(pdf.output())

# ---------- results ----------
if plan:
    pm = plan["_mode"]; icon, label, _ = MODES[pm]
    st.subheader(f"{icon} {label} · {plan.get('distanceKm','?')} km · {plan.get('duration','')}")
    st.caption(plan.get("summary", ""))
    with st.container(border=True):
        st.markdown("**🗺️ Route map** – drag to pan, scroll/pinch to zoom · 🔴 must-visit · 🟢 on-the-way stop")
        data = json.dumps({"plan": plan, "mode": pm, "icon": icon, "label": label}).replace("</", "<\\/")
        components.html(MAP_HTML.replace("__DATA__", data), height=520)
    a, b = st.columns(2)
    with a.container(border=True):
        st.markdown(f"**{icon} Transport plan**")
        for l in plan.get("legs", []):
            st.markdown(f"**{l.get('title','')}**  \n{l.get('detail','')}  \n⏱ {l.get('duration','')} · 💰 {l.get('fare','')}  \n_{l.get('availability','')}_")
        if plan.get("stops"):
            st.markdown("**🟢 On-the-way stops (no real delay)**")
            for s in plan["stops"]: st.markdown(f"- **{s['name']}** (+{s.get('detourMin')} min) – {s.get('why','')}")
    with b.container(border=True):
        st.markdown("**📅 Stay plan**")
        for i in plan.get("itinerary", []): st.markdown(f"**{day_label(i)}** – covers {i.get('covers','')}  \n_{i.get('plan','')}_")
    c, d = st.columns(2)
    with c.container(border=True):
        st.markdown("**📍 Must-visit places**")
        for i, s in enumerate(plan.get("places", []), 1): st.markdown(f"**{i}. {s['name']}** · {s.get('timeNeeded','')}  \n_{s.get('why','')}_")
    with d.container(border=True):
        st.markdown("**🏨 Stays (low → high)**")
        for s in plan.get("stays", []):
            st.markdown(f"**{s['name']}** · `{s['tier']}`  \n{s.get('area','')}  \n🟢 Normal: {s.get('normal','')} · 🔴 Peak: {s.get('peak','')}")
    with st.container(border=True):
        st.download_button("⬇️ Download trip as PDF", make_pdf(plan), file_name="trip-plan.pdf", mime="application/pdf", use_container_width=True)
        st.markdown("<p style='text-align:center;color:#9fb2d8'>Enjoy your trip! 🧳✈️</p>", unsafe_allow_html=True)

    # ---------- chat ----------
    st.subheader("💬 Ask your travel buddy")
    for m in st.session_state.get("chat", []):
        with st.chat_message(m["role"]): st.write(m["content"])
    q = st.chat_input("Ask a follow-up (food, safety, best season, budget…)")
    if q:
        st.session_state.chat.append({"role": "user", "content": q})
        ctx = {"role": "system", "content": "You are a friendly, concise travel assistant. Trip plan: " + json.dumps(plan)[:6000]}
        try:
            ans = groq([ctx] + st.session_state.chat[-10:])
        except Exception as e:
            ans = f"Sorry: {e}"
        st.session_state.chat.append({"role": "assistant", "content": ans}); st.rerun()
else:
    st.info("Enter From / To, pick a transport mode and press **Plan**.")
st.caption("AI-generated estimates – confirm timings, fares and availability before booking. Map © OpenStreetMap contributors.")
