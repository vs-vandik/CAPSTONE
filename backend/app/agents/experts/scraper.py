"""Expert data scraper - automates gathering of expert information."""

from typing import List, Dict, Optional
from dataclasses import dataclass
import json
import os


@dataclass
class ScrapedData:
    """Container for scraped expert data."""
    source: str
    content: str
    url: str
    date: str
    relevance_score: float = 0.0


class ExpertScraper:
    """
    Base class for scraping expert data from the web.
    
    Note: Due to Twitter's API restrictions, we use multiple sources:
    - Search engines (SerpAPI)
    - YouTube transcripts
    - News articles
    - Public interviews
    """
    
    def __init__(self, expert_name: str):
        self.expert_name = expert_name
        self.data_dir = f"./data/{expert_name.lower().replace(' ', '_')}"
        os.makedirs(self.data_dir, exist_ok=True)
    
    async def scrape(self, query: str, max_results: int = 10) -> List[ScrapedData]:
        """
        Scrape the web for information about the expert.
        
        Args:
            query: Search query
            max_results: Maximum number of results
            
        Returns:
            List of ScrapedData objects
        """
        raise NotImplementedError("Subclasses must implement scrape()")
    
    def save_to_knowledge_base(self, data: List[ScrapedData]):
        """Save scraped data to knowledge base."""
        for item in data:
            filename = f"{self.data_dir}/{item.source}_{item.date}.txt"
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(f"Source: {item.url}\n")
                f.write(f"Date: {item.date}\n")
                f.write(f"Relevance: {item.relevance_score}\n")
                f.write("---\n")
                f.write(item.content)
    
    def load_from_knowledge_base(self) -> List[ScrapedData]:
        """Load previously scraped data."""
        data = []
        if not os.path.exists(self.data_dir):
            return data
        
        for filename in os.listdir(self.data_dir):
            if filename.endswith('.txt'):
                filepath = os.path.join(self.data_dir, filename)
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                    # Parse the saved format
                    parts = content.split("---")
                    if len(parts) >= 2:
                        header = parts[0]
                        body = parts[1]
                        source = "unknown"
                        url = "unknown"
                        date = "unknown"
                        for line in header.split('\n'):
                            if line.startswith("Source:"):
                                url = line.replace("Source:", "").strip()
                            elif line.startswith("Date:"):
                                date = line.replace("Date:", "").strip()
                        data.append(ScrapedData(
                            source=source,
                            content=body.strip(),
                            url=url,
                            date=date
                        ))
        return data


class ElonMuskScraper(ExpertScraper):
    """Scraper specifically configured for Elon Musk."""
    
    def __init__(self):
        super().__init__("Elon Musk")
        self.search_queries = [
            "Elon Musk decision making process",
            "Elon Musk first principles thinking",
            "Elon Musk interview 2024 2025",
            "Elon Musk Tesla earnings call",
            "Elon Musk SpaceX strategy"
        ]
    
    async def scrape(self, query: str = None, max_results: int = 10) -> List[ScrapedData]:
        """
        Scrape web for Elon Musk data.
        
        Uses multiple sources to build comprehensive profile.
        """
        results = []
        
        # Use predefined queries if no specific query
        queries = [query] if query else self.search_queries
        
        for q in queries[:3]:  # Limit to avoid rate limits
            try:
                # In production, this would call:
                # - SerpAPI for search results
                # - YouTube API for transcripts
                # - News API for articles
                
                # For now, we create a placeholder that shows the structure
                scraped = await self._scrape_query(q, max_results)
                results.extend(scraped)
            except Exception as e:
                print(f"Error scraping '{q}': {e}")
        
        return results
    
    async def _scrape_query(self, query: str, max_results: int) -> List[ScrapedData]:
        """
        Internal method to scrape a single query.
        
        In production, this would integrate with:
        - SerpAPI: for Google search results
        - YouTube API: for interview transcripts
        - NewsAPI: for recent articles
        """
        # Placeholder - shows the structure
        # Real implementation would call external APIs
        
        return [
            ScrapedData(
                source="search",
                content=f"Scraped data for query: {query}",
                url=f"https://example.com/search?q={query}",
                date="2025-01-01",
                relevance_score=0.8
            )
        ]
    
    def generate_voice_profile(self, data: List[ScrapedData]) -> Dict:
        """
        Analyze scraped data to generate voice profile.
        
        This creates the Soul Document automatically from scraped data.
        """
        # Keywords to look for
        vocabulary_markers = [
            "first principles", "paradigm shift", "obvious",
            "fail fast", "move fast", "solve",
            "engineer", "physics", "math"
        ]
        
        speaking_patterns = []
        phrases_to_use = []
        phrases_to_avoid = []
        
        # Analyze each piece of data
        for item in data:
            content_lower = item.content.lower()
            
            # Find vocabulary markers
            for marker in vocabulary_markers:
                if marker in content_lower:
                    speaking_patterns.append(marker)
        
        # Generate profile
        profile = {
            "expert": "Elon Musk",
            "bio": "CEO of SpaceX, Tesla, xAI, owner of X",
            "speaking_style": {
                "sentence_structure": "Short, declarative sentences",
                "tone": "High energy, confident, challenging",
                "metaphors": "Engineering and physics metaphors"
            },
            "vocabulary_markers": list(set(speaking_patterns)),
            "phrases_to_use": [
                "The solution is obvious when you think about it from first principles",
                "Most people think about this wrong",
                "We're going to need to think about this differently"
            ],
            "phrases_to_avoid": [
                "I believe",
                "Perhaps",
                "Maybe"
            ],
            "data_sources": len(data)
        }
        
        return profile


# Factory function to get scraper for any expert
def get_expert_scraper(expert_name: str) -> ExpertScraper:
    """Get the appropriate scraper for an expert."""
    scrapers = {
        "Elon Musk": ElonMuskScraper,
        # Add more scrapers here
    }
    
    scraper_class = scrapers.get(expert_name, ExpertScraper)
    return scraper_class()


async def scrape_expert(expert_name: str, query: str = None) -> Dict:
    """
    Main function to scrape an expert's data and generate voice profile.
    
    Args:
        expert_name: Name of the expert to scrape
        query: Optional specific query
        
    Returns:
        Dict with scraped data and generated voice profile
    """
    scraper = get_expert_scraper(expert_name)
    
    # Scrape data
    data = await scraper.scrape(query)
    
    # Save to knowledge base
    scraper.save_to_knowledge_base(data)
    
    # Generate voice profile
    if isinstance(scraper, ElonMuskScraper):
        profile = scraper.generate_voice_profile(data)
    else:
        profile = {"expert": expert_name, "data_sources": len(data)}
    
    return {
        "expert": expert_name,
        "scraped_items": len(data),
        "voice_profile": profile,
        "data_saved_to": scraper.data_dir
    }