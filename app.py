from flask import Flask, render_template, request, session, redirect, url_for, jsonify
import requests
from googletrans import Translator
from transformers import pipeline
import re
import os
import datetime
from dotenv import load_dotenv
from functools import lru_cache

# Load environment variables from .env file
load_dotenv()

# Initialize Flask application
app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY')  # Secret key from .env

# Define API Key and NewsAPI URL from .env
api_key = os.getenv('NEWS_API_KEY')
news_api_url = os.getenv('NEWS_API_URL')

zones = {
    'tech': ['technology'],
    'business': ['business'],
    'entertainment': ['entertainment'],
    'economy':  ['economy'],
    'health': ['health', 'medicine'],
    'science': ['science'],
}

# Initialize the summarization model (using T5 or PEGASUS)
summarizer = pipeline("summarization", model="t5-small")  # Change model to T5 or PEGASUS
translator = Translator()

# Function to clean unwanted text
def clean_article_content(content):
    content = re.sub(r'If you click.*will also store and/or access information.*', '', content)
    content = re.sub(r'[\n\r]+', ' ', content)  # Remove unnecessary newlines and carriage returns
    content = re.sub(r'<[^>]*>', '', content)  # Remove HTML tags (if any)
    content = re.sub(r'\[\+.?Ch.?\]', '', content)
    content = re.sub(r'\[Removed\]', '', content)
    content = re.sub(r'\[\+.?\d+ chars?\]', '', content)
    content = re.sub(r'www\.\S+', '', content)
    content = re.sub(r'\b…$', '', content)
    content = re.sub(r'[^\x00-\x7F]+', '', content)
    return content

# Function to summarize an article
def summarize_article(article, target_language='en'):
    cleaned_content = clean_article_content(article['content'])
    cleaned_content = re.sub(r'\b\d{10,}\b', '', cleaned_content)  # Remove phone numbers
    cleaned_content = re.sub(r'\b\d{3}-\d{3}-\d{4}\b', '', cleaned_content)  # Remove formatted numbers
    cleaned_content = re.sub(r'https?://\S+|www\.\S+', '', cleaned_content)  # Remove URLs
    cleaned_content = re.sub(r'\b08457 \d{2} \d{2} \d{2}\b', '', cleaned_content)  # Specific phone patterns
    
    if not cleaned_content:
        return None
    
    # Detect language of the article content and translate if needed
    detected_language = translator.detect(cleaned_content).lang
    if detected_language != target_language:
        cleaned_content = translator.translate(
            cleaned_content, src=detected_language, dest=target_language).text
    
    try:
        # Summarize the content using the T5 model, limiting the length to 5-6 lines
        summary = summarizer(cleaned_content, max_length=200, min_length=80, do_sample=False)
        return summary[0]['summary_text']
    except Exception as e:
        print(f"Error summarizing article: {e}")
        return None

# Cache articles to avoid fetching them multiple times
@lru_cache(maxsize=128)
def fetch_articles_from_newsapi(keywords, page=1):
    keywords_tuple = tuple(keywords)  # Convert list to tuple for caching
    articles = []
    for keyword in keywords_tuple:  # Use the tuple here
        params = {
            'apiKey': api_key,
            'q': keyword,
            'language': 'en',
            'page': page,
            'pageSize': 5  # Limit articles per page to 5
        }
        try:
            response = requests.get(news_api_url, params=params)
            data = response.json()
            if data.get("status") == "ok":
                for article in data.get("articles", []):
                    if article.get('content') and len(article['content']) > 100:  # Ensure content is meaningful
                        articles.append({
                            'title': article['title'],
                            'content': article.get('content', ''),
                            'url': article['url']
                        })
        except Exception as e:
            print(f"Error fetching article for keyword {keyword}: {e}")
    return articles

# Route for the home page
@app.route('/')
def home():
    session.setdefault('bookmarks', [])
    session.setdefault('history', [])
    session.setdefault('analytics', {'summaries_viewed': 0, 'bookmarks_added': 0})
    return render_template('home.html')

# Route to display summarized news with pagination
@app.route('/summarize', methods=['POST', 'GET'])
def summarize():
    zone = request.form.get('zone') or request.args.get('zone')
    language = request.form.get('language') or request.args.get('language')
    page = int(request.args.get('page', 1))  # Default to page 1 if not provided

    if not zone or not language:
        return render_template('home.html', error="Please select both a zone and a language.")
    
    # Reset summaries when zone changes
    if 'summaries' in session and zone != session.get('current_zone'):
        session['summaries'] = {}  # Reset summaries for new zone
    
    # Store the current zone in session to track changes
    session['current_zone'] = zone

    # Check if summaries for the current zone and page already exist in session
    if 'summaries' in session and session['summaries'].get(f'{zone}_page_{page}'):
        summaries = session['summaries'][f'{zone}_page_{page}']
    else:
        keywords = tuple(zones.get(zone, []))  # Convert to tuple here
        articles = fetch_articles_from_newsapi(keywords, page)
        
        summaries = []
        for article in articles:
            summary = summarize_article(article, language)
            if summary:
                summaries.append({
                    'title': article['title'],
                    'summary': summary,
                    'url': article['url']
                })
                # Track activity in session without counting duplicates
                if article['url'] not in [item['url'] for item in session['history']]:
                    session['history'].append({'title': article['title'], 'url': article['url']})
                    session['analytics']['summaries_viewed'] += 1
        
        # Store summaries in the session for the current zone and page
        if 'summaries' not in session:
            session['summaries'] = {}
        session['summaries'][f'{zone}_page_{page}'] = summaries

    session.modified = True

    next_page = page + 1  # Calculate next page number
    prev_page = page - 1 if page > 1 else 1  # Prevent going below page 1
    return render_template('summaries.html', summaries=summaries, zone=zone, language=language, next_page=next_page, prev_page=prev_page)

# Route to add a bookmark
@app.route('/bookmark', methods=['POST'])
def bookmark():
    data = request.json  # Access JSON body sent via fetch
    title = data.get('title')
    url = data.get('url')
    
    if title and url:
        # Define a maximum number of bookmarks you want to keep
        max_bookmarks = 5

        # Add bookmark to session
        if 'bookmarks' not in session:
            session['bookmarks'] = []

        # Prevent duplicates by checking if the bookmark already exists
        if url not in [bookmark['url'] for bookmark in session['bookmarks']]:
            # Check if the number of bookmarks exceeds the max limit
            if len(session['bookmarks']) >= max_bookmarks:
                # Remove the oldest bookmark (like a stack)
                session['bookmarks'].pop(0)

            # Add the new bookmark to the list
            session['bookmarks'].append({'title': title, 'url': url})
            session['analytics']['bookmarks_added'] += 1
        
        # Mark session as modified to ensure it gets saved
        session.modified = True
        app.logger.debug(f"Added bookmark: {title} - {url}")
        
    return ("", 204)  # No content response

@app.route('/analytics')
def analytics_dashboard():
    analytics = session.get('analytics', {'summaries_viewed': 0, 'bookmarks_added': 0})
    bookmarks = session.get('bookmarks', [])
    app.logger.debug(f"Bookmarks: {bookmarks}")  # Debugging log
    return render_template('analytics.html', analytics=analytics, bookmarks=bookmarks)

@app.route('/clear_bookmarks')
def clear_bookmarks():
    session.pop('bookmarks', None)  # Removes 'bookmarks' key from session
    session.pop('analytics', None)  # Removes 'analytics' key from session
    session.modified = True  # Mark session as modified
    return redirect(url_for('analytics_dashboard'))  # Redirect to analytics page or another page

@app.route('/clear_session')
def clear_session():
    session.clear()  # Clears all session data
    return redirect(url_for('home')) 

if __name__ == '__main__':
    app.run(debug=False)
