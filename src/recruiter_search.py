"""
AI-Powered Recruiter Search Query Generator.
Uses Gemini API to create diverse search queries.
"""
import random
from typing import Any, List, Optional, cast
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

    ROLE_KEYWORDS = [
        "Senior Recruiter",
        "Technical Recruiter",
        "Recruitment Consultant",
        "Staffing Consultant",
        "Talent Acquisition Recruiter",
        "Hiring Specialist",
        "Recruiter",
    ]
    
    # Fallback queries focused on US, Canada, Australia
    FALLBACK_QUERIES = [
        ("Recruiter", "United States"),
        ("Senior Recruiter", "United States"),
        ("Technical Recruiter", "United States"),
        ("Recruitment Consultant", "United States"),
        ("Staffing Consultant", "United States"),
        ("Talent Acquisition Recruiter", "United States"),
        ("Hiring Specialist", "United States"),
        ("Recruiter", "Canada"),
        ("Senior Recruiter", "Canada"),
        ("Technical Recruiter", "Canada"),
        ("Recruitment Consultant", "Canada"),
        ("Staffing Consultant", "Canada"),
        ("Talent Acquisition Recruiter", "Canada"),
        ("Hiring Specialist", "Canada"),
        ("Recruiter", "Australia"),
        ("Senior Recruiter", "Australia"),
        ("Technical Recruiter", "Australia"),
        ("Recruitment Consultant", "Australia"),
        ("Staffing Consultant", "Australia"),
        ("Talent Acquisition Recruiter", "Australia"),
        ("Hiring Specialist", "Australia"),
    ]
    
    def __init__(self):
        self.model: Optional[Any] = None
        self.model_name = config.GEMINI_MODEL
        if genai and config.GEMINI_API_KEY:
            try:
                genai_client: Any = cast(Any, genai)
                configure = getattr(genai_client, "configure")
                model_factory = getattr(genai_client, "GenerativeModel")
                configure(api_key=config.GEMINI_API_KEY)
                
                # Ensure model name is valid (fallback to 1.5-flash if 3-flash passed)
                clean_model = self.model_name
                if "gemini-3" in clean_model:
                    clean_model = "gemini-1.5-flash"
                    
                self.model = model_factory(clean_model)
                print(f"Gemini AI search generator initialized successfully (model: {clean_model})")
            except Exception as e:
                print(f"Failed to initialize Gemini: {e}")
    
    def generate_queries(self, count: int = 10) -> List[tuple]:
        """Generate diverse search queries for recruiters."""
        if self.model:
            try:
                return self._generate_ai_queries(count)
            except Exception as e:
                print(f"AI query generation failed (model: {self.model_name}): {e}")
        
        return self._get_fallback_queries(count)
    
    def _generate_ai_queries(self, count: int) -> List[tuple]:
        """Use Gemini to generate search queries."""
        locations = ", ".join(config.PRIORITY_LOCATIONS)
        allowed_roles = ", ".join(self.ROLE_KEYWORDS)

        prompt = f"""Generate {count} unique LinkedIn search queries to find hiring professionals.

Requirements:
- Use ONLY these role keywords: {allowed_roles}
- Locations to prioritize: {locations}
- Keyword should be role-focused only (no skills, no tech stack, no industry buzzwords)
- Do NOT include terms like developer, engineering, SaaS, cloud, AI/ML, cybersecurity, or data.

Return ONLY a JSON array of objects with "keyword" and "location" fields.
Example: [{{"keyword": "Technical Recruiter", "location": "United States"}}]

Generate {count} unique combinations:"""

        model = self.model
        if model is None:
            return self._get_fallback_queries(count)

        response = cast(Any, model).generate_content(prompt)
        text = response.text
        
        # Parse JSON from response
        import json
        import re
        
        # Extract JSON array from response
        json_match = re.search(r'\[.*\]', text, re.DOTALL)
        if json_match:
            queries_data = json.loads(json_match.group())
            normalized = []
            seen = set()
            valid_locations = set(config.PRIORITY_LOCATIONS)

            for item in queries_data:
                raw_keyword = str(item.get("keyword", "")).strip()
                raw_location = str(item.get("location", "")).strip()
                if not raw_keyword:
                    continue

                keyword_lower = raw_keyword.lower()
                canonical_keyword = None
                for role in self.ROLE_KEYWORDS:
                    role_lower = role.lower()
                    if role_lower in keyword_lower or keyword_lower in role_lower:
                        canonical_keyword = role
                        break

                if not canonical_keyword:
                    continue

                location = raw_location if raw_location in valid_locations else random.choice(config.PRIORITY_LOCATIONS)
                pair = (canonical_keyword, location)
                if pair not in seen:
                    seen.add(pair)
                    normalized.append(pair)

            if normalized:
                if len(normalized) >= count:
                    return normalized[:count]

                fallback = self._get_fallback_queries(count)
                for pair in fallback:
                    if pair not in seen:
                        normalized.append(pair)
                        seen.add(pair)
                    if len(normalized) >= count:
                        break
                return normalized

        return self._get_fallback_queries(count)
    
    def _get_fallback_queries(self, count: int) -> List[tuple]:
        """Get fallback queries without AI."""
        queries = self.FALLBACK_QUERIES.copy()
        random.shuffle(queries)
        return queries[:count]
    
    def get_query_for_location(self, location: str) -> str:
        """Get a random recruiter keyword for a specific location."""
        del location
        return random.choice(self.ROLE_KEYWORDS)


# Singleton instance
search_generator = RecruiterSearchGenerator()
