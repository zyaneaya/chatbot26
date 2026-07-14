import datetime
import hashlib
import re
from urllib.parse import quote

import pythoncom
import pyttsx3
import pywhatkit
import requests
import speech_recognition as sr
import streamlit as st

MAX_LOGIN_ATTEMPTS = 3
BASE_LOCKOUT_SECONDS = 30
MAX_LOCKOUT_SECONDS = 300
SESSION_TIMEOUT_MINUTES = 10

# ---------------------------------------------------------
# Synthèse vocale : l'assistant parle
# ---------------------------------------------------------
def parler(text):
    # Streamlit exécute le script dans un thread secondaire : pyttsx3 (SAPI5)
    # a besoin d'un appartement COM initialisé sur ce thread pour ne pas bloquer.
    pythoncom.CoInitialize()
    try:
        engine = pyttsx3.init()
        engine.say(text)
        engine.runAndWait()
        engine.stop()
    finally:
        pythoncom.CoUninitialize()


# ---------------------------------------------------------
# Reconnaissance vocale : l'assistant écoute le micro
# ---------------------------------------------------------
def ecouter():
    recognizer = sr.Recognizer()
    command = ""

    try:
        with sr.Microphone() as source:
            recognizer.adjust_for_ambient_noise(source, duration=1)
            voix = recognizer.listen(source, timeout=5, phrase_time_limit=8)
            command = recognizer.recognize_google(voix, language="fr-FR")
            command = command.lower()
    except sr.WaitTimeoutError:
        command = ""
    except sr.UnknownValueError:
        command = ""
    except OSError:
        raise
    except Exception:
        command = ""

    return command


# ---------------------------------------------------------
# Culture générale : recherche d'un sujet sur Wikipédia (FR)
# ---------------------------------------------------------
WIKI_TRIGGER = re.compile(
    r"^(?:qui (?:est|était|êtes)|c'est qui|qu'est[- ]ce que|c'est quoi|"
    r"défini[s]?|définition de|parle[- ]moi de|explique[- ]moi)\s+(.+)"
)
WIKI_ARTICLES = re.compile(r"^(le |la |les |l'|un |une |des )")


def rechercher_wikipedia(sujet):
    headers = {"User-Agent": "VirtualAssist/1.0 (assistant vocal pédagogique)"}

    try:
        recherche = requests.get(
            "https://fr.wikipedia.org/w/api.php",
            params={"action": "query", "list": "search", "srsearch": sujet, "format": "json", "srlimit": 1},
            headers=headers,
            timeout=5,
        )
        recherche.raise_for_status()
        resultats = recherche.json().get("query", {}).get("search", [])
        if not resultats:
            return None

        titre = resultats[0]["title"]
        resume_resp = requests.get(
            f"https://fr.wikipedia.org/api/rest_v1/page/summary/{titre.replace(' ', '_')}",
            headers=headers,
            timeout=5,
        )
        if resume_resp.status_code != 200:
            return None

        extrait = resume_resp.json().get("extract", "").strip()
        if not extrait:
            return None

        phrases = extrait.split(". ")
        resume = ". ".join(phrases[:2]).strip()
        if resume and not resume.endswith((".", "!", "?")):
            resume += "."
        return titre, resume
    except requests.RequestException:
        return None


# ---------------------------------------------------------
# Traitement de la commande : décide de la réponse à donner
# ---------------------------------------------------------
def traiter_commande(command):
    command = command.strip()

    if not command:
        return "Je n'ai rien entendu, pouvez-vous répéter ?", None

    if "joue" in command or "lance" in command:
        chanteur = re.sub(r"\b(joue|lance)\b", "", command).strip()
        if chanteur:
            return f"Je lance « {chanteur} » sur YouTube 🎵", ("youtube", chanteur)
        return "Que voulez-vous que je joue ?", None

    if "heure" in command:
        heure = datetime.datetime.now().strftime("%H:%M")
        return f"Il est actuellement {heure}.", None

    if any(mot in command for mot in ["bonjour", "salut", "coucou", "hello"]):
        return "Bonjour ! Comment puis-je vous aider aujourd'hui ?", None

    if any(mot in command for mot in ["merci"]):
        return "Avec plaisir !", None

    if any(mot in command for mot in ["date", "quel jour"]):
        date = datetime.datetime.now().strftime("%A %d %B %Y")
        return f"Nous sommes le {date}.", None

    wiki_match = WIKI_TRIGGER.match(command)
    if wiki_match:
        sujet = wiki_match.group(1).strip().strip("?!.").strip()
        sujet = WIKI_ARTICLES.sub("", sujet).strip()
        if not sujet:
            return "Sur quel sujet voulez-vous en savoir plus ?", None

        trouve = rechercher_wikipedia(sujet)
        if trouve is None:
            return f"Je n'ai pas trouvé d'information fiable sur « {sujet} ».", None

        titre, resume = trouve
        return f"D'après Wikipédia ({titre}) : {resume}", None

    return "Désolé, je n'ai pas compris votre demande.", None


def executer_action(action):
    if action is None:
        return
    kind, payload = action
    if kind == "youtube":
        pywhatkit.playonyt(payload)


# ---------------------------------------------------------
# Style de l'interface
# ---------------------------------------------------------
DOT_PATTERN_SVG = quote(
    "<svg xmlns='http://www.w3.org/2000/svg' width='28' height='28'>"
    "<circle cx='2' cy='2' r='1' fill='#e8c88a' opacity='0.35'/>"
    "</svg>"
)


def inject_css():
    st.markdown(
        f"""
        <style>
        html, body, [class*="css"] {{
            font-family: 'Segoe UI', Tahoma, sans-serif;
        }}

        .stApp {{
            background-image:
                url("data:image/svg+xml,{DOT_PATTERN_SVG}"),
                radial-gradient(circle at 12% 18%, rgba(230, 200, 156, 0.20), transparent 42%),
                radial-gradient(circle at 88% 12%, rgba(159, 140, 230, 0.22), transparent 46%),
                radial-gradient(circle at 50% 95%, rgba(120, 180, 200, 0.14), transparent 50%),
                linear-gradient(165deg, #0c0a18 0%, #171331 45%, #0a0916 100%);
            background-repeat: repeat, no-repeat, no-repeat, no-repeat, no-repeat;
            background-size: 28px 28px, auto, auto, auto, cover;
            background-attachment: fixed;
        }}

        .block-container {{
            max-width: 760px;
            background: rgba(255, 255, 255, 0.045);
            border: 1px solid rgba(230, 200, 156, 0.28);
            border-radius: 32px;
            padding: 3rem 3rem 3.5rem 3rem;
            box-shadow:
                0 24px 70px rgba(0, 0, 0, 0.45),
                inset 0 1px 0 rgba(255, 255, 255, 0.06);
            backdrop-filter: blur(18px);
            -webkit-backdrop-filter: blur(18px);
        }}

        h1, h1 span {{
            font-family: Georgia, 'Cambria', 'Times New Roman', serif !important;
            font-weight: 700;
            letter-spacing: 0.01em;
            background: linear-gradient(90deg, #e8c88a 0%, #c9a7f0 55%, #8fd0dc 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }}

        p, span, label, .stMarkdown, .stCaption, div[data-testid="stCaptionContainer"] {{
            color: #cfc9e8 !important;
        }}

        hr {{
            border-color: rgba(230, 200, 156, 0.25) !important;
        }}

        [data-testid="stChatMessage"] {{
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid rgba(230, 200, 156, 0.20);
            border-radius: 20px;
            padding: 0.65rem 1rem;
            box-shadow: 0 8px 24px rgba(0, 0, 0, 0.25);
            backdrop-filter: blur(10px);
        }}

        div[data-testid="stForm"] {{
            background: rgba(255, 255, 255, 0.04);
            border: 1px solid rgba(230, 200, 156, 0.22);
            border-radius: 24px;
            padding: 1.6rem;
            box-shadow: 0 16px 40px rgba(0, 0, 0, 0.3);
        }}

        button[data-testid^="stBaseButton"] {{
            background: linear-gradient(90deg, #e6c89c, #cda06a);
            color: #241a08;
            border: none;
            border-radius: 999px;
            padding: 0.55rem 1.6rem;
            font-weight: 600;
            letter-spacing: 0.01em;
            box-shadow: 0 6px 20px rgba(205, 160, 106, 0.35);
            transition: transform 0.15s ease, box-shadow 0.15s ease;
        }}

        button[data-testid^="stBaseButton"]:hover {{
            background: linear-gradient(90deg, #f0d5ab, #d9ae79);
            transform: translateY(-1px);
            box-shadow: 0 10px 26px rgba(205, 160, 106, 0.45);
        }}

        button[data-testid="stBaseButton-header"],
        button[data-testid="stMainMenuButton"] {{
            background: transparent;
            box-shadow: none;
            color: #cfc9e8;
        }}

        input, textarea {{
            background: rgba(255, 255, 255, 0.06) !important;
            color: #f3efe3 !important;
            border: 1px solid rgba(230, 200, 156, 0.25) !important;
            border-radius: 14px !important;
        }}

        input:focus, textarea:focus {{
            border-color: rgba(230, 200, 156, 0.6) !important;
            box-shadow: 0 0 0 1px rgba(230, 200, 156, 0.4) !important;
        }}

        [data-testid="stCheckbox"] label span {{
            color: #cfc9e8 !important;
        }}

        [data-baseweb="notification"] {{
            border-radius: 16px !important;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------
# Authentification (avec protection anti brute-force)
# ---------------------------------------------------------
def lockout_remaining_seconds():
    lockout_until = st.session_state.get("lockout_until")
    if lockout_until is None:
        return 0
    remaining = (lockout_until - datetime.datetime.now()).total_seconds()
    return max(0, int(remaining))


def register_failed_attempt():
    attempts = st.session_state.get("login_attempts", 0) + 1
    st.session_state.login_attempts = attempts

    if attempts >= MAX_LOGIN_ATTEMPTS:
        lockout_count = st.session_state.get("lockout_count", 0) + 1
        st.session_state.lockout_count = lockout_count
        duration = min(BASE_LOCKOUT_SECONDS * (2 ** (lockout_count - 1)), MAX_LOCKOUT_SECONDS)
        st.session_state.lockout_until = datetime.datetime.now() + datetime.timedelta(seconds=duration)
        st.session_state.login_attempts = 0
        return duration
    return None


def register_successful_login():
    st.session_state.authenticated = True
    st.session_state.login_attempts = 0
    st.session_state.lockout_count = 0
    st.session_state.lockout_until = None
    st.session_state.last_activity = datetime.datetime.now()


def login_screen():
    st.title("🔐 Virtual Assist")
    st.caption("Connectez-vous pour accéder à l'assistant.")

    remaining = lockout_remaining_seconds()
    if remaining > 0:
        st.error(f"🔒 Trop de tentatives échouées. Réessayez dans {remaining} secondes.")
        st.button("🔄 Actualiser", key="refresh_lockout")
        return

    with st.form("login_form"):
        username = st.text_input("Nom d'utilisateur")
        password = st.text_input("Mot de passe", type="password")
        submitted = st.form_submit_button("Se connecter")

    if submitted:
        creds = st.secrets.get("auth", {})
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        if username == creds.get("username") and password_hash == creds.get("password_hash"):
            register_successful_login()
            st.rerun()
        else:
            lockout_duration = register_failed_attempt()
            if lockout_duration:
                st.error(f"🔒 Trop de tentatives échouées. Compte verrouillé {lockout_duration} secondes.")
            else:
                attempts_left = MAX_LOGIN_ATTEMPTS - st.session_state.login_attempts
                st.error(f"Nom d'utilisateur ou mot de passe incorrect. ({attempts_left} tentative(s) restante(s))")


def session_expired():
    last_activity = st.session_state.get("last_activity")
    if last_activity is None:
        return False
    return datetime.datetime.now() - last_activity > datetime.timedelta(minutes=SESSION_TIMEOUT_MINUTES)


# ---------------------------------------------------------
# Application Streamlit
# ---------------------------------------------------------
def init_state():
    if "chat" not in st.session_state:
        st.session_state.chat = [
            {"role": "assistant", "content": "Bonjour, je suis Virtual Assist 🤖. Cliquez sur le micro ou tapez une commande."}
        ]


def repondre(command, source_label):
    st.session_state.chat.append({"role": "user", "content": f"{source_label} {command}" if command else f"{source_label} (rien entendu)"})
    reply, action = traiter_commande(command)
    st.session_state.chat.append({"role": "assistant", "content": reply})
    executer_action(action)
    if st.session_state.get("voix_active", True):
        try:
            parler(reply)
        except Exception:
            pass


def main():
    st.set_page_config(page_title="Virtual Assist", page_icon="🤖", layout="centered")
    inject_css()

    if not st.session_state.get("authenticated", False):
        login_screen()
        return

    if session_expired():
        st.session_state.authenticated = False
        st.session_state.last_activity = None
        st.warning("⏱️ Session expirée après 10 minutes d'inactivité. Veuillez vous reconnecter.")
        login_screen()
        return

    st.session_state.last_activity = datetime.datetime.now()
    init_state()

    top_left, top_right = st.columns([4, 1])
    with top_left:
        st.title("🤖 Virtual Assist")
        st.caption("Assistant vocal — parlez ou écrivez : « joue [chanson] », « quelle heure est-il », « qui est Albert Einstein », « c'est quoi la photosynthèse »...")
    with top_right:
        if st.button("🚪 Déconnexion"):
            st.session_state.authenticated = False
            st.session_state.last_activity = None
            st.rerun()

    st.checkbox("🔊 Réponse vocale (synthèse audio)", value=True, key="voix_active")

    for msg in st.session_state.chat:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    col1, col2 = st.columns([1, 3])
    with col1:
        if st.button("🎤 Parler"):
            with st.spinner("Je vous écoute..."):
                try:
                    command = ecouter()
                except OSError:
                    st.error("Aucun microphone détecté sur cet ordinateur.")
                    command = None
            if command is not None:
                repondre(command, "🎙️")
                st.rerun()

    with col2:
        typed = st.chat_input("Ou écrivez votre commande ici...")
        if typed:
            repondre(typed.lower(), "⌨️")
            st.rerun()


if __name__ == "__main__":
    main()
