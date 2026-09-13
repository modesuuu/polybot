import requests
import json
from datetime import datetime

class LLMNewsOracle:
    def __init__(self):
        # Memakai RSS feed/News API gratis
        self.news_url = "https://min-api.cryptocompare.com/data/v2/news/?lang=EN"
        
    def fetch_latest_news(self):
        try:
            res = requests.get(self.news_url, timeout=5)
            data = res.json().get('Data', [])
            headlines = [item['title'] for item in data[:5]]
            return headlines
        except Exception:
            return []

    def get_sentiment_score(self):
        """
        Mengambil berita & menganalisa kata kunci (Bisa disambung ke Hermes AI)
        Return score -1.0 (Very Bearish) s/d 1.0 (Very Bullish)
        """
        headlines = self.fetch_latest_news()
        if not headlines:
            return 0.0 # Netral
            
        bullish_words = ['bull', 'surge', 'high', 'gain', 'support', 'etf', 'buy']
        bearish_words = ['bear', 'drop', 'low', 'crash', 'ban', 'sec', 'sell']
        
        score = 0.0
        for h in headlines:
            h_lower = h.lower()
            for w in bullish_words:
                if w in h_lower: score += 0.2
            for w in bearish_words:
                if w in h_lower: score -= 0.2
                
        # Clamp score between -1.0 and 1.0
        final_score = max(-1.0, min(1.0, score))
        print(f"[{datetime.now()}] [NEWS ORACLE] Sentimen Pasar: {final_score:.2f} dari {len(headlines)} Berita")
        return final_score

news_oracle = LLMNewsOracle()
