from datetime import timedelta
from django.utils import timezone
from partners.models import Opportunity

def get_ranked_opportunities_for_ep(ep):
    """
    Returns a sorted list of dictionaries representing matched opportunities for an EP.
    Score breakdown:
    +40 if track matches (GTe/GTa)
    +20 if study field matches
    +20 if experience level matches
    +10 if availability date is within 30 days of opp start date
    """
    ranked_opps = []
    
    # Only consider open opportunities with remaining capacity
    open_opps = Opportunity.objects.filter(is_open=True)
    
    for opp in open_opps:
        score = 0
        breakdown = []
        
        # Track match
        # EP track choices: 'GTE', 'GTA', 'GV'
        # Opportunity track choices: 'GTE', 'GTA', 'GV'
        if ep.track and opp.track and ep.track == opp.track:
            score += 40
            breakdown.append("Track Match (+40)")
            
        # Study field match
        if ep.study_field and opp.required_study_field and ep.study_field.lower() in opp.required_study_field.lower():
            score += 20
            breakdown.append("Field Match (+20)")
            
        # Experience level match
        if ep.experience_level and opp.experience_level_required and ep.experience_level == opp.experience_level_required:
            score += 20
            breakdown.append("Experience Match (+20)")
            
        # Availability match (within 30 days) - using expires_at as a proxy for start date
        if ep.availability_date and opp.expires_at:
            date_diff = abs((ep.availability_date - opp.expires_at).days)
            if date_diff <= 30:
                score += 10
                breakdown.append("Date Match (+10)")
                
        # Filter out 0 scores or you can return them all, but ranked
        ranked_opps.append({
            'opportunity': opp,
            'score': score,
            'breakdown': breakdown
        })
        
    # Sort by score descending
    ranked_opps.sort(key=lambda x: x['score'], reverse=True)
    return ranked_opps
