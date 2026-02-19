import yfinance as yf
import feedparser
from datetime import datetime, timedelta
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
import requests
import json
import time
import sys
import pandas as pd

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

# Companies organized by sector
SECTORS = {
    'Healthcare Services': [
        {'ticker': 'UNH', 'name': 'UnitedHealth'},
        {'ticker': 'CVS', 'name': 'CVS Health'},
        {'ticker': 'CNC', 'name': 'Centene'},
        {'ticker': 'ELV', 'name': 'Elevance'},
        {'ticker': 'CI', 'name': 'Cigna'},
        {'ticker': 'MOH', 'name': 'Molina Healthcare'},
        {'ticker': 'HUM', 'name': 'Humana'},
        {'ticker': 'OSCR', 'name': 'Oscar Health'},
        {'ticker': 'DOCS', 'name': 'Doximity'},
    ],
    'Software/Tech': [
        {'ticker': 'TEM', 'name': 'Tempus AI'},
        {'ticker': 'HIMS', 'name': 'Hims & Hers'},
        {'ticker': 'HNGE', 'name': 'Hinge Health'},
        {'ticker': 'OMDA', 'name': 'Omada Health'},
        {'ticker': 'HTFL', 'name': 'HeartFlow'},
    ],
    'Life Sciences': [
        {'ticker': 'SDGR', 'name': 'Schrodinger'},
        {'ticker': 'DNA', 'name': 'Ginkgo Bioworks'},
        {'ticker': 'TWST', 'name': 'Twist Bioscience'},
        {'ticker': 'LLY', 'name': 'Eli Lilly'},
        {'ticker': 'NVO', 'name': 'Novo Nordisk'},
    ]
}

def get_stock_data_with_vwap(ticker):
    """Get stock price with VWAP comparisons"""
    try:
        stock = yf.Ticker(ticker)
        
        # Get historical data for VWAP calculations
        hist_1y = stock.history(period="1y")
        hist_6m = stock.history(period="6mo")
        hist_3m = stock.history(period="3mo")
        hist_2d = stock.history(period="2d")
        
        if len(hist_2d) < 2:
            return None
            
        # Current price data
        current = hist_2d['Close'].iloc[-1]
        previous = hist_2d['Close'].iloc[-2]
        change = current - previous
        change_pct = (change / previous) * 100
        
        # Calculate VWAPs
        def calc_vwap(hist_data):
            if len(hist_data) == 0:
                return None
            typical_price = (hist_data['High'] + hist_data['Low'] + hist_data['Close']) / 3
            vwap = (typical_price * hist_data['Volume']).sum() / hist_data['Volume'].sum()
            return vwap
        
        vwap_3m = calc_vwap(hist_3m)
        vwap_6m = calc_vwap(hist_6m)
        vwap_1y = calc_vwap(hist_1y)
        
        # Calculate deviations
        def calc_deviation(current_price, vwap):
            if vwap and vwap > 0:
                return ((current_price - vwap) / vwap) * 100
            return None
        
        return {
            'price': round(current, 2),
            'change': round(change, 2),
            'change_pct': round(change_pct, 2),
            'vwap_3m': round(vwap_3m, 2) if vwap_3m else None,
            'vwap_6m': round(vwap_6m, 2) if vwap_6m else None,
            'vwap_1y': round(vwap_1y, 2) if vwap_1y else None,
            'vwap_3m_dev': round(calc_deviation(current, vwap_3m), 1) if calc_deviation(current, vwap_3m) else None,
            'vwap_6m_dev': round(calc_deviation(current, vwap_6m), 1) if calc_deviation(current, vwap_6m) else None,
            'vwap_1y_dev': round(calc_deviation(current, vwap_1y), 1) if calc_deviation(current, vwap_1y) else None,
        }
    except Exception as e:
        print(f"Error getting stock data for {ticker}: {e}")
        return None

def get_valuation_multiples(ticker):
    """Get EV/Revenue, EV/Gross Profit, EV/EBITDA"""
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        
        # Get financials for calculations
        enterprise_value = info.get('enterpriseValue')
        
        # Try to get multiples from yfinance first
        ev_revenue = info.get('enterpriseToRevenue')
        ev_ebitda = info.get('enterpriseToEbitda')
        
        # For EV/Gross Profit, we need to calculate it
        try:
            financials = stock.financials
            if not financials.empty and 'Gross Profit' in financials.index:
                gross_profit = financials.loc['Gross Profit'].iloc[0]
                ev_gross_profit = enterprise_value / gross_profit if enterprise_value and gross_profit else None
            else:
                ev_gross_profit = None
        except:
            ev_gross_profit = None
        
        return {
            'ev_revenue': round(ev_revenue, 2) if ev_revenue else None,
            'ev_gross_profit': round(ev_gross_profit, 2) if ev_gross_profit else None,
            'ev_ebitda': round(ev_ebitda, 2) if ev_ebitda else None,
        }
    except Exception as e:
        print(f"Error getting multiples for {ticker}: {e}")
        return None

def get_upcoming_earnings(ticker):
    """Check for upcoming earnings and investor events"""
    try:
        stock = yf.Ticker(ticker)
        calendar = stock.calendar
        
        if calendar is not None and not calendar.empty:
            # Check if earnings date is in the next 7 days
            if 'Earnings Date' in calendar.index:
                earnings_dates = calendar.loc['Earnings Date']
                if not pd.isna(earnings_dates).all():
                    next_week = datetime.now() + timedelta(days=7)
                    
                    # Handle both single date and date range
                    if isinstance(earnings_dates, pd.Series):
                        for date in earnings_dates:
                            if pd.notna(date):
                                if isinstance(date, str):
                                    date = pd.to_datetime(date)
                                if date <= next_week:
                                    return date.strftime('%b %d, %Y')
                    else:
                        if isinstance(earnings_dates, str):
                            earnings_dates = pd.to_datetime(earnings_dates)
                        if earnings_dates <= next_week:
                            return earnings_dates.strftime('%b %d, %Y')
        return None
    except Exception as e:
        print(f"Error checking earnings for {ticker}: {e}")
        return None

def get_news(company_name, ticker):
    """Get news from Google News and Seeking Alpha"""
    articles = []
    seen_titles = set()
    
    print(f"\n📰 Searching news for {company_name} ({ticker})")
    
    # Google News
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
    
    # Seeking Alpha
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
    """Generate AI summary linking news to price movement"""
    api_key = os.environ.get('OPENAI_API_KEY')
    
    if not api_key:
        print(f"❌ No OpenAI API key found for {company_name}")
        return "AI summary unavailable - API key not configured"
    
    print(f"\n🔍 Generating AI summary for {company_name}:")
    print(f"   - Articles found: {len(articles)}")
    print(f"   - Stock data available: {stock_data is not None}")
    
    if not articles or (len(articles) == 1 and 'No recent news found' in articles[0]['title']):
        return f"Limited news coverage for {company_name} in recent days. Stock {'up' if stock_data and stock_data['change'] > 0 else 'down' if stock_data else 'data unavailable'}."
    
    # Build context
    news_context = f"News for {company_name} ({ticker}):\n"
    for i, article in enumerate(articles[:5], 1):
        news_context += f"\n{i}. Headline: {article['title']}"
        if article.get('summary') and article['summary'] != article['title']:
            news_context += f"\n   Details: {article['summary'][:150]}"
    
    if stock_data:
        direction = 'UP' if stock_data['change'] > 0 else 'DOWN'
        stock_context = f"\n\nStock Movement: {ticker} is {direction} ${abs(stock_data['change']):.2f} ({stock_data['change_pct']:+.1f}%) to ${stock_data['price']}"
        
        # Add VWAP context
        vwap_context = "\nVWAP Position:"
        if stock_data.get('vwap_3m_dev'):
            vwap_context += f"\n- 3M VWAP: {stock_data['vwap_3m_dev']:+.1f}%"
        if stock_data.get('vwap_6m_dev'):
            vwap_context += f"\n- 6M VWAP: {stock_data['vwap_6m_dev']:+.1f}%"
        if stock_data.get('vwap_1y_dev'):
            vwap_context += f"\n- 1Y VWAP: {stock_data['vwap_1y_dev']:+.1f}%"
    else:
        stock_context = f"\n\nStock data not available for {ticker}"
        vwap_context = ""
    
    full_context = news_context + stock_context + vwap_context
    
    print(f"   - Sending {len(full_context)} characters to OpenAI")
    
    prompt = f"""I am a healthcare-focused venture capital investor. Provide a 2-3 sentence analysis of {company_name} that SPECIFICALLY connects the news to the stock price movement.

Focus on:
1) What specific news or catalyst drove today's price movement
2) Whether the VWAP position suggests the move is part of a larger trend or an outlier
3) Any upcoming catalysts to watch

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
                    {"role": "system", "content": "You are a financial analyst who connects news catalysts to stock movements. Be specific about what drove the price change."},
                    {"role": "user", "content": prompt}
                ],
                "max_tokens": 200,
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

def create_daily_email():
    """Create daily email with significant movers by sector"""
    html = f"""
    <html>
    <body style="font-family: Arial, sans-serif; max-width: 900px; margin: 0 auto;">
        <h1 style="color: #2c3e50;">📈 Daily Market Update - {datetime.now().strftime('%B %d, %Y')}</h1>
        <p style="color: #666;">Significant movers (>3%) with AI-powered analysis</p>
        <hr>
    """
    
    total_movers = 0
    
    # Process each sector
    for sector_name, companies in SECTORS.items():
        sector_html = ""
        sector_has_movers = False
        
        for company in companies:
            print(f"Processing {company['name']} ({sector_name})...")
            
            # Get stock data with VWAP
            stock = get_stock_data_with_vwap(company['ticker'])
            
            # Skip if movement < 3%
            if not stock or abs(stock['change_pct']) < 3.0:
                print(f"   ⏭️ Skipping {company['name']} - only {abs(stock['change_pct']):.1f}% movement" if stock else "   ⏭️ No data available")
                continue
            
            sector_has_movers = True
            total_movers += 1
            
            # Get news
            news = get_news(company['name'], company['ticker'])
            
            # Build company card
            emoji = "📈" if stock['change'] > 0 else "📉"
            color = "#27ae60" if stock['change'] > 0 else "#e74c3c"
            
            sector_html += f"""
            <div style="border: 1px solid #ddd; border-radius: 8px; padding: 20px; margin: 15px 0; background: #fafafa;">
                <h3 style="color: #2c3e50; margin-top: 0;">{emoji} {company['name']} ({company['ticker']})</h3>
                
                <div style="background: white; padding: 15px; border-radius: 5px; margin-bottom: 15px;">
                    <strong>Price:</strong> ${stock['price']} 
                    <span style="color: {color}; font-weight: bold; margin-left: 20px;">
                        {'+' if stock['change'] > 0 else ''}{stock['change']} ({stock['change_pct']:+.2f}%)
                    </span>
                </div>
                
                <div style="background: #f8f9fa; padding: 12px; border-radius: 5px; margin-bottom: 15px;">
                    <strong>📊 VWAP Position:</strong><br>
                    <table style="width: 100%; margin-top: 8px; font-size: 14px;">
                        <tr>
                            <td>3-Month:</td>
                            <td style="font-weight: bold; color: {'#27ae60' if stock.get('vwap_3m_dev', 0) > 0 else '#e74c3c'};">
                                {stock.get('vwap_3m_dev', 'N/A'):+.1f}% {'above' if stock.get('vwap_3m_dev', 0) > 0 else 'below'} VWAP
                                {' 🔥' if abs(stock.get('vwap_3m_dev', 0)) > 10 else ''}
                            </td>
                        </tr>
                        <tr>
                            <td>6-Month:</td>
                            <td style="font-weight: bold; color: {'#27ae60' if stock.get('vwap_6m_dev', 0) > 0 else '#e74c3c'};">
                                {stock.get('vwap_6m_dev', 'N/A'):+.1f}% {'above' if stock.get('vwap_6m_dev', 0) > 0 else 'below'} VWAP
                                {' 🔥' if abs(stock.get('vwap_6m_dev', 0)) > 10 else ''}
                            </td>
                        </tr>
                        <tr>
                            <td>1-Year:</td>
                            <td style="font-weight: bold; color: {'#27ae60' if stock.get('vwap_1y_dev', 0) > 0 else '#e74c3c'};">
                                {stock.get('vwap_1y_dev', 'N/A'):+.1f}% {'above' if stock.get('vwap_1y_dev', 0) > 0 else 'below'} VWAP
                                {' 🔥' if abs(stock.get('vwap_1y_dev', 0)) > 10 else ''}
                            </td>
                        </tr>
                    </table>
                </div>
            """
            
            # Get AI summary
            ai_summary = get_ai_summary(company['name'], company['ticker'], news, stock)
            
            if ai_summary:
                sector_html += f"""
                <div style="background: #e8f4f8; padding: 15px; border-radius: 5px; margin-bottom: 15px; border-left: 4px solid #3498db;">
                    <strong>🤖 AI Analysis:</strong><br>
                    <em style="color: #2c3e50; line-height: 1.5;">{ai_summary}</em>
                </div>
                """
            
            # Show news headlines
            if news and len(news) > 0:
                sector_html += "<div><strong>📰 Latest Headlines:</strong><ul style='margin-top: 10px;'>"
                for article in news[:3]:
                    sector_html += f'<li style="margin: 5px 0;"><a href="{article["link"]}" style="color: #0066cc; text-decoration: none;">{article["title"]}</a></li>'
                sector_html += "</ul></div>"
            
            sector_html += "</div>"
            
            # Small delay to avoid rate limiting
            time.sleep(0.5)
        
        # Add sector header and content if there were movers
        if sector_has_movers:
            html += f"""
            <div style="margin: 30px 0;">
                <h2 style="color: #3498db; border-bottom: 3px solid #3498db; padding-bottom: 10px;">
                    {sector_name}
                </h2>
                {sector_html}
            </div>
            """
    
    if total_movers == 0:
        html += """
        <div style="text-align: center; padding: 40px; background: #f8f9fa; border-radius: 8px;">
            <h3 style="color: #666;">📊 Quiet Day</h3>
            <p style="color: #888;">No significant moves (>3%) across monitored companies today.</p>
        </div>
        """
    
    html += """
    <hr style="margin-top: 30px;">
    <p style="font-size: 12px; color: #888; text-align: center;">
        Powered by OpenAI GPT-3.5 • Generated automatically via GitHub Actions<br>
        🔥 indicates >10% deviation from VWAP
    </p>
    </body>
    </html>
    """
    return html

def create_weekly_email():
    """Create Monday email with valuation multiples and upcoming events"""
    html = f"""
    <html>
    <body style="font-family: Arial, sans-serif; max-width: 900px; margin: 0 auto;">
        <h1 style="color: #2c3e50;">📊 Weekly Valuation Dashboard - {datetime.now().strftime('%B %d, %Y')}</h1>
        <p style="color: #666;">Key multiples and upcoming events</p>
        <hr>
    """
    
    # Process each sector
    for sector_name, companies in SECTORS.items():
        html += f"""
        <div style="margin: 30px 0;">
            <h2 style="color: #3498db; border-bottom: 3px solid #3498db; padding-bottom: 10px;">
                {sector_name}
            </h2>
            <table style="width: 100%; border-collapse: collapse; margin-top: 15px; background: white;">
                <thead>
                    <tr style="background: #f8f9fa; border-bottom: 2px solid #ddd;">
                        <th style="padding: 12px; text-align: left; border: 1px solid #ddd;">Company</th>
                        <th style="padding: 12px; text-align: center; border: 1px solid #ddd;">EV/Revenue</th>
                        <th style="padding: 12px; text-align: center; border: 1px solid #ddd;">EV/Gross Profit</th>
                        <th style="padding: 12px; text-align: center; border: 1px solid #ddd;">EV/EBITDA</th>
                        <th style="padding: 12px; text-align: left; border: 1px solid #ddd;">Upcoming Events</th>
                    </tr>
                </thead>
                <tbody>
        """
        
        for company in companies:
            print(f"Getting multiples for {company['name']}...")
            
            multiples = get_valuation_multiples(company['ticker'])
            earnings = get_upcoming_earnings(company['ticker'])
            
            html += f"""
                    <tr style="border-bottom: 1px solid #ddd;">
                        <td style="padding: 12px; border: 1px solid #ddd;"><strong>{company['name']}</strong><br><span style="color: #666; font-size: 12px;">{company['ticker']}</span></td>
                        <td style="padding: 12px; text-align: center; border: 1px solid #ddd;">{multiples['ev_revenue'] if multiples and multiples['ev_revenue'] else 'N/A'}</td>
                        <td style="padding: 12px; text-align: center; border: 1px solid #ddd;">{multiples['ev_gross_profit'] if multiples and multiples['ev_gross_profit'] else 'N/A'}</td>
                        <td style="padding: 12px; text-align: center; border: 1px solid #ddd;">{multiples['ev_ebitda'] if multiples and multiples['ev_ebitda'] else 'N/A'}</td>
                        <td style="padding: 12px; border: 1px solid #ddd;">{'📅 Earnings: ' + earnings if earnings else 'None scheduled'}</td>
                    </tr>
            """
            
            time.sleep(0.3)  # Rate limiting
        
        html += """
                </tbody>
            </table>
        </div>
        """
    
    html += """
    <hr style="margin-top: 30px;">
    <p style="font-size: 12px; color: #888; text-align: center;">
        Generated automatically via GitHub Actions<br>
        Multiples data from Yahoo Finance • Earnings dates subject to change
    </p>
    </body>
    </html>
    """
    return html

def send_email(html_content, subject):
    """Send the email"""
    sender = os.environ.get('EMAIL_SENDER')
    password = os.environ.get('EMAIL_PASSWORD')
    recipients = os.environ.get('EMAIL_RECIPIENTS', '').split(',')
    
    if not sender or not password:
        print("Email not configured - skipping")
        return False
    
    try:
        msg = MIMEMultipart()
        msg['Subject'] = subject
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
    today = datetime.now()
    
    # Check if weekend
    if today.weekday() >= 5:
        print(f"🚫 Skipping - Today is {today.strftime('%A')} (weekend)")
        print("Market updates only run on weekdays.")
        sys.exit(0)
    
    print(f"Starting market update for {today.strftime('%A, %B %d, %Y')}...")
    
    # Check for API key
    if not os.environ.get('OPENAI_API_KEY'):
        print("⚠️  Warning: OPENAI_API_KEY not set - AI summaries will be skipped")
    
    # Monday = Weekly multiples email
    if today.weekday() == 0:  # 0 = Monday
        print("📊 Generating WEEKLY multiples email...")
        html = create_weekly_email()
        subject = f"Weekly Valuation Dashboard - {today.strftime('%B %d')}"
        filename = 'weekly_multiples.html'
    else:
        # Tuesday-Friday = Daily movers email
        print("📈 Generating DAILY movers email...")
        html = create_daily_email()
        subject = f"Daily Market Update - {today.strftime('%B %d')}"
        filename = 'latest_report.html'
    
    # Save locally
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"Report saved to {filename}")
    
    # Send email
    send_email(html, subject)
    
    print("Done!")
