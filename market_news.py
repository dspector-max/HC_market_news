import yfinance as yf
import feedparser
from datetime import datetime
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
import requests
import json
import time
import sys

# Debug: Check if secrets are loading
print("=" * 50)
print("CHECKING ENVIRONMENT VARIABLES:")
print(f"EMAIL_SENDER exists: {bool(os.environ.get('EMAIL_SENDER'))}")
print(f"EMAIL_PASSWORD exists: {bool(os.environ.get('EMAIL_PASSWORD'))}")
print(f"OPENAI_API_KEY exists: {bool(os.environ.get('OPENAI_API_KEY'))}")
if os.environ.get('OPENAI_API_KEY'):
    key = os.environ.get('OPENAI_API_KEY')
    print(f"OPENAI_API_KEY starts with: {key[:7]}...")
print("=" * 50)

# Your companies to track
COMPANIES = [
    {'ticker': 'HIMS', 'name': 'Hims & Hers'},
    {'ticker': 'HNGE', 'name': 'Hinge Health'},
    {'ticker': 'OMDA', 'name': 'Omada Health'},
    {'ticker': 'HTFL', 'name': 'HeartFlow'},
    {'ticker': 'DOCS', 'name': 'Doximity'},
    {'ticker': 'OSCR', 'name': 'Oscar Health'},
    {'ticker': 'UNH', 'name': 'UnitedHealth'},
    {'ticker': 'CVS', 'name': 'CVS Health'},
    {'ticker': 'CNC', 'name': 'Centene'},
    {'ticker': 'ELV', 'name': 'Elevance'},
    {'ticker': 'CI', 'name': 'Cigna'},
    {'ticker': 'TEM', 'name': 'Tempus AI'},
    {'ticker': 'SDGR', 'name': 'Schrodinger'},
    {'ticker': 'DNA', 'name': 'Ginkgo Bioworks'},
    {'ticker': 'TWST', 'name': 'Twist Bioscience'},
    {'ticker': 'ABCL', 'name': 'AbCellera Biologics'},
]

def get_stock_data(ticker):
    """Get today's stock price"""
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period="2d")
        if len(hist) >= 2:
            current = hist['Close'].iloc[-1]
            previous = hist['Close'].iloc[-2]
            change = current - previous
            change_pct = (change / previous) * 100
            return {
                'price': round(current, 2),
                'change': round(change, 2),
                'change_pct': round(change_pct, 2)
            }
    except Exception as e:
        print(f"Error getting stock data for {ticker}: {e}")
        return None

def get_news(company_name, ticker):
    """Get news from Google News and Seeking Alpha - company specific"""
    articles = []
    seen_titles = set()
    
    print(f"\n📰 Searching news for {company_name} ({ticker})")
    
    # 1. GOOGLE NEWS - Single search
    try:
        url = f"https://news.google.com/rss/search?q={company_name}+OR+{ticker}&hl=en-US&gl=US&ceid=US:en"
        feed = feedparser.parse(url)
        
        for entry in feed.entries[:10]:
            title = entry.title
            if title not in seen_titles:
                seen_titles.add(title)
                articles.append({
                    'title': title,
                    'link': entry.link,
                    'source': 'Google News',
                    'date': entry.get('published', 'Recent'),
                    'summary': entry.get('summary', '')[:200]
                })
    except Exception as e:
        print(f"   Error with Google News: {e}")
    
    # 2. SEEKING ALPHA - Single search
    try:
        url = f"https://seekingalpha.com/api/sa/combined/{ticker}.xml"
        feed = feedparser.parse(url)
        
        for entry in feed.entries[:10]:
            title = entry.title
            if title not in seen_titles:
                seen_titles.add(title)
                articles.append({
                    'title': title,
                    'link': entry.link,
                    'source': 'Seeking Alpha',
                    'date': entry.get('published', 'Recent'),
                    'summary': entry.get('summary', '')[:200]
                })
    except Exception as e:
        print(f"   Seeking Alpha not available for {ticker}")
    
    print(f"   Found {len(articles)} articles")
    
    if not articles:
        articles = [{
            'title': f'No recent news found for {company_name}',
            'link': '#',
            'source': 'N/A',
            'summary': 'No recent coverage found.'
        }]
    
    return articles[:5]

def get_ai_summary(company_name, ticker, articles, stock_data):
    """Generate AI summary using OpenAI with better debugging"""
    api_key = os.environ.get('OPENAI_API_KEY')
    
    if not api_key:
        print(f"❌ No OpenAI API key found for {company_name}")
        return "AI summary unavailable - API key not configured"
    
    # Debug: Show what we're working with
    print(f"\n🔍 Generating AI summary for {company_name}:")
    print(f"   - Articles found: {len(articles)}")
    print(f"   - Stock data available: {stock_data is not None}")
    
    if not articles or (len(articles) == 1 and 'No recent news found' in articles[0]['title']):
        return f"Limited news coverage for {company_name} in recent days. Stock {'up' if stock_data and stock_data['change'] > 0 else 'down' if stock_data else 'data unavailable'}."
    
    # Build detailed context - include everything we have
    news_context = f"News for {company_name} ({ticker}):\n"
    for i, article in enumerate(articles[:5], 1):
        news_context += f"\n{i}. Headline: {article['title']}"
        if article.get('summary') and article['summary'] != article['title']:
            news_context += f"\n   Details: {article['summary'][:150]}"
    
    if stock_data:
        direction = 'UP' if stock_data['change'] > 0 else 'DOWN'
        stock_context = f"\n\nStock Movement: {ticker} is {direction} ${abs(stock_data['change']):.2f} ({stock_data['change_pct']:+.1f}%) to ${stock_data['price']}"
    else:
        stock_context = f"\n\nStock data not available for {ticker}"
    
    full_context = news_context + stock_context
    
    # Debug: Show what we're sending to AI
    print(f"   - Sending {len(full_context)} characters to OpenAI")
    
    prompt = f"""I am a healthcare-focused venture capital investor with investments in similar companies, provide a 2-3 sentence analysis of {company_name} based on the following information.
Focus on: 1) What has happened in the last 24-hours that has driven any changes in the share price or market perception, 2) Any notable business developments or earnings releases, 3) any upcoming events / earnings reports to watch.
Be specific about {company_name}'s business and market position.

{full_context}

Provide your analysis:"""
    
    try:
        print(f"   - Calling OpenAI API...")
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": "gpt-3.5-turbo",
                "messages": [
                    {"role": "system", "content": "You are a concise financial analyst. Provide specific, actionable insights about the company based on the provided context."},
                    {"role": "user", "content": prompt}
                ],
                "max_tokens": 150,
                "temperature": 0.7
            },
            timeout=15
        )
        
        if response.status_code == 200:
            summary = response.json()['choices'][0]['message']['content'].strip()
            print(f"   ✅ AI summary generated successfully")
            return summary
        else:
            error_msg = f"API error {response.status_code}: {response.text[:200]}"
            print(f"   ❌ {error_msg}")
            return f"AI analysis temporarily unavailable (API error {response.status_code})"
            
    except requests.exceptions.Timeout:
        print(f"   ❌ OpenAI API timeout for {company_name}")
        return "AI analysis timed out - trying again next run"
    except Exception as e:
        print(f"   ❌ Error: {str(e)}")
        return f"AI analysis error: {str(e)[:100]}"

def create_email_content():
    """Create the email with all the data"""
    html = f"""
    <html>
    <body style="font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto;">
        <h1 style="color: #2c3e50;">📈 Daily Market Update - {datetime.now().strftime('%B %d, %Y')}</h1>
        <p style="color: #666;">AI-powered analysis of today's market movements</p>
        <hr>
    """
    
    for company in COMPANIES:
        print(f"Processing {company['name']}...")
        
        # Get stock data
        stock = get_stock_data(company['ticker'])

         # ADD THIS LINE - skip if movement < 2%
        if stock and abs(stock['change_pct']) < 2.0:
            print(f"   ⏭️ Skipping {company['name']} - only {abs(stock['change_pct']):.1f}% movement")
            continue
        
        # Get news FIRST (before using it)
        news = get_news(company['name'], company['ticker'])
        
        # Now build the HTML
        if stock:
            # Determine emoji and color
            emoji = "📈" if stock['change'] > 0 else "📉"
            color = "#27ae60" if stock['change'] > 0 else "#e74c3c"
            
            html += f"""
            <div style="border: 1px solid #ddd; border-radius: 8px; padding: 20px; margin: 20px 0; background: #fafafa;">
                <h2 style="color: #2c3e50; margin-top: 0;">{emoji} {company['name']} ({company['ticker']})</h2>
                
                <div style="background: white; padding: 15px; border-radius: 5px; margin-bottom: 15px;">
                    <strong>Price:</strong> ${stock['price']} 
                    <span style="color: {color}; font-weight: bold; margin-left: 20px;">
                        {'+' if stock['change'] > 0 else ''}{stock['change']} ({stock['change_pct']:+.2f}%)
                    </span>
                </div>
            """
            
            # Get AI summary (with news context)
            ai_summary = get_ai_summary(company['name'], company['ticker'], news, stock)
            
            if ai_summary:
                html += f"""
                <div style="background: #e8f4f8; padding: 15px; border-radius: 5px; margin-bottom: 15px; border-left: 4px solid #3498db;">
                    <strong>🤖 AI Analysis:</strong><br>
                    <em style="color: #2c3e50; line-height: 1.5;">{ai_summary}</em>
                </div>
                """
            
            # Show news headlines
            if news and len(news) > 0:
                html += "<div><strong>📰 Latest Headlines:</strong><ul style='margin-top: 10px;'>"
                for article in news[:3]:  # Show top 3 headlines
                    html += f'<li style="margin: 5px 0;"><a href="{article["link"]}" style="color: #0066cc; text-decoration: none;">{article["title"]}</a></li>'
                html += "</ul></div>"
            else:
                html += "<p><em>No recent news found</em></p>"
            
            html += "</div>"
        
        # Small delay to avoid rate limiting
        time.sleep(0.5)
    
    html += """
    <hr style="margin-top: 30px;">
    <p style="font-size: 12px; color: #888; text-align: center;">
        Powered by OpenAI GPT-3.5 • Generated automatically via GitHub Actions
    </p>
    </body>
    </html>
    """
    return html

def send_email(html_content):
    """Send the email"""
    sender = os.environ.get('EMAIL_SENDER')
    password = os.environ.get('EMAIL_PASSWORD')
    recipients = os.environ.get('EMAIL_RECIPIENTS', '').split(',')
    
    if not sender or not password:
        print("Email not configured - skipping")
        return False
    
    try:
        msg = MIMEMultipart()
        msg['Subject'] = f"Market Update with AI Analysis - {datetime.now().strftime('%B %d')}"
        msg['From'] = sender
        msg['To'] = ', '.join(recipients)
        
        msg.attach(MIMEText(html_content, 'html'))
        
        with smtplib.SMTP('smtp.gmail.com', 587) as server:
            server.starttls()
            server.login(sender, password)
            server.send_message(msg)
        
        print("✅ Email sent successfully!")
        return True
    except Exception as e:
        print(f"❌ Email failed: {e}")
        return False

# Main execution
if __name__ == "__main__":
    # CHECK IF IT'S A WEEKDAY - ADD THESE 5 LINES
    today = datetime.now()
    if today.weekday() >= 5:  # 5=Saturday, 6=Sunday
        print(f"🚫 Skipping - Today is {today.strftime('%A')} (weekend)")
        print("Market updates only run on weekdays.")
        sys.exit(0)
        
    print("Starting market update with AI analysis...")
    print(f"Time: {datetime.now()}")
    
    # Check for API key
    if not os.environ.get('OPENAI_API_KEY'):
        print("⚠️  Warning: OPENAI_API_KEY not set - AI summaries will be skipped")
    
    # Create the email content
    html = create_email_content()
    
    # Save locally
    with open('latest_report.html', 'w', encoding='utf-8') as f:
        f.write(html)
    print("Report saved to latest_report.html")
    
    # Send email
    send_email(html)
    
    print("Done!")
