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

# Initialize session cache for API responses
if "cache" not in st.session_state:
    st.session_state.cache = {}

# Helper functions
def get_cache_key(func_name, params):
    """Generate a cache key from function name and parameters"""
    params_str = json.dumps(params, sort_keys=True)
    key = f"{func_name}:{params_str}"
    return hashlib.md5(key.encode()).hexdigest()

def search_islamic_websites(query, madhab=None):
    """Search reputable Islamic websites for information about salah"""
    cache_key = get_cache_key("search_islamic_websites", {"query": query, "madhab": madhab})
    
    # Check cache first
    if cache_key in st.session_state.cache:
        cache_entry = st.session_state.cache[cache_key]
        # Cache valid for 1 hour
        if time.time() - cache_entry["timestamp"] < 3600:
            return cache_entry["data"]
    
    results = []
    
    # List of reputable Islamic websites to search
    websites = [
        {"name": "IslamQA", "url": f"https://islamqa.info/en/search?q={query}+prayer"},
        {"name": "SeekersGuidance", "url": f"https://seekersguidance.org/search/{query}+prayer/"},
        {"name": "AboutIslam", "url": f"https://aboutislam.net/?s={query}+prayer"}
    ]
    
    # Add madhab-specific sources if madhab is specified
    if madhab:
        if madhab.lower() == "hanafi":
            websites.append({"name": "Hanafi Fiqh", "url": f"https://hanafifiqh.org/?s={query}+prayer"})
        elif madhab.lower() == "shafii":
            websites.append({"name": "Shafii Fiqh", "url": f"https://seekersguidance.org/search/{query}+prayer+shafi/"})
        elif madhab.lower() == "maliki":
            websites.append({"name": "Maliki Fiqh", "url": f"https://seekersguidance.org/search/{query}+prayer+maliki/"})
        elif madhab.lower() == "hanbali":
            websites.append({"name": "Hanbali Fiqh", "url": f"https://islamqa.info/en/search?q={query}+prayer+hanbali"})
    
    # User agent to mimic a browser
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    
    # Fetch and parse results from each website
    for site in websites:
        try:
            response = requests.get(site["url"], headers=headers, timeout=8)
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Extract relevant information (customized for each site)
                site_results = []
                
                if site["name"] == "IslamQA":
                    articles = soup.find_all('div', class_='search-item')
                    for article in articles[:3]:
                        title_elem = article.find('h3')
                        if title_elem and title_elem.find('a'):
                            title = title_elem.text.strip()
                            link = "https://islamqa.info" + title_elem.find('a')['href'] if title_elem.find('a')['href'].startswith('/') else title_elem.find('a')['href']
                            snippet = article.find('div', class_='search-item-excerpt')
                            content = snippet.text.strip() if snippet else "No preview available"
                            
                            site_results.append({
                                "title": title,
                                "link": link,
                                "snippet": content
                            })
                
                elif site["name"] == "SeekersGuidance":
                    articles = soup.find_all('article')
                    for article in articles[:3]:
                        title_elem = article.find('h2', class_='entry-title')
                        if title_elem and title_elem.find('a'):
                            title = title_elem.text.strip()
                            link = title_elem.find('a')['href']
                            snippet = article.find('div', class_='entry-summary')
                            content = snippet.text.strip() if snippet else "No preview available"
                            
                            site_results.append({
                                "title": title,
                                "link": link,
                                "snippet": content
                            })
                
                elif site["name"] == "AboutIslam":
                    articles = soup.find_all('article')
                    for article in articles[:3]:
                        title_elem = article.find('h2', class_='jeg_post_title')
                        if title_elem and title_elem.find('a'):
                            title = title_elem.text.strip()
                            link = title_elem.find('a')['href']
                            snippet = article.find('div', class_='jeg_post_excerpt')
                            content = snippet.text.strip() if snippet else "No preview available"
                            
                            site_results.append({
                                "title": title,
                                "link": link,
                                "snippet": content
                            })
                
                # Generic fallback if site-specific parsing fails
                if not site_results:
                    articles = soup.find_all('article') or soup.find_all('div', class_='result-item') or soup.find_all('div', class_='search-result')
                    for article in articles[:3]:
                        title_elem = article.find('h2') or article.find('h3') or article.find('h4')
                        if title_elem:
                            title = title_elem.text.strip()
                            link_elem = title_elem.find('a') or article.find('a')
                            link = link_elem['href'] if link_elem else ""
                            snippet = article.find('p') or article.find('div', class_='excerpt')
                            content = snippet.text.strip() if snippet else "No preview available"
                            
                            site_results.append({
                                "title": title,
                                "link": link,
                                "snippet": content
                            })
                
                if site_results:
                    results.append({
                        "source": site["name"],
                        "results": site_results
                    })
        except Exception as e:
            st.error(f"Error fetching from {site['name']}: {str(e)}")
    
    # Cache the results
    st.session_state.cache[cache_key] = {
        "timestamp": time.time(),
        "data": results
    }
    
    return results

def search_sunnah_database(query):
    """Search hadith collections for relevant information"""
    cache_key = get_cache_key("search_sunnah_database", {"query": query})
    
    # Check cache first
    if cache_key in st.session_state.cache:
        cache_entry = st.session_state.cache[cache_key]
        # Cache valid for 1 day
        if time.time() - cache_entry["timestamp"] < 86400:
            return cache_entry["data"]
    
    try:
        # Using sunnah.com for search results (web scraping as they don't have a public API)
        url = f"https://sunnah.com/search?q={query}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            hadith_results = []
            
            # Parse hadith results from sunnah.com
            results = soup.find_all('div', class_='hadith_container')
            
            for result in results[:5]:  # Limit to top 5 hadiths
                collection = result.find('div', class_='book_title')
                collection_name = collection.text.strip() if collection else "Unknown Collection"
                
                hadith_text = result.find('div', class_='text_details')
                text = hadith_text.text.strip() if hadith_text else "Hadith text not available"
                
                reference = result.find('div', class_='hadith_reference')
                ref_text = reference.text.strip() if reference else "Reference not available"
                
                hadith_results.append({
                    "collection": collection_name,
                    "text": text,
                    "reference": ref_text
                })
            
            # Cache the results
            st.session_state.cache[cache_key] = {
                "timestamp": time.time(),
                "data": hadith_results
            }
            
            return hadith_results
        else:
            return None
    except Exception as e:
        st.error(f"Error searching hadith database: {str(e)}")
        return None

def search_quran(query):
    """Search Quran for specific keywords"""
    cache_key = get_cache_key("search_quran", {"query": query})
    
    # Check cache first
    if cache_key in st.session_state.cache:
        cache_entry = st.session_state.cache[cache_key]
        # Cache valid for 1 week (Quran content doesn't change)
        if time.time() - cache_entry["timestamp"] < 604800:
            return cache_entry["data"]
    
    try:
        response = requests.get(QURAN_API_URL, params={
            "q": query,
            "size": 5,
            "page": 1,
            "language": "en"
        })
        
        if response.status_code == 200:
            data = response.json()
            
            # Cache the results
            st.session_state.cache[cache_key] = {
                "timestamp": time.time(),
                "data": data
            }
            
            return data
        else:
            return None
    except Exception as e:
        st.error(f"Error searching Quran: {str(e)}")
        return None

def get_prayer_times(city, country, madhab=None):
    """Get prayer times for a specific location"""
    cache_key = get_cache_key("get_prayer_times", {"city": city, "country": country, "madhab": madhab})
    
    # Check cache first - but with shorter expiry as prayer times change daily
    if cache_key in st.session_state.cache:
        cache_entry = st.session_state.cache[cache_key]
        # Cache valid for 6 hours
        if time.time() - cache_entry["timestamp"] < 21600:
            return cache_entry["data"]
    
    try:
        # Map madhabs to calculation methods
        method_map = {
            "hanafi": 1,  # University of Islamic Sciences, Karachi (Hanafi)
            "shafii": 3,  # Muslim World League (close to Shafi'i)
            "maliki": 3,  # Muslim World League (used by many Malikis)
            "hanbali": 4,  # Umm Al-Qura University, Makkah
            None: 2       # Islamic Society of North America (default)
        }
        
        method = method_map.get(madhab.lower() if madhab else None, 2)
        
        response = requests.get(PRAYER_API_URL, params={
            "city": city,
            "country": country,
            "method": method
        })
        
        if response.status_code == 200:
            data = response.json()
            
            # Cache the results
            st.session_state.cache[cache_key] = {
                "timestamp": time.time(),
                "data": data
            }
            
            return data
        else:
            return None
    except Exception as e:
        st.error(f"Error fetching prayer times: {str(e)}")
        return None

def get_qibla_direction(city, country):
    """Get Qibla direction for a specific location"""
    cache_key = get_cache_key("get_qibla_direction", {"city": city, "country": country})
    
    # Check cache first
    if cache_key in st.session_state.cache:
        cache_entry = st.session_state.cache[cache_key]
        # Cache valid for 1 month (Qibla direction doesn't change)
        if time.time() - cache_entry["timestamp"] < 2592000:
            return cache_entry["data"]
    
    try:
        response = requests.get(QIBLA_API_URL, params={
            "city": city,
            "country": country
        })
        
        if response.status_code == 200:
            data = response.json()
            
            # Cache the results
            st.session_state.cache[cache_key] = {
                "timestamp": time.time(),
                "data": data
            }
            
            return data
        else:
            return None
    except Exception as e:
        st.error(f"Error fetching Qibla direction: {str(e)}")
        return None


def validate_wudu():
    """Return step-by-step wudu instructions"""
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

def salah_validation():
    """Return prerequisites and pillars of salah"""
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

def awrah_guidance(gender, madhab):
    """Return awrah guidance based on gender and madhab"""
    guidance = {
        "Hanafi": {"Male": "Navel to knees", "Female": "Entire body except face, hands, and feet"},
        "Shafii": {"Male": "Navel to knees", "Female": "Entire body except face and hands"},
        "Maliki": {"Male": "Navel to knees", "Female": "Entire body except face and hands"},
        "Hanbali": {"Male": "Navel to knees", "Female": "Entire body except face and hands"}
    }
    madhab = madhab.capitalize() if madhab else "Hanafi"  # Default to Hanafi
    return guidance.get(madhab, guidance["Hanafi"])[gender.capitalize()]

def sunnah_prayers(prayer, madhab):
    """Return the number of sunnah rak’ahs for a given prayer"""
    sunnah_muakkadah = {
        "Fajr": 2, "Dhuhr": 4, "Maghrib": 2, "Isha": 2
    }
    return sunnah_muakkadah.get(prayer, 0)


from langdetect import detect

def detect_language(text):
    """Detect the language of the input text."""
    try:
        return detect(text)
    except:
        return "en"  # Default to English if detection fails

def generate_response(query, results, madhab=None):
    """Generate response using OpenAI in the same language as the query."""
    if not openai_api_key:
        st.error("Please provide an OpenAI API key to generate responses.")
        return None
    
    # Detect the language of the query
    query_language = detect_language(query)
    
    # Create system prompt based on madhab preference and detected language
    system_prompt = f"""
    You are Salah GPT, an Islamic AI assistant specializing in prayer (Salah) guidance.
    When providing information:
    1. Always give accurate information according to authentic Islamic sources
    2. Cite Quran verses and Hadith when applicable
    3. Be respectful and maintain Islamic etiquette in responses
    4. Provide detailed step-by-step guidance when asked about prayer procedures
    5. Acknowledge differences between madhabs (schools of thought)
    6. Include references to the websites or sources where information was found
    7. Format your response in a clear, organized way with headings and bullet points when appropriate
    8. Respond in the same language as the user's query. The user's query is in {query_language}, so respond in {query_language}.
    """
    if madhab:
        system_prompt += f"\nThe user follows the {madhab.capitalize()} madhab, so prioritize rulings according to this school of thought while acknowledging others when relevant."
    
    try:
        response = client.chat.completions.create(
            model="gpt-4-turbo",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"The user asked: '{query}'\n\nHere are the relevant sources I've found:\n{json.dumps(results, indent=2)}\n\nProvide a structured, easy-to-understand answer with references. If there are differences between madhabs on this topic, explain them respectfully. Make sure to cite sources where information was found."}
            ]
        )
        
        return response.choices[0].message.content
    except Exception as e:
        st.error(f"Error generating response: {str(e)}")
        return None

import streamlit.components.v1 as components

# JavaScript to fetch client timezone
timezone_js = """
<script>
const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
window.parent.postMessage({timezone: timezone}, "*");
</script>
"""

# Inject JavaScript and listen for the response
components.html(timezone_js, height=0)

# Get the timezone from the client
if "timezone" not in st.session_state:
    st.session_state.timezone = "UTC"

def get_user_timezone():
    return pytz.timezone(st.session_state.timezone)

# App UI
st.title("🕌 Salah GPT")
st.markdown("### Your Intelligent Islamic Prayer Assistant")

# Sidebar for settings
st.sidebar.header("Settings")
madhab = st.sidebar.selectbox(
    "Select Your Madhab (School of Thought)",
    options=["None", "Hanafi", "Shafii", "Maliki", "Hanbali"],
    index=0
)

if madhab == "None":
    madhab = None

# Location information
st.sidebar.header("Your Location")
city = st.sidebar.text_input("City")
country = st.sidebar.text_input("Country")

# Display current prayer time if location is provided
if city and country:
    st.sidebar.header("Prayer Information")
    
    prayer_data = get_prayer_times(city, country, madhab)
    qibla_data = get_qibla_direction(city, country)
    
    if prayer_data and prayer_data.get("code") == 200:
        timings = prayer_data["data"]["timings"]
        date = prayer_data["data"]["date"]["readable"]
        
        st.sidebar.subheader(f"Prayer Times for {city}, {country}")
        st.sidebar.markdown(f"**Date**: {date}")
        
        # Display prayer times
        for prayer in ["Fajr", "Sunrise", "Dhuhr", "Asr", "Maghrib", "Isha"]:
            st.sidebar.markdown(f"**{prayer}**: {timings[prayer]}")
        
        # Get local timezone
        local_tz = get_user_timezone()
        
        # Determine current prayer
        now = datetime.now(local_tz)
        current_time = now.strftime("%H:%M")
        
        # Simple logic to determine current/next prayer (improved)
        prayer_order = ["Fajr", "Sunrise", "Dhuhr", "Asr", "Maghrib", "Isha"]
        current_prayer = None
        next_prayer = None
        
        # Convert times to comparable format
        current_minutes = int(current_time.split(":")[0]) * 60 + int(current_time.split(":")[1])
        prayer_minutes = {}
        
        for prayer in prayer_order:
            prayer_time = timings[prayer]
            hours, minutes = map(int, prayer_time.split(":"))
            prayer_minutes[prayer] = hours * 60 + minutes
        
        # Find current and next prayers
        for i, prayer in enumerate(prayer_order):
            if current_minutes < prayer_minutes[prayer]:
                if i == 0:
                    current_prayer = "Isha (from yesterday)"
                    next_prayer = prayer
                else:
                    current_prayer = prayer_order[i-1]
                    next_prayer = prayer
                break
        
        # If we've passed all prayers, it's after Isha
        if not current_prayer:
            current_prayer = "Isha"
            next_prayer = "Fajr (tomorrow)"
        
        st.sidebar.markdown("---")
        st.sidebar.markdown(f"**Current Prayer**: {current_prayer}")
        st.sidebar.markdown(f"**Next Prayer**: {next_prayer}")
    
    if qibla_data and qibla_data.get("code") == 200:
        qibla_direction = qibla_data["data"]["direction"]
        st.sidebar.markdown("---")
        st.sidebar.subheader("Qibla Direction")
        st.sidebar.markdown(f"**Direction**: {qibla_direction}° from North")

# Main chat interface
st.markdown("---")
if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "assistant", "content": "Assalamu alaikum! I'm Salah GPT, your Islamic prayer assistant. I search reputable Islamic websites to provide accurate information about Salah (prayer), prayer times, wudu, and other prayer-related questions. Ask me anything!"}
    ]

# Display chat messages
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Chat input
query = st.chat_input("Ask about Salah (prayer)...")

if query:
    # Add user message to chat history
    st.session_state.messages.append({"role": "user", "content": query})
    
    # Display user message
    with st.chat_message("user"):
        st.markdown(query)
    
    # Show processing message
    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        message_placeholder.markdown("🤔 Processing your question...")
        
        # Gather information from various sources
        results = []
        
        # 1. Search Islamic websites
        website_results = search_islamic_websites(query, madhab)
        if website_results:
            results.append({"source": "Islamic Websites", "data": website_results})
        
        # 2. Search hadith database
        if any(keyword in query.lower() for keyword in ["hadith", "prophet", "sunnah", "tradition"]):
            hadith_results = search_sunnah_database(query)
            if hadith_results:
                results.append({"source": "Hadith Database", "data": hadith_results})
        
        # 3. Get prayer times if location is provided and query seems relevant
        if city and country and any(keyword in query.lower() for keyword in ["time", "prayer", "when", "schedule"]):
            prayer_data = get_prayer_times(city, country, madhab)
            if prayer_data and prayer_data.get("code") == 200:
                results.append({"source": "Prayer Times API", "data": prayer_data["data"]})
        
        # 4. Get Qibla information if location is provided and query seems relevant
        if city and country and "qibla" in query.lower():
            qibla_data = get_qibla_direction(city, country)
            if qibla_data and qibla_data.get("code") == 200:
                results.append({"source": "Qibla API", "data": qibla_data["data"]})
        
        # 5. Search Quran if relevant
        if any(keyword in query.lower() for keyword in ["quran", "verse", "ayah", "surah", "ayat"]):
            quran_data = search_quran(query)
            if quran_data and "search" in quran_data and "results" in quran_data["search"]:
                results.append({"source": "Quran API", "data": {"verses": quran_data["search"]["results"]}})
        
        # Generate response
        if results:
            response = generate_response(query, results, madhab)
            if response:
                message_placeholder.markdown(response)
                st.session_state.messages.append({"role": "assistant", "content": response})
            else:
                message_placeholder.markdown("I apologize, but I couldn't generate a response. Please try again or check your API key.")
        else:
            generic_response = """
            I don't have enough information from trusted Islamic sources to fully answer your question. 
            
            Could you:
            - Be more specific about your question?
            - Mention the specific aspect of prayer you're asking about?
            - Provide your city and country to get accurate prayer times?
            
            I strive to provide accurate information from reputable Islamic sources rather than relying on pre-programmed knowledge.
            """
            message_placeholder.markdown(generic_response)
            st.session_state.messages.append({"role": "assistant", "content": generic_response})

# Footer
st.markdown("---")
st.markdown("""
*This application provides Islamic prayer guidance based on information from reputable Islamic websites. 
Always consult with knowledgeable scholars for specific religious rulings.*

*Sources: IslamQA, SeekersGuidance, SunnahOnline, and other reputable Islamic websites.*
""")
