"""
AI-Powered Recruiter Search Query Generator.
Uses Gemini API to create diverse search queries.
"""
import random
from typing import List, Optional
import warnings

# Suppress Google GenAI deprecation warnings
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)

try:
    import google.generativeai as genai
except ImportError:
    genai = None

from config import config


class RecruiterSearchGenerator:
    """Generates diverse recruiter search queries using AI."""
    
    # Fallback queries focused on US, Canada, Australia
    FALLBACK_QUERIES = [
        ("Senior Technical Recruiter", "United States"),
        ("Tech Talent Acquisition", "United States"),
        ("IT Recruitment Consultant", "Canada"),
        ("Software Engineer Recruiter", "Australia"),
        ("Talent Acquisition Manager", "United States"),
        ("Staffing Consultant IT", "United States"),
        ("Talent Acquisition Specialist", "Canada"),
        ("Recruitment Manager Tech", "Australia"),
        ("Engineering Recruiter", "United States"),
        ("Developer Recruiter", "United States"),
        ("Cloud Technology Recruiter", "Canada"),
        ("AI ML Recruiter", "United States"),
        ("Senior Recruiter Technology", "Australia"),
        ("Technical Hiring Manager", "Canada"),
        ("Headhunter Technology", "United States"),
        ("SaaS Recruiter", "Australia"),
        ("Executive Recruiter IT", "United States"),
        ("HR Tech Recruiter", "Canada"),
        ("Cyber Security Recruiter", "United States"),
        ("Data Engineering Recruiter", "Australia"),
    ]
    
    def __init__(self):
        self.model = None
        if genai and config.GEMINI_API_KEY:
            try:
                genai.configure(api_key=config.GEMINI_API_KEY)
                self.model = genai.GenerativeModel("gemini-2.0-flash")
                print("Gemini AI search generator initialized successfully")
            except Exception as e:
                print(f"Failed to initialize Gemini: {e}")
    
    def generate_queries(self, count: int = 10) -> List[tuple]:
        """Generate diverse search queries for recruiters."""
        if self.model:
            try:
                return self._generate_ai_queries(count)
            except Exception as e:
                print(f"AI query generation failed: {e}")
        
        return self._get_fallback_queries(count)
    
    def _generate_ai_queries(self, count: int) -> List[tuple]:
        """Use Gemini to generate search queries."""
        locations = ", ".join(config.PRIORITY_LOCATIONS)
        
        prompt = f"""Generate {count} unique LinkedIn search queries to find tech recruiters.

Requirements:
- Target: Senior Recruiters, Technical Recruiters, IT Staffing Consultants, Talent Acquisition professionals
- Industries: Software, IT, Technology, Cloud, AI/ML, Fintech, SaaS, Cybersecurity, Data Engineering
- Locations to prioritize: {locations}
- Queries should be diverse and specific
- Each query should use a different combination of role title and location

Return ONLY a JSON array of objects with "keyword" and "location" fields.
Example: [{{"keyword": "Senior Technical Recruiter", "location": "United States"}}]

Generate {count} unique combinations:"""

        response = self.model.generate_content(prompt)
        text = response.text
        
        # Parse JSON from response
        import json
        import re
        
        # Extract JSON array from response
        json_match = re.search(r'\[.*\]', text, re.DOTALL)
        if json_match:
            queries_data = json.loads(json_match.group())
            return [(q["keyword"], q["location"]) for q in queries_data]
        
        return self._get_fallback_queries(count)
    
    def _get_fallback_queries(self, count: int) -> List[tuple]:
        """Get fallback queries without AI."""
        queries = self.FALLBACK_QUERIES.copy()
        random.shuffle(queries)
        return queries[:count]
    
    def get_query_for_location(self, location: str) -> str:
        """Get a random recruiter keyword for a specific location."""
        keywords = [
            "Senior Technical Recruiter",
            "Tech Recruiter",
            "IT Recruitment Consultant",
            "Talent Acquisition Manager",
            "Software Recruiter",
            "Engineering Recruiter",
            "Technology Hiring Manager",
            "Staffing Consultant IT",
        ]
        return random.choice(keywords)


# Singleton instance
search_generator = RecruiterSearchGenerator()
