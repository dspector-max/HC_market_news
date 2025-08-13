import yfinance as yf
import feedparser
from datetime import datetime
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
import requests
import json

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
    except:
        return None

def get_news(company_name, ticker):
    """Get latest news"""
    articles = []
    try:
        url = f"https://news.google.com/rss/search?q={company_name}+{ticker}&hl=en-US&gl=US&ceid=US:en"
        feed = feedparser.parse(url)
        
        for entry in feed.entries[:5]:  # Get top 5 articles
            articles.append({
                'title': entry.title,
                'link': entry.link
            })
    except:
        pass
    return articles

def get_ai_summary(company_name, ticker, articles, stock_data):
    """Generate AI summary using OpenAI"""
    api_key = os.environ.get('OPENAI_API_KEY')
    
    if not api_key:
        return None
    
    # Prepare context for AI
    news_titles = "\n".join([f"- {article['title']}" for article in articles[:5]])
    
    if stock_data:
        stock_context = f"Stock is {'up' if stock_data['change'] > 0 else 'down'} {abs(stock_data['change_pct']):.1f}% today at ${stock_data['price']}."
    else:
        stock_context = "Stock data unavailable."
    
    prompt = f"""Based on these recent headlines about {company_name} ({ticker}) and today's stock performance, 
provide a 2-3 sentence summary of the key developments and market sentiment.

{stock_context}

Recent headlines:
{news_titles}

Summary:"""
    
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
                    {"role": "system", "content": "You are a concise financial analyst. Provide brief, insightful market summaries."},
                    {"role": "user", "content": prompt}
                ],
                "max_tokens": 100,
                "temperature": 0.7
            }
        )
        
        if response.status_code == 200:
            return response.json()['choices'][0]['message']['content'].strip()
        else:
            print(f"AI API error: {response.status_code}")
            return None
    except Exception as e:
        print(f"AI summary error: {e}")
        return None

def create_email_content():
    """Create the email with all the data"""
    html = f"""
    <html>
    <body style="font-family: Arial, sans-serif;">
        <h1>📈 Daily Market Update - {datetime.now().strftime('%B %d, %Y')}</h1>
        <p style="color: #666;">AI-powered summaries of today's market movements and news</p>
    """
    
    for company in COMPANIES:
        # Get stock data
        stock = get_stock_data(company['ticker'])
        
        if stock:
            # Determine emoji and color
            emoji = "📈" if stock['change'] > 0 else "📉"
            color = "green" if stock['change'] > 0 else "red"
            
            html += f"""
            <div style="border: 1px solid #ddd; border-radius: 8px; padding: 15px; margin: 20px 0;">
                <h2>{emoji} {company['name']} ({company['ticker']})</h2>
                <p><strong>Price:</strong> ${stock['price']}<br>
                <strong>Change:</strong> <span style="color: {color}">${stock['change']} ({stock['change_pct']:+.2f}%)</span></p>
            """
            
            # Get news
            news = get_news(company['name'], company['ticker'])
            
            # Get AI summary
            ai_summary = get_ai_summary(company['name'], company['ticker'], news, stock)
            
            if ai_summary:
                html += f"""
                <div style="background: #f0f8ff; padding: 10px; border-radius: 5px; margin: 10px 0;">
                    <strong>🤖 AI Summary:</strong><br>
                    <em>{ai_summary}</em>
                </div>
                """
            
            if news:
                html += "<p><strong>📰 Latest Headlines:</strong></p><ul>"
                for article in news[:3]:
                    html += f'<li><a href="{article["link"]}" style="color: #0066cc;">{article["title"]}</a></li>'
                html += "</ul>"
            
            html += "</div>"
    
    html += """
    <hr style="margin-top: 30px;">
    <p style="font-size: 12px; color: #888;">
        Powered by OpenAI GPT-3.5 • <a href="https://github.com/yourusername/market-news">View on GitHub</a>
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
        msg['Subject'] = f"Market Update with AI Insights - {datetime.now().strftime('%B %d')}"
        msg['From'] = sender
        msg['To'] = ', '.join(recipients)
        
        msg.attach(MIMEText(html_content, 'html'))
        
        with smtplib.SMTP('smtp.gmail.com', 587) as server:
            server.starttls()
            server.login(sender, password)
            server.send_message(msg)
        
        print("✅ Email sent!")
        return True
    except Exception as e:
        print(f"❌ Email failed: {e}")
        return False

# Main execution
if __name__ == "__main__":
    print("Starting market update with AI summaries...")
    
    # Create the email content
    html = create_email_content()
    
    # Save locally
    with open('latest_report.html', 'w') as f:
        f.write(html)
    print("Report saved to latest_report.html")
    
    # Send email
    send_email(html)
    
    print("Done!")
