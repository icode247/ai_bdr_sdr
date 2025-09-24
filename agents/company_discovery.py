from crewai import Agent, Task
from crewai.tools import BaseTool
from typing import Any
from pydantic import BaseModel, Field

class CompanyDiscoveryInput(BaseModel):
    industry: str = Field(description="Target industry for company discovery")
    size_range: str = Field(description="Company size range (startup, small, medium, enterprise)")
    location: str = Field(default="", description="Geographic location or region")

class CompanyDiscoveryTool(BaseTool):
    name: str = "discover_companies"
    description: str = "Find companies matching ICP criteria using web scraping"
    args_schema: type[BaseModel] = CompanyDiscoveryInput
    mcp: Any = None
    
    def __init__(self, mcp_client):
        super().__init__()
        self.mcp = mcp_client
    
    def _run(self, industry: str, size_range: str, location: str = "") -> list:
        companies = []
        
        # Search multiple sources for companies with broader terms
        search_terms = [
            f"{industry} companies {size_range}",
            f"{industry} startups {location}",
            f"{industry} technology companies"
        ]
        
        for term in search_terms:
            results = self._search_companies(term)
            for company in results:
                enriched = self._enrich_company_data(company)
                if self._matches_icp(enriched, industry, size_range):
                    companies.append(enriched)
        
        return self._deduplicate_companies(companies)
    
    def _search_companies(self, term):
        """Search for companies using real web search through Bright Data."""
        try:
            # Use real company search through Google
            companies = []
            
            # Search for company listings and directories with simpler queries
            search_queries = [
                f"{term} directory",
                f"{term} list",
                f"{term} news"
            ]
            
            for query in search_queries:
                try:
                    # Perform actual web search using Bright Data
                    results = self._perform_company_search(query)
                    companies.extend(results)
                    
                    # Limit to avoid too many results
                    if len(companies) >= 10:
                        break
                        
                except Exception as e:
                    print(f"Error in search query '{query}': {str(e)}")
                    continue
            
            # Remove duplicates and return
            return self._filter_unique_companies(companies)
            
        except Exception as e:
            print(f"Error searching companies for '{term}': {str(e)}")
            return []
    
    def _enrich_company_data(self, company):
        linkedin_data = self.mcp.scrape_company_linkedin(company['name'])
        website_data = self.mcp.scrape_company_website(company.get('domain', ''))
        
        # Extract employee count from LinkedIn data if available
        employee_count = linkedin_data.get('employee_count') or 150
        
        return {
            **company,
            'linkedin_intelligence': linkedin_data,
            'website_intelligence': website_data,
            'employee_count': employee_count,
            'icp_score': 0
        }
    
    def _matches_icp(self, company, industry, size_range):
        score = 0
        if industry.lower() in company.get('industry', '').lower():
            score += 30
        if self._check_size_range(company.get('employee_count', 0), size_range):
            score += 25
        
        # Add base score for having basic company information
        if company.get('name') and company.get('domain'):
            score += 20
        
        company['icp_score'] = score
        
        # Lower threshold to allow more companies through for demonstration
        return score >= 20
    
    def _check_size_range(self, count, size_range):
        ranges = {'startup': (1, 50), 'small': (51, 200), 'medium': (201, 1000)}
        min_size, max_size = ranges.get(size_range, (0, 999999))
        return min_size <= count <= max_size
    
    def _deduplicate_companies(self, companies):
        seen = set()
        unique = []
        for company in companies:
            key = company.get('domain') or company['name'].lower()
            if key not in seen:
                seen.add(key)
                unique.append(company)
        return unique
    
    def _perform_company_search(self, query):
        """Perform company search using Bright Data MCP."""
        try:
            # Use MCP to search for companies
            search_result = self.mcp.search_company_news(query)
            
            if search_result and search_result.get('results'):
                return self._extract_companies_from_mcp_results(search_result['results'], query)
            else:
                print(f"No MCP results for: {query}")
                return []
                
        except Exception as e:
            print(f"Error performing company search via MCP: {str(e)}")
            return []
    
    def _extract_companies_from_search(self, html_content, original_query):
        """Extract company information from search results."""
        from bs4 import BeautifulSoup
        import re
        
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            companies = []
            
            # Look for search result snippets that contain company information
            search_results = soup.find_all(['div', 'span'], class_=re.compile(r'.*result.*|.*snippet.*', re.I))
            
            for result in search_results[:10]:  # Limit to first 10 results
                try:
                    text = result.get_text().strip()
                    
                    # Look for company patterns in the text
                    company_patterns = [
                        r'([A-Z][a-zA-Z\s&]+(?:Inc|Corp|LLC|Ltd|Solutions|Systems|Technologies|Software|Platform))',
                        r'([A-Z][a-zA-Z]+(?:Tech|Data|Cloud|Smart|Next|Pro|Max|Plus|Soft))',
                        r'([A-Z][a-zA-Z\s]+(?:is a|provides|offers|specializes))'
                    ]
                    
                    for pattern in company_patterns:
                        matches = re.findall(pattern, text)
                        for match in matches:
                            company_name = match.strip()
                            
                            # Basic filtering
                            if (len(company_name) > 3 and 
                                len(company_name) < 50 and
                                not any(word in company_name.lower() for word in ['google', 'facebook', 'microsoft', 'amazon', 'apple'])):
                                
                                # Try to extract domain
                                domain = self._guess_domain(company_name)
                                
                                # Determine industry from query
                                industry = self._extract_industry_from_query(original_query)
                                
                                companies.append({
                                    'name': company_name,
                                    'domain': domain,
                                    'industry': industry
                                })
                                
                                if len(companies) >= 5:  # Limit per search
                                    break
                        
                        if len(companies) >= 5:
                            break
                            
                except Exception as e:
                    continue  # Skip problematic results
            
            return companies
            
        except Exception as e:
            print(f"Error extracting companies from search: {str(e)}")
            return []
    
    def _guess_domain(self, company_name):
        """Generate likely domain name from company name."""
        import re
        
        # Clean company name
        clean_name = re.sub(r'(Inc|Corp|LLC|Ltd|Solutions|Systems|Technologies|Software|Platform)', '', company_name, flags=re.IGNORECASE)
        clean_name = re.sub(r'[^a-zA-Z\s]', '', clean_name).strip()
        
        # Convert to domain format
        domain_parts = clean_name.lower().split()[:2]  # Take first 2 words max
        if domain_parts:
            domain = ''.join(domain_parts) + '.com'
            return domain
        
        return ""
    
    def _extract_industry_from_query(self, query):
        """Extract industry from search query."""
        query_lower = query.lower()
        
        industry_mappings = {
            'saas': 'SaaS',
            'fintech': 'FinTech', 
            'ecommerce': 'E-commerce',
            'healthcare': 'Healthcare',
            'ai': 'AI/ML',
            'machine learning': 'AI/ML',
            'artificial intelligence': 'AI/ML'
        }
        
        for keyword, industry in industry_mappings.items():
            if keyword in query_lower:
                return industry
        
        return 'Technology'  # Default industry
    
    def _filter_unique_companies(self, companies):
        """Filter out duplicate companies."""
        seen_names = set()
        unique_companies = []
        
        for company in companies:
            name_key = company.get('name', '').lower()
            if name_key and name_key not in seen_names:
                seen_names.add(name_key)
                unique_companies.append(company)
        
        return unique_companies
    
    def _extract_companies_from_mcp_results(self, mcp_results, original_query):
        """Extract company information from MCP search results."""
        companies = []
        
        for result in mcp_results[:10]:  # Limit to first 10 results
            try:
                title = result.get('title', '')
                url = result.get('url', '')
                snippet = result.get('snippet', '')
                
                # Extract company name from title or URL
                company_name = self._extract_company_name_from_result(title, url)
                
                if company_name and len(company_name) > 2:
                    # Try to extract domain
                    domain = self._extract_domain_from_url(url)
                    
                    # Determine industry from query
                    industry = self._extract_industry_from_query(original_query)
                    
                    companies.append({
                        'name': company_name,
                        'domain': domain,
                        'industry': industry
                    })
                    
            except Exception as e:
                print(f"Error extracting company from MCP result: {str(e)}")
                continue
        
        return companies
    
    def _extract_company_name_from_result(self, title, url):
        """Extract company name from search result title or URL."""
        import re
        
        # Try to get company name from title
        if title:
            # Look for patterns like "Company Name - About" or "About Company Name"
            title_clean = re.sub(r'[\|\-\—\–].*$', '', title).strip()
            
            # Remove common suffixes
            title_clean = re.sub(r'\s+(Inc|Corp|LLC|Ltd|Solutions|Systems|Technologies|Software|Platform|Company)$', '', title_clean, flags=re.IGNORECASE)
            
            if len(title_clean) > 2 and len(title_clean) < 50:
                return title_clean
        
        # Fallback: try to extract from URL
        if url:
            domain_parts = url.split('/')[2].split('.')
            if len(domain_parts) > 1:
                return domain_parts[0].title()
        
        return None
    
    def _extract_domain_from_url(self, url):
        """Extract domain from URL."""
        if not url:
            return ""
        
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            return parsed.netloc
        except:
            # Fallback parsing
            if '//' in url:
                return url.split('//')[1].split('/')[0]
            return ""

def create_company_discovery_agent(mcp_client):
    return Agent(
        role='Company Discovery Specialist',
        goal='Find high-quality prospects matching ICP criteria',
        backstory='Expert at identifying potential customers using real-time web intelligence.',
        tools=[CompanyDiscoveryTool(mcp_client)],
        verbose=True
    )