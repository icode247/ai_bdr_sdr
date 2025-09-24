from crewai import Agent, Task
from crewai.tools import BaseTool
from typing import Any, List
from pydantic import BaseModel, Field
import re

class ContactResearchInput(BaseModel):
    companies: List[dict] = Field(description="List of companies to research contacts for")
    target_roles: List[str] = Field(description="List of target roles to find contacts for")

class ContactResearchTool(BaseTool):
    name: str = "research_contacts"
    description: str = "Find and verify decision-maker contact information using MCP"
    args_schema: type[BaseModel] = ContactResearchInput
    mcp: Any = None
    
    def __init__(self, mcp_client):
        super().__init__()
        self.mcp = mcp_client
    
    def _run(self, companies, target_roles) -> list:
        # Ensure companies is a list
        if not isinstance(companies, list):
            print(f"Warning: Expected list of companies, got {type(companies)}")
            return []
        
        if not companies:
            print("No companies provided for contact research")
            return []
        
        # Ensure target_roles is a list
        if not isinstance(target_roles, list):
            target_roles = [target_roles] if target_roles else []
        
        for company in companies:
            if not isinstance(company, dict):
                print(f"Warning: Expected company dict, got {type(company)}")
                continue
                
            contacts = []
            
            for role in target_roles:
                role_contacts = self._search_contacts_by_role(company, role)
                for contact in role_contacts:
                    enriched = self._enrich_contact_data(contact, company)
                    if self._validate_contact(enriched):
                        contacts.append(enriched)
            
            company['contacts'] = self._deduplicate_contacts(contacts)
            company['contact_score'] = self._calculate_contact_quality(contacts)
        
        return companies
    
    def _search_contacts_by_role(self, company, role):
        """Search for contacts by role using MCP."""
        try:
            # Search for LinkedIn contacts using MCP
            search_query = f"{company['name']} {role} LinkedIn contact"
            search_result = self.mcp.search_company_news(search_query)
            
            contacts = []
            if search_result and search_result.get('results'):
                contacts.extend(self._extract_contacts_from_mcp_results(search_result['results'], role))
            
            # Also search for general contact information
            if not contacts:
                contact_query = f"{company['name']} {role} email contact"
                contact_result = self.mcp.search_company_news(contact_query)
                if contact_result and contact_result.get('results'):
                    contacts.extend(self._extract_contacts_from_mcp_results(contact_result['results'], role))
            
            return contacts[:3]  # Limit to 3 contacts per role
            
        except Exception as e:
            print(f"Error searching contacts for {company['name']} {role}: {str(e)}")
            return []
    
    def _extract_contacts_from_mcp_results(self, results, role):
        """Extract contact information from MCP search results."""
        contacts = []
        
        for result in results:
            try:
                title = result.get('title', '')
                snippet = result.get('snippet', '')
                url = result.get('url', '')
                
                # Try to extract names from title or snippet
                names = self._extract_names_from_text(title + ' ' + snippet)
                
                for name_parts in names:
                    if len(name_parts) >= 2:
                        first_name, last_name = name_parts[0], ' '.join(name_parts[1:])
                        
                        contacts.append({
                            'first_name': first_name,
                            'last_name': last_name,
                            'title': role,
                            'linkedin_url': url if 'linkedin' in url else '',
                            'data_sources': 1,
                            'source': 'mcp_search'
                        })
                        
                        if len(contacts) >= 2:  # Limit contacts per result
                            break
                            
            except Exception as e:
                print(f"Error extracting contact from result: {str(e)}")
                continue
        
        return contacts
    
    def _extract_names_from_text(self, text):
        """Extract likely names from text."""
        import re
        
        # Pattern for names (First Last, First M Last, etc.)
        name_patterns = [
            r'\b([A-Z][a-z]+)\s+([A-Z][a-z]+)\b',  # First Last
            r'\b([A-Z][a-z]+)\s+([A-Z]\.?\s*[A-Z][a-z]+)\b',  # First M Last
            r'\b([A-Z][a-z]+)\s+([A-Z][a-z]+)\s+([A-Z][a-z]+)\b'  # First Middle Last
        ]
        
        names = []
        for pattern in name_patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                if isinstance(match, tuple):
                    names.append(list(match))
                
        return names[:3]  # Limit to 3 names
    
    def _enrich_contact_data(self, contact, company):
        # Generate email using common patterns
        if not contact.get('email'):
            contact['email'] = self._generate_email(
                contact['first_name'], 
                contact['last_name'], 
                company.get('domain', '')
            )
        
        # Validate email format
        contact['email_valid'] = self._validate_email(contact.get('email', ''))
        
        # Calculate confidence score
        contact['confidence_score'] = self._calculate_confidence(contact)
        
        return contact
    
    def _generate_email(self, first, last, domain):
        if not all([first, last, domain]):
            return ""
        return f"{first.lower()}.{last.lower()}@{domain}"
    
    def _validate_email(self, email):
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email))
    
    def _calculate_confidence(self, contact):
        score = 0
        if contact.get('linkedin_url'): score += 30
        if contact.get('email_valid'): score += 25
        if contact.get('data_sources', 0) > 1: score += 20
        if all(contact.get(f) for f in ['first_name', 'last_name', 'title']): score += 25
        return score
    
    def _validate_contact(self, contact):
        required = ['first_name', 'last_name', 'title']
        return (all(contact.get(f) for f in required) and 
                contact.get('confidence_score', 0) >= 50)
    
    def _deduplicate_contacts(self, contacts):
        seen = set()
        unique = []
        for contact in contacts:
            key = contact.get('email', '') or f"{contact.get('first_name', '')}_{contact.get('last_name', '')}"
            if key and key not in seen:
                seen.add(key)
                unique.append(contact)
        return sorted(unique, key=lambda x: x.get('confidence_score', 0), reverse=True)
    
    def _calculate_contact_quality(self, contacts):
        if not contacts:
            return 0
        avg_confidence = sum(c.get('confidence_score', 0) for c in contacts) / len(contacts)
        high_quality = sum(1 for c in contacts if c.get('confidence_score', 0) >= 75)
        return min(avg_confidence + (high_quality * 5), 100)

def create_contact_research_agent(mcp_client):
    return Agent(
        role='Contact Intelligence Specialist',
        goal='Find accurate contact information for decision-makers using MCP',
        backstory='Expert at finding and verifying contact information using advanced MCP search tools.',
        tools=[ContactResearchTool(mcp_client)],
        verbose=True
    )