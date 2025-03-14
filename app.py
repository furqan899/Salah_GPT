import streamlit as st
import requests
from bs4 import BeautifulSoup
import os
from openai import OpenAI
import json
from datetime import datetime
import pytz
import hashlib
import time

# Set page configuration
st.set_page_config(
    page_title="Salah GPT",
    page_icon="🕌",
    layout="wide"
)

# Initialize OpenAI client
openai_api_key = os.getenv("OPENAI_API_KEY", "")
if not openai_api_key:
    openai_api_key = st.sidebar.text_input("OpenAI API Key", type="password")

if openai_api_key:
    client = OpenAI(api_key=openai_api_key)

# API URLs
PRAYER_API_URL = "https://api.aladhan.com/v1/timingsByCity"
QIBLA_API_URL = "https://api.aladhan.com/v1/qibla"
QURAN_API_URL = "https://api.quran.com/api/v4/search"

# Initialize session cache and state
if "cache" not in st.session_state:
    st.session_state.cache = {}
if "sunnah_tracker" not in st.session_state:
    st.session_state.sunnah_tracker = {"Fajr": 0, "Dhuhr": 0, "Asr": 0, "Maghrib": 0, "Isha": 0}

# Helper functions
def get_cache_key(func_name, params):
    params_str = json.dumps(params, sort_keys=True)
    key = f"{func_name}:{params_str}"
    return hashlib.md5(key.encode()).hexdigest()

def search_islamic_websites(query, madhab=None):
    cache_key = get_cache_key("search_islamic_websites", {"query": query, "madhab": madhab})
    if cache_key in st.session_state.cache and time.time() - st.session_state.cache[cache_key]["timestamp"] < 3600:
        return st.session_state.cache[cache_key]["data"]
    
    results = []
    websites = [
        {"name": "IslamQA", "url": f"https://islamqa.info/en/search?q={query}+prayer"},
        {"name": "SeekersGuidance", "url": f"https://seekersguidance.org/search/{query}+prayer/"}
    ]
    headers = {"User-Agent": "Mozilla/5.0"}
    
    for site in websites:
        try:
            response = requests.get(site["url"], headers=headers, timeout=8)
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                site_results = []
                for article in soup.find_all('div', class_='search-item')[:3]:
                    title = article.find('h3').text.strip() if article.find('h3') else "No title"
                    link = article.find('a')['href'] if article.find('a') else ""
                    snippet = article.find('p').text.strip() if article.find('p') else "No preview"
                    site_results.append({"title": title, "link": link, "snippet": snippet})
                results.append({"source": site["name"], "results": site_results})
        except Exception as e:
            st.error(f"Error fetching from {site['name']}: {str(e)}")
    
    st.session_state.cache[cache_key] = {"timestamp": time.time(), "data": results}
    return results

def get_prayer_times(city, country, madhab=None):
    cache_key = get_cache_key("get_prayer_times", {"city": city, "country": country, "madhab": madhab})
    if cache_key in st.session_state.cache and time.time() - st.session_state.cache[cache_key]["timestamp"] < 21600:
        return st.session_state.cache[cache_key]["data"]
    
    method_map = {"hanafi": 1, "shafii": 3, "maliki": 3, "hanbali": 4, None: 2}
    method = method_map.get(madhab.lower() if madhab else None, 2)
    
    try:
        response = requests.get(PRAYER_API_URL, params={"city": city, "country": country, "method": method})
        if response.status_code == 200:
            data = response.json()
            st.session_state.cache[cache_key] = {"timestamp": time.time(), "data": data}
            return data
        return None
    except Exception as e:
        st.error(f"Error fetching prayer times: {str(e)}")
        return None

def get_qibla_direction(city, country):
    cache_key = get_cache_key("get_qibla_direction", {"city": city, "country": country})
    if cache_key in st.session_state.cache and time.time() - st.session_state.cache[cache_key]["timestamp"] < 2592000:
        return st.session_state.cache[cache_key]["data"]
    
    try:
        response = requests.get(QIBLA_API_URL, params={"city": city, "country": country})
        if response.status_code == 200:
            data = response.json()
            st.session_state.cache[cache_key] = {"timestamp": time.time(), "data": data}
            return data
        return None
    except Exception as e:
        st.error(f"Error fetching Qibla direction: {str(e)}")
        return None

def validate_wudu():
    steps = [
        "Wash hands 3 times",
        "Rinse mouth 3 times",
        "Clean nose 3 times",
        "Wash face 3 times",
        "Wash arms up to elbows 3 times",
        "Wipe head once",
        "Wash feet up to ankles 3 times"
    ]
    return "\n".join([f"- {step}" for step in steps]) + "\n\n**Note**: Ensure water reaches all required areas, maintain order (Hanafi/Shafi’i), and make niyyah (intention)."

def awrah_guidance(gender, madhab):
    guidance = {
        "Hanafi": {"Male": "Navel to knees", "Female": "Entire body except face, hands, and feet"},
        "Shafii": {"Male": "Navel to knees", "Female": "Entire body except face and hands"},
        "Maliki": {"Male": "Navel to knees", "Female": "Entire body except face and hands"},
        "Hanbali": {"Male": "Navel to knees", "Female": "Entire body except face and hands"}
    }
    madhab = madhab.capitalize() if madhab else "Hanafi"  # Default to Hanafi
    return guidance.get(madhab, guidance["Hanafi"])[gender.capitalize()]

def salah_validation():
    return """
    **Salah Prerequisites**:
    - Wudu: Complete ablution (see steps above).
    - Purity: Clean body, clothes, and place of prayer.
    - Niyyah: Intention in heart for specific prayer (e.g., 'I intend to pray 2 rak’ahs of Fajr').
    - Qibla: Face the Ka’bah.
    - Time: Perform within prayer window.
    
    **Pillars (Arkan)**:
    - Takbir al-Ihram: 'Allahu Akbar' to start.
    - Recite Surah Al-Fatihah: Mandatory in every rak’ah (Hanafi/Shafi’i).
    - Ruku: Bow with tuma’ninah (calmness, pause for 1-2 seconds).
    - Sujud: Prostrate twice per rak’ah with tuma’ninah.
    - Tashahhud: Sit and recite after 2nd and final rak’ah.
    - Tasleem: 'Assalamu alaikum wa rahmatullah' to end.
    """

def sunnah_prayers(prayer, madhab):
    sunnah_muakkadah = {
        "Fajr": 2, "Dhuhr": 4, "Maghrib": 2, "Isha": 2
    }
    return sunnah_muakkadah.get(prayer, 0)

def generate_response(query, results, madhab=None, gender="Male"):
    system_prompt = """
    You are Salah GPT, an Islamic AI assistant specializing in prayer guidance.
    - Provide accurate info from authentic sources.
    - Cite Quran/Hadith when applicable.
    - Respect Islamic etiquette.
    - Offer step-by-step guidance for prayer procedures.
    - Note madhab differences.
    - Include source references.
    """
    if madhab:
        system_prompt += f"\nPrioritize {madhab.capitalize()} madhab rulings."
    
    try:
        response = client.chat.completions.create(
            model="gpt-4-turbo",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Query: '{query}'\nSources:\n{json.dumps(results, indent=2)}\nGender: {gender}\nProvide a structured answer with references."}
            ]
        )
        return response.choices[0].message.content
    except Exception as e:
        st.error(f"Error generating response: {str(e)}")
        return None

# App UI
st.title("🕌 Salah GPT")
st.markdown("### Your Intelligent Islamic Prayer Assistant")

# Sidebar
st.sidebar.header("Settings")
madhab = st.sidebar.selectbox("Madhab", ["None", "Hanafi", "Shafii", "Maliki", "Hanbali"], index=0)
if madhab == "None": madhab = None
gender = st.sidebar.selectbox("Gender", ["Male", "Female"], index=0)

st.sidebar.header("Location")
city = st.sidebar.text_input("City")
country = st.sidebar.text_input("Country")

if city and country:
    st.sidebar.header("Prayer Information")
    prayer_data = get_prayer_times(city, country, madhab)
    if prayer_data and prayer_data.get("code") == 200:
        timings = prayer_data["data"]["timings"]
        st.sidebar.subheader(f"Prayer Times for {city}, {country}")
        for prayer in ["Fajr", "Dhuhr", "Asr", "Maghrib", "Isha"]:
            st.sidebar.markdown(f"**{prayer}**: {timings[prayer]}")
            sunnah_count = sunnah_prayers(prayer, madhab)
            if sunnah_count:
                if st.sidebar.button(f"Mark {sunnah_count} Sunnah for {prayer}"):
                    st.session_state.sunnah_tracker[prayer] += sunnah_count
                st.sidebar.markdown(f"Sunnah Performed: {st.session_state.sunnah_tracker[prayer]}")

    qibla_data = get_qibla_direction(city, country)
    if qibla_data and qibla_data.get("code") == 200:
        st.sidebar.markdown(f"**Qibla**: {qibla_data['data']['direction']}° from North")

# Main Interface
if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "assistant", "content": "Assalamu alaikum! Ask me about Salah, wudu, or prayer times!"}
    ]

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

query = st.chat_input("Ask about Salah...")
if query:
    st.session_state.messages.append({"role": "user", "content": query})
    with st.chat_message("user"):
        st.markdown(query)
    
    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        message_placeholder.markdown("🤔 Processing...")
        
        results = []
        if "wudu" in query.lower():
            results.append({"source": "Internal", "data": validate_wudu()})
        if "awrah" in query.lower():
            results.append({"source": "Internal", "data": awrah_guidance(gender, madhab)})
        if "salah" in query.lower():
            results.append({"source": "Internal", "data": salah_validation()})
        if "sunnah" in query.lower():
            results.append({"source": "Internal", "data": {p: sunnah_prayers(p, madhab) for p in ["Fajr", "Dhuhr", "Maghrib", "Isha"]}})
        
        website_results = search_islamic_websites(query, madhab)
        if website_results:
            results.append({"source": "Islamic Websites", "data": website_results})
        
        if city and country and "time" in query.lower():
            prayer_data = get_prayer_times(city, country, madhab)
            if prayer_data:
                results.append({"source": "Prayer Times API", "data": prayer_data["data"]})
        
        response = generate_response(query, results, madhab, gender) if results else "Please provide more details or check your API key."
        message_placeholder.markdown(response)
        st.session_state.messages.append({"role": "assistant", "content": response})

st.markdown("---")
st.markdown("*Sources: IslamQA, SeekersGuidance, Internal Logic*")