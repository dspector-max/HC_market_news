import yfinance as yf
import feedparser
from datetime import datetime
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os

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
        # Get news from Google News RSS
        url = f"https://news.google.com/rss/search?q={company_name}+{ticker}&hl=en-US&gl=US&ceid=US:en"
        feed = feedparser.parse(url)
        
        for entry in feed.entries[:3]:  # Get top 3 articles
            articles.append({
                'title': entry.title,
                'link': entry.link
            })
    except:
        pass
    return articles

def create_email_content():
    """Create the email with all the data"""
    html = f"""
    <html>
    <body style="font-family: Arial, sans-serif;">
        <h1>📈 Daily Market Update - {datetime.now().strftime('%B %d, %Y')}</h1>
    """
    
    for company in COMPANIES:
        # Get stock data
        stock = get_stock_data(company['ticker'])
        
        if stock:
            # Determine emoji
            emoji = "📈" if stock['change'] > 0 else "📉"
            color = "green" if stock['change'] > 0 else "red"
            
            html += f"""
            <h2>{emoji} {company['name']} ({company['ticker']})</h2>
            <p><strong>Price:</strong> ${stock['price']}<br>
            <strong>Change:</strong> <span style="color: {color}">${stock['change']} ({stock['change_pct']:+.2f}%)</span></p>
            """
            
            # Get news
            news = get_news(company['name'], company['ticker'])
            if news:
                html += "<p><strong>Latest News:</strong></p><ul>"
                for article in news:
                    html += f'<li><a href="{article["link"]}">{article["title"]}</a></li>'
                html += "</ul>"
            
            html += "<hr>"
    
    html += """
    </body>
    </html>
    """
    return html

def send_email(html_content):
    """Send the email"""
    # Get email settings from environment variables (GitHub will set these)
    sender = os.environ.get('EMAIL_SENDER')
    password = os.environ.get('EMAIL_PASSWORD')
    recipients = os.environ.get('EMAIL_RECIPIENTS', '').split(',')
    
    if not sender or not password:
        print("Email not configured - skipping")
        return False
    
    try:
        msg = MIMEMultipart()
        msg['Subject'] = f"Market Update - {datetime.now().strftime('%B %d')}"
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
    print("Starting market update...")
    
    # Create the email content
    html = create_email_content()
    
    # Save locally
    with open('latest_report.html', 'w') as f:
        f.write(html)
    print("Report saved to latest_report.html")
    
    # Send email
    send_email(html)
    
    print("Done!")
