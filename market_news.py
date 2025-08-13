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

# Your companies to track
COMPANIES = [
    {'ticker': 'HIMS', 'name': 'Hims & Hers'},
    {'ticker': 'HNGE', 'name': 'Hinge Health'},
    {'ticker': 'OMDA', 'name': 'Omada Health'},
    {'ticker': 'HTFL', 'name': 'HeartFlow'},
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
    """Get latest news - try multiple search strategies"""
    articles = []
    
    # Try different search combinations
    search_terms = [
        f"{company_name} {ticker}",
        f"{company_name}",
        f"{ticker} stock",
        f"{company_name} news"
    ]
    
    for search_term in search_terms:
        if len(articles) >= 3:  # Stop if we have enough articles
            break
            
        try:
            url = f"https://news.google.com/rss/search?q={search_term}&hl=en-US&gl=US&ceid=US:en"
            feed = feedparser.parse(url)
            
            for entry in feed.entries[:5]:
                # Avoid duplicates
                if not any(article['title'] == entry.title for article in articles):
                    articles.append({
                        'title': entry.title,
                        'link': entry.link,
                        'summary': entry.get('summary', '')[:200]
                    })
        except Exception as e:
            print(f"Error searching for {search_term}: {e}")
    
    if not articles:
        print(f"No news found for {company_name} ({ticker}) after trying multiple searches")
    
    return articles[:5]  # Return top 5 unique articles

def get_ai_summary(company_name, ticker, articles, stock_data):
    """Generate AI summary using OpenAI with better context"""
    api_key = os.environ.get('OPENAI_API_KEY')
    
    if not api_key:
        print("No OpenAI API key found")
        return None
    
    if not articles:
        return f"No recent news found for {company_name}."
    
    # Build detailed context
    news_context = "Recent news:\n"
    for i, article in enumerate(articles[:5], 1):
        news_context += f"{i}. {article['title']}\n"
        if article.get('summary'):
            news_context += f"   Context: {article['summary']}\n"
    
    if stock_data:
        stock_context = f"\nStock Performance: {'UP' if stock_data['change'] > 0 else 'DOWN'} {abs(stock_data['change_pct']):.1f}% at ${stock_data['price']}."
    else:
        stock_context = ""
    
    prompt = f"""You are a financial analyst. Based on today's news and stock performance for {company_name} ({ticker}), 
provide a 2-3 sentence analysis that explains WHY the stock might be moving and what investors should know.
Be specific about {company_name}'s business, products, or recent events.

{news_context}
{stock_context}

Provide a brief, specific analysis about {company_name}:"""
    
    try:
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": "gpt-3.5-turbo",
                "messages": [
                    {"role": "system", "content": f"You are a concise financial analyst specializing in tech stocks. Always mention specific details about {company_name}'s products, leadership, or recent announcements when analyzing the news."},
                    {"role": "user", "content": prompt}
                ],
                "max_tokens": 150,
                "temperature": 0.7
            },
            timeout=10
        )
        
        if response.status_code == 200:
            summary = response.json()['choices'][0]['message']['content'].strip()
            print(f"✅ AI summary generated for {company_name}")
            return summary
        else:
            print(f"AI API error for {company_name}: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        print(f"AI summary error for {company_name}: {e}")
        return None

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
