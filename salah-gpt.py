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
import asyncio
import aiohttp
from functools import wraps
import html
from dotenv import load_dotenv
import concurrent.futures
import threading
from langdetect import detect
import streamlit.components.v1 as components
from geopy.geocoders import Nominatim
from timezonefinder import TimezoneFinder
# Load environment variables from .env file if present
load_dotenv()

# Set page configuration
st.set_page_config(
    page_title="Salah GPT",
    page_icon="🕌",
    layout="wide"
)

# Apply custom CSS
st.markdown("""
<style>
    .main .block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
    }
    h1, h2, h3 {
        color: #2c3e50;
    }
    .stApp {
        background-color: #f8f9fa;
    }
    .css-1d391kg {
        background-color: #ffffff;
        border-radius: 10px;
        padding: 20px;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
    }
    .sidebar .sidebar-content {
        background-color: #f1f3f5;
    }
    .prayer-time {
        background-color: #eef2f7;
        padding: 10px;
        border-radius: 5px;
        margin-bottom: 10px;
    }
    .current-prayer {
        background-color: #e3f2fd;
        border-left: 4px solid #1976d2;
    }
    .css-1v0mbdj.e115fcil1 {
        max-width: 1200px;
    }
</style>
""", unsafe_allow_html=True)

# Initialize OpenAI client from environment variable first
openai_api_key = os.getenv("OPENAI_API_KEY", "")

# If not in environment, ask via sidebar but with improved security
if not openai_api_key:
    openai_api_key = st.sidebar.text_input("OpenAI API Key", type="password")
    if openai_api_key:
        # Don't store the API key in session state to reduce exposure
        pass

if openai_api_key:
    client = OpenAI(api_key=openai_api_key)

# API URLs
PRAYER_API_URL = "https://api.aladhan.com/v1/timingsByCity"
QIBLA_API_URL = "https://api.aladhan.com/v1/qibla"
QURAN_API_URL = "https://api.quran.com/api/v4/search"

# Initialize session cache for API responses
if "cache" not in st.session_state:
    st.session_state.cache = {}

# Add a request semaphore to limit concurrent requests
REQUEST_SEMAPHORE = threading.Semaphore(5)

# Initialize request timeout and retry parameters
REQUEST_TIMEOUT = 10  # seconds
MAX_RETRIES = 3
RETRY_DELAY = 2  # seconds

# Helper functions
def get_cache_key(func_name, params):
    """Generate a cache key from function name and parameters"""
    # Sanitize params to remove any sensitive information
    if isinstance(params, dict) and "api_key" in params:
        sanitized_params = params.copy()
        sanitized_params["api_key"] = "REDACTED"
    else:
        sanitized_params = params
    
    params_str = json.dumps(sanitized_params, sort_keys=True)
    key = f"{func_name}:{params_str}"
    return hashlib.md5(key.encode()).hexdigest()

def cached(expiry_seconds):
    """Decorator to cache function results with given expiry time"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Create cache key from function name and arguments
            params = {
                "args": args,
                "kwargs": kwargs
            }
            cache_key = get_cache_key(func.__name__, params)
            
            # Check cache first
            if cache_key in st.session_state.cache:
                cache_entry = st.session_state.cache[cache_key]
                # Check if cache is still valid
                if time.time() - cache_entry["timestamp"] < expiry_seconds:
                    return cache_entry["data"]
            
            # Call the function if cache miss or expired
            result = func(*args, **kwargs)
            
            # Cache the result
            if result is not None:
                st.session_state.cache[cache_key] = {
                    "timestamp": time.time(),
                    "data": result
                }
            
            return result
        return wrapper
    return decorator

def retry_request(func):
    """Decorator to retry failed requests"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        retries = 0
        last_exception = None
        
        while retries < MAX_RETRIES:
            try:
                return func(*args, **kwargs)
            except (requests.RequestException, aiohttp.ClientError) as e:
                last_exception = e
                retries += 1
                if retries < MAX_RETRIES:
                    time.sleep(RETRY_DELAY * retries)  # Exponential backoff
        
        # If all retries failed, log error and return None
        st.error(f"Request failed after {MAX_RETRIES} attempts: {str(last_exception)}")
        return None
    return wrapper

def sanitize_input(text):
    """Sanitize user input to prevent injection attacks"""
    if text is None:
        return ""
    # Escape HTML entities and strip potentially dangerous characters
    return html.escape(text).strip()

@cached(3600)  # Cache for 1 hour
@retry_request
def search_islamic_websites(query, madhab=None):
    """Search reputable Islamic websites for information about salah"""
    sanitized_query = sanitize_input(query)
    results = []
    
    # List of reputable Islamic websites to search
    websites = [
        {"name": "IslamQA", "url": f"https://islamqa.info/en/search?q={sanitized_query}+prayer"},
        {"name": "SeekersGuidance", "url": f"https://seekersguidance.org/search/{sanitized_query}+prayer/"},
        {"name": "AboutIslam", "url": f"https://aboutislam.net/?s={sanitized_query}+prayer"}
    ]
    
    # Add madhab-specific sources if madhab is specified
    if madhab:
        sanitized_madhab = sanitize_input(madhab)
        if sanitized_madhab.lower() == "hanafi":
            websites.append({"name": "Hanafi Fiqh", "url": f"https://hanafifiqh.org/?s={sanitized_query}+prayer"})
        elif sanitized_madhab.lower() == "shafii":
            websites.append({"name": "Shafii Fiqh", "url": f"https://seekersguidance.org/search/{sanitized_query}+prayer+shafi/"})
        elif sanitized_madhab.lower() == "maliki":
            websites.append({"name": "Maliki Fiqh", "url": f"https://seekersguidance.org/search/{sanitized_query}+prayer+maliki/"})
        elif sanitized_madhab.lower() == "hanbali":
            websites.append({"name": "Hanbali Fiqh", "url": f"https://islamqa.info/en/search?q={sanitized_query}+prayer+hanbali"})
    
    # User agent to mimic a browser
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    
    # Use ThreadPoolExecutor for concurrent requests
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        # Submit all requests
        future_to_site = {
            executor.submit(
                _fetch_and_parse_website, site, headers, REQUEST_TIMEOUT
            ): site for site in websites
        }
        
        # Process results as they complete
        for future in concurrent.futures.as_completed(future_to_site):
            site = future_to_site[future]
            try:
                site_result = future.result()
                if site_result:
                    results.append({
                        "source": site["name"],
                        "results": site_result
                    })
            except Exception as e:
                st.error(f"Error fetching from {site['name']}: {str(e)}")
    
    return results

def _fetch_and_parse_website(site, headers, timeout):
    """Helper function to fetch and parse a website"""
    try:
        with REQUEST_SEMAPHORE:
            response = requests.get(site["url"], headers=headers, timeout=timeout)
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
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
            
            return site_results
        return None
    except Exception as e:
        print(f"Error in _fetch_and_parse_website for {site['name']}: {str(e)}")
        return None

@cached(86400)  # Cache for 1 day
@retry_request
def search_sunnah_database(query):
    """Search hadith collections for relevant information"""
    sanitized_query = sanitize_input(query)
    
    try:
        # Using sunnah.com for search results (web scraping as they don't have a public API)
        url = f"https://sunnah.com/search?q={sanitized_query}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        
        with REQUEST_SEMAPHORE:
            response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
        
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
            
            return hadith_results
        else:
            return None
    except Exception as e:
        st.error(f"Error searching hadith database: {str(e)}")
        return None

@cached(604800)  # Cache for 1 week (Quran content doesn't change)
@retry_request
def search_quran(query):
    """Search Quran for specific keywords"""
    sanitized_query = sanitize_input(query)
    
    try:
        with REQUEST_SEMAPHORE:
            response = requests.get(QURAN_API_URL, params={
                "q": sanitized_query,
                "size": 5,
                "page": 1,
                "language": "en"
            }, timeout=REQUEST_TIMEOUT)
        
        if response.status_code == 200:
            data = response.json()
            return data
        else:
            st.warning(f"Quran API returned status code {response.status_code}")
            return None
    except Exception as e:
        st.error(f"Error searching Quran: {str(e)}")
        return None

@cached(21600)  # Cache for 6 hours
@retry_request
def get_prayer_times(city, country, madhab=None):
    """Get prayer times for a specific location with improved accuracy"""
    
    sanitized_city = sanitize_input(city)
    sanitized_country = sanitize_input(country)
    
    try:
        # Map madhabs to calculation methods for better accuracy
        method_map = {
            "hanafi": 1,  # University of Islamic Sciences, Karachi (Hanafi)
            "shafii": 3,  # Muslim World League (close to Shafi'i)
            "maliki": 3,  # Muslim World League (used by many Malikis)
            "hanbali": 4,  # Umm Al-Qura University, Makkah
            None: 2       # Islamic Society of North America (default)
        }
        
        method = method_map.get(madhab.lower() if madhab else None, 2)
        
        # Add adjustment options for better accuracy
        params = {
            "city": sanitized_city,
            "country": sanitized_country,
            "method": method,
            "tune": "0,0,0,0,0,0,0,0,0"  # Optional fine-tuning of times
        }
        
        with REQUEST_SEMAPHORE:
            response = requests.get(PRAYER_API_URL, params=params, timeout=REQUEST_TIMEOUT)
        
        if response.status_code == 200:
            data = response.json()
            
            # ✅ Removed debug print statement (for production readiness)
            
            return data
        else:
            st.warning(f"Prayer API returned status code {response.status_code}")
            return None
    except Exception as e:
        st.error(f"Error fetching prayer times: {str(e)}")
        return None

def detect_language(text):
    """Detect the language of the input text."""
    try:
        return detect(text)
    except:
        return "en"  # Default to English if detection fails

@retry_request
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

def get_location_timezone(city, country):
    try:
        geolocator = Nominatim(user_agent="salah_gpt")
        location = geolocator.geocode(f"{city}, {country}")
        if location:
            tf = TimezoneFinder()
            timezone_str = tf.timezone_at(lat=location.latitude, lng=location.longitude)
            if timezone_str:
                return pytz.timezone(timezone_str)
        # Fallback to UTC if timezone cannot be determined
        return pytz.timezone("UTC")
    except Exception as e:
        st.warning(f"Could not determine timezone: {str(e)}. Using UTC as fallback.")
        return pytz.timezone("UTC")

# JavaScript to fetch client timezone
timezone_js = """
<script>
document.addEventListener('DOMContentLoaded', function() {
    const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
    window.parent.postMessage({timezone: timezone}, "*");
});

window.addEventListener('message', function(event) {
    if (event.data.hasOwnProperty('timezone')) {
        window.parent.postMessage({timezone: event.data.timezone}, "*");
    }
});
</script>
"""

# Inject JavaScript and listen for the response
components.html(timezone_js, height=0)

# App UI
st.title("🕌 Salah GPT")
st.markdown("""
<div style="background-color: #f1f8e9; padding: 20px; border-radius: 10px; border-left: 5px solid #558b2f;">
<h3 style="margin-top: 0;">Your Intelligent Islamic Prayer Assistant</h3>
<p>Ask questions about Salah, prayer times, wudu, and other prayer-related topics. I'll search reputable Islamic sources to provide accurate information.</p>
</div>
""", unsafe_allow_html=True)

# Sidebar for settings
with st.sidebar:
    st.image("https://raw.githubusercontent.com/twitter/twemoji/master/assets/svg/1f54b.svg", width=100)
    st.header("Settings")
    
    madhab_options = ["None", "Hanafi", "Shafii", "Maliki", "Hanbali"]
    madhab = st.selectbox(
        "Select Your Madhab (School of Thought)",
        options=madhab_options,
        index=0
    )

    if madhab == "None":
        madhab = None

    # Location information with improved styling
    st.header("Your Location")
    
    col1, col2 = st.columns(2)
    with col1:
        city = st.text_input("City")
    with col2:
        country = st.text_input("Country")

# Sidebar prayer times section
if city and country:
    with st.sidebar:
        st.markdown("""
        <div style="background-color: #e8f5e9; padding: 15px; border-radius: 10px; margin-top: 20px;">
        <h3 style="margin-top: 0; color: #2e7d32;">Prayer Information</h3>
        """, unsafe_allow_html=True)
        
        with st.spinner("Fetching prayer times and timezone..."):
            prayer_data = get_prayer_times(city, country, madhab)
            local_tz = get_location_timezone(city, country)
        
        if prayer_data and prayer_data.get("code") == 200:
            timings = prayer_data["data"]["timings"]
            date = prayer_data["data"]["date"]["readable"]
            
            # Get current time in the location's timezone
            now = datetime.now(local_tz)
            current_time = now.strftime("%H:%M:%S")
            
            st.markdown(f"#### Prayer Times for {city}, {country}")
            st.markdown(f"**Date**: {date}")
            st.markdown(f"**Current Local Time**: {current_time} ({local_tz.zone})")
            
            # Prayer order
            prayer_order = ["Fajr", "Sunrise", "Dhuhr", "Asr", "Maghrib", "Isha"]
            
            # Convert times to minutes for comparison
            current_minutes = int(current_time.split(":")[0]) * 60 + int(current_time.split(":")[1])
            prayer_minutes = {prayer: int(timings[prayer].split(":")[0]) * 60 + int(timings[prayer].split(":")[1]) for prayer in prayer_order}
            
            # Determine current and next prayer
            current_prayer = None
            next_prayer = None
            for i, prayer in enumerate(prayer_order):
                if current_minutes < prayer_minutes[prayer]:
                    if i == 0:
                        current_prayer = "Isha (from yesterday)"
                        next_prayer = prayer
                    else:
                        current_prayer = prayer_order[i-1]
                        next_prayer = prayer
                    break
            if not current_prayer:
                current_prayer = "Isha"
                next_prayer = "Fajr (tomorrow)"
            
            # Display prayer times
            st.markdown("<div style='background-color: #f5f5f5; padding: 10px; border-radius: 5px;'>", unsafe_allow_html=True)
            for prayer in prayer_order:
                time_display = timings[prayer]
                if prayer == current_prayer or (current_prayer == "Isha (from yesterday)" and prayer == "Isha") or (current_prayer == "Isha" and next_prayer == "Fajr (tomorrow)" and prayer == "Isha"):
                    st.markdown(f"""
                    <div style='background-color: #b3e5fc; padding: 8px; border-radius: 5px; margin-bottom: 5px; border-left: 4px solid #0288d1;'>
                        <strong>{prayer}:</strong> {time_display} <span style='color: #0288d1; float: right;'>Current</span>
                    </div>
                    """, unsafe_allow_html=True)
                elif prayer == next_prayer or (next_prayer == "Fajr (tomorrow)" and prayer == "Fajr"):
                    st.markdown(f"""
                    <div style='background-color: #e8f5e9; padding: 8px; border-radius: 5px; margin-bottom: 5px; border-left: 4px solid #43a047;'>
                        <strong>{prayer}:</strong> {time_display} <span style='color: #43a047; float: right;'>Next</span>
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    st.markdown(f"""
                    <div style='padding: 8px; border-radius: 5px; margin-bottom: 5px;'>
                        <strong>{prayer}:</strong> {time_display}
                    </div>
                    """, unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)
            
            st.markdown("</div>", unsafe_allow_html=True)
        else:
            st.error("Could not fetch prayer times. Please check your city and country names.")

# Main chat interface
st.markdown("---")
if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "assistant", "content": "Assalamu alaikum! I'm Salah GPT, your Islamic prayer assistant. I search reputable Islamic websites to provide accurate information about Salah (prayer), prayer times, wudu, and other prayer-related questions. Ask me anything!"}
    ]

# Display chat messages with improved styling
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
        
        # Create placeholder for errors to show at the end
        errors = []
        
        try:
            # 1. Search Islamic websites
            with st.spinner("Searching Islamic websites..."):
                website_results = search_islamic_websites(query, madhab)
                if website_results:
                    results.append({"source": "Islamic Websites", "data": website_results})
        except Exception as e:
            errors.append(f"Error searching Islamic websites: {str(e)}")
        
        try:
            # 2. Search hadith database
            if any(keyword in query.lower() for keyword in ["hadith", "prophet", "sunnah", "tradition"]):
                with st.spinner("Searching hadith database..."):
                    hadith_results = search_sunnah_database(query)
                    if hadith_results:
                        results.append({"source": "Hadith Database", "data": hadith_results})
        except Exception as e:
            errors.append(f"Error searching hadith database: {str(e)}")
        
        try:
            # 3. Get prayer times if location is provided and query seems relevant
            if city and country and any(keyword in query.lower() for keyword in ["time", "prayer", "when", "schedule"]):
                with st.spinner("Fetching prayer times..."):
                    prayer_data = get_prayer_times(city, country, madhab)
                    if prayer_data and prayer_data.get("code") == 200:
                        results.append({"source": "Prayer Times API", "data": prayer_data["data"]})
        except Exception as e:
            errors.append(f"Error fetching prayer times: {str(e)}")
        
        try:
            # 4. Search Quran if relevant
            if any(keyword in query.lower() for keyword in ["quran", "verse", "ayah", "surah", "ayat"]):
                with st.spinner("Searching Quran..."):
                    quran_data = search_quran(query)
                    if quran_data and "search" in quran_data and "results" in quran_data["search"]:
                        results.append({"source": "Quran API", "data": {"verses": quran_data["search"]["results"]}})
        except Exception as e:
            errors.append(f"Error searching Quran: {str(e)}")
        
        # Generate response
        try:
            if results:
                with st.spinner("Generating response..."):
                    response = generate_response(query, results, madhab)
                    if response:
                        message_placeholder.markdown(response)
                        st.session_state.messages.append({"role": "assistant", "content": response})
                    else:
                        fallback_response = """
                        I apologize, but I couldn't generate a response based on the information I found. This might be due to:
                        
                        - Limited information available on this specific topic
                        - Technical issues with the search results
                        - Issues with processing the query
                        
                        Could you try rephrasing your question or asking about a different aspect of prayer?
                        """
                        message_placeholder.markdown(fallback_response)
                        st.session_state.messages.append({"role": "assistant", "content": fallback_response})
            else:
                # Display any errors that occurred during searches
                if errors:
                    error_message = "I encountered some issues while searching for information:\n\n"
                    for error in errors:
                        error_message += f"- {error}\n"
                    st.warning(error_message)
                
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
        except Exception as e:
            st.error(f"Error generating final response: {str(e)}")
            fallback_response = "I apologize, but I encountered an error while processing your question. Please try again or rephrase your question."
            message_placeholder.markdown(fallback_response)
            st.session_state.messages.append({"role": "assistant", "content": fallback_response})

# Add a "Clear Conversation" button
if st.button("Clear Conversation"):
    st.session_state.messages = [
        {"role": "assistant", "content": "Assalamu alaikum! I'm Salah GPT, your Islamic prayer assistant. I search reputable Islamic websites to provide accurate information about Salah (prayer), prayer times, wudu, and other prayer-related questions. Ask me anything!"}
    ]
    st.rerun()

# Footer with improved styling
st.markdown("---")
st.markdown("""
<div style="background-color: #f5f5f5; padding: 15px; border-radius: 10px; text-align: center; margin-top: 20px;">
    <p style="font-style: italic; margin-bottom: 5px;">This application provides Islamic prayer guidance based on information from reputable Islamic websites.</p>
    <p style="font-style: italic; margin-bottom: 5px;">Always consult with knowledgeable scholars for specific religious rulings.</p>
    <p style="font-size: 0.8em; color: #666;">Sources: IslamQA, SeekersGuidance, SunnahOnline, and other reputable Islamic websites.</p>
</div>
""", unsafe_allow_html=True)

# Add version information
st.sidebar.markdown("---")
st.sidebar.markdown("""
<div style="text-align: center; font-size: 0.8em; color: #666;">
    Salah GPT v2.0<br>
    Developed with ❤️ for the Islamic community
</div>
""", unsafe_allow_html=True)