from crewai import Agent, Task
from crewai.tools import BaseTool
from datetime import datetime, timedelta
from typing import Any, List
from pydantic import BaseModel, Field

class TriggerDetectionInput(BaseModel):
    companies: List[dict] = Field(description="List of companies to analyze for trigger events")

class TriggerDetectionTool(BaseTool):
    name: str = "detect_triggers"
    description: str = "Find hiring signals, funding news, leadership changes"
    args_schema: type[BaseModel] = TriggerDetectionInput
    mcp: Any = None
    
    def __init__(self, mcp_client):
        super().__init__()
        self.mcp = mcp_client
    
    def _run(self, companies) -> list:
        # Handle case where companies might be wrapped in a dict
        if isinstance(companies, dict) and 'companies' in companies:
            companies = companies['companies']
        
        # Ensure companies is a list
        if not isinstance(companies, list):
            return []
        
        if not companies:
            return []
        
        for company in companies:
            if not isinstance(company, dict):
                continue
                
            triggers = []
            
            # Detect hiring triggers
            hiring_signals = self._detect_hiring_triggers(company)
            triggers.extend(hiring_signals)
            
            # Detect funding triggers
            funding_signals = self._detect_funding_triggers(company)
            triggers.extend(funding_signals)
            
            # Detect leadership changes
            leadership_signals = self._detect_leadership_triggers(company)
            triggers.extend(leadership_signals)
            
            # Detect expansion signals
            expansion_signals = self._detect_expansion_triggers(company)
            triggers.extend(expansion_signals)
            
            company['trigger_events'] = triggers
            company['trigger_score'] = self._calculate_trigger_score(triggers)
        
        return sorted(companies, key=lambda x: x.get('trigger_score', 0), reverse=True)
    
    def _detect_hiring_triggers(self, company):
        """Detect hiring triggers using LinkedIn data."""
        try:
            linkedin_data = self.mcp.scrape_company_linkedin(company['name'])
            
            triggers = []
            
            # Check for hiring activity in LinkedIn data
            if linkedin_data and not linkedin_data.get('error'):
                hiring_posts = linkedin_data.get('hiring_posts', [])
                recent_activity = linkedin_data.get('recent_activity', [])
                
                if hiring_posts:
                    triggers.append({
                        'type': 'hiring_spike',
                        'severity': 'high',
                        'description': f"Active hiring detected at {company['name']} - {len(hiring_posts)} open positions",
                        'date_detected': datetime.now().isoformat(),
                        'source': 'linkedin_api'
                    })
                
                if recent_activity:
                    triggers.append({
                        'type': 'company_activity',
                        'severity': 'medium',
                        'description': f"Increased LinkedIn activity at {company['name']}",
                        'date_detected': datetime.now().isoformat(),
                        'source': 'linkedin_api'
                    })
            
            return triggers
        except Exception as e:
            print(f"Error detecting hiring triggers for {company['name']}: {str(e)}")
            return []
    
    
    def _detect_funding_triggers(self, company):
        """Detect funding triggers using news search."""
        try:
            funding_data = self.mcp.search_funding_news(company['name'])
            
            triggers = []
            
            if funding_data and not funding_data.get('error'):
                results = funding_data.get('results', [])
                
                if results:
                    triggers.append({
                        'type': 'funding_round',
                        'severity': 'high',
                        'description': f"Recent funding activity detected at {company['name']}",
                        'date_detected': datetime.now().isoformat(),
                        'source': 'news_search'
                    })
            
            return triggers
        except Exception as e:
            print(f"Error detecting funding triggers for {company['name']}: {str(e)}")
            return []
    
    
    def _detect_leadership_triggers(self, company):
        """Detect leadership changes using news search."""
        try:
            news_data = self.mcp.search_company_news(company['name'])
            
            triggers = []
            
            if news_data and not news_data.get('error'):
                results = news_data.get('results', [])
                
                if results:
                    # Check for leadership keywords in news results
                    leadership_keywords = ['ceo', 'cto', 'vp', 'hired', 'joins', 'appointed']
                    for result in results:
                        if any(keyword in str(result).lower() for keyword in leadership_keywords):
                            triggers.append({
                                'type': 'leadership_change',
                                'severity': 'medium',
                                'description': f"Leadership changes detected at {company['name']}",
                                'date_detected': datetime.now().isoformat(),
                                'source': 'news_search'
                            })
                            break
            
            return triggers
        except Exception as e:
            print(f"Error detecting leadership triggers for {company['name']}: {str(e)}")
            return []
    
    def _detect_expansion_triggers(self, company):
        """Detect business expansion using news search."""
        try:
            news_data = self.mcp.search_company_news(company['name'])
            
            triggers = []
            
            if news_data and not news_data.get('error'):
                results = news_data.get('results', [])
                
                if results:
                    # Check for expansion keywords in news results
                    expansion_keywords = ['expansion', 'new office', 'opening', 'market']
                    for result in results:
                        if any(keyword in str(result).lower() for keyword in expansion_keywords):
                            triggers.append({
                                'type': 'expansion',
                                'severity': 'medium',
                                'description': f"Business expansion detected at {company['name']}",
                                'date_detected': datetime.now().isoformat(),
                                'source': 'news_search'
                            })
                            break
            
            return triggers
        except Exception as e:
            print(f"Error detecting expansion triggers for {company['name']}: {str(e)}")
            return []
    
    def _calculate_trigger_score(self, triggers):
        severity_weights = {'high': 15, 'medium': 10, 'low': 5}
        return sum(severity_weights.get(t.get('severity', 'low'), 5) for t in triggers)

def create_trigger_detection_agent(mcp_client):
    return Agent(
        role='Trigger Event Analyst',
        goal='Identify buying signals and optimal timing for outreach',
        backstory='Expert at detecting business events that indicate readiness to buy.',
        tools=[TriggerDetectionTool(mcp_client)],
        verbose=True
    )
    