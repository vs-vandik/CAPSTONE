"""Aporia system - exposes limitations of expert arguments."""

from typing import List, Dict, Optional
from dataclasses import dataclass


@dataclass
class AporiaFinding:
    """A single finding about argument limitations."""
    expert: str
    limitation_type: str  # assumption, blind_spot, contradiction, unaddressed
    description: str
    question: str


class Aporia:
    """
    Aporia system - exposes the limitations of expert arguments.
    
    Named after the Socratic concept of aporia (ἀπορία) - a state of 
    productive puzzlement reached when examining a belief reveals 
    its limitations or contradictions.
    
    This module analyzes debate history to identify:
    - Unstated assumptions
    - Blind spots (topics not addressed)
    - Contradictions between experts
    - Unanswered questions
    
    Two modes:
    1. EMBEDDED: Limitations included in each response (free)
    2. ON_DEMAND: Full analysis when user clicks button
    """
    
    # ==================
    # LIMITATION TYPES
    # ==================
    
    LIMITATION_TYPES = {
        "assumption": "Unstated assumption that underlies the argument",
        "blind_spot": "Topic not addressed but relevant to the question",
        "contradiction": "Direct conflict with another expert's position",
        "unanswered": "Important question raised but not addressed"
    }
    
    # ==================
    # EMBEDDED LIMITATIONS (Free - no LLM)
    # ==================
    
    @staticmethod
    def get_limitations_prompt(expert_name: str) -> str:
        """
        Returns a prompt that experts can use to include their own limitations.
        This is inserted into the LLM prompt when generating expert responses.
        
        Args:
            expert_name: Name of the expert
            
        Returns:
            Prompt string to add to system prompt
        """
        return f"""
As {expert_name}, after your main response, include a brief section:

LIMITATIONS:
- One assumption your argument makes that could be challenged: ...
- One thing your view does not account for: ...
- One question your position raises but does not answer: ..."""
    
    @staticmethod
    def parse_embedded_limitations(response: str) -> Optional[AporiaFinding]:
        """
        Parse limitations from an expert's response if present.
        
        Args:
            response: The expert's full response
            
        Returns:
            AporiaFinding if limitations found, None otherwise
        """
        if "LIMITATIONS:" not in response:
            return None
        
        try:
            limitations_section = response.split("LIMITATIONS:")[1]
            # Simple parsing - in production could be more sophisticated
            return AporiaFinding(
                expert="current",
                limitation_type="embedded",
                description=limitations_section[:200],
                question="Consider these limitations when evaluating this argument."
            )
        except IndexError:
            return None
    
    # ==================
    # ON-DEMAND ANALYSIS (Triggered by button)
    # ==================
    
    @staticmethod
    def analyze(turns: List[Dict], mode: str = "simple") -> Dict:
        """
        Analyze debate turns to identify limitations.
        
        Args:
            turns: List of all debate turns
            mode: "simple" (free, algorithm) or "deep" (LLM-powered)
            
        Returns:
            Dict with aporia findings
        """
        # Collect speakers first
        speakers = []
        for turn in turns:
            speaker = turn.get("speaker")
            if speaker and speaker not in speakers:
                speakers.append(speaker)
        
        if mode == "simple":
            return Aporia._simple_analysis(turns, speakers)
        else:
            return Aporia._deep_analysis(turns)
    
    @staticmethod
    def _simple_analysis(turns: List[Dict], speakers: List[str]) -> Dict:
        """
        Free algorithm-based analysis.
        
        Identifies limitations through keyword detection and pattern matching.
        No LLM needed.
        """
        findings = []

        # Keywords that indicate assumptions
        assumption_keywords = [
            "assume", "presume", "taken for granted", 
            "naturally", "of course", "obviously"
        ]
        
        # Keywords that indicate blind spots
        blind_spot_keywords = [
            "don't consider", "overlook", "fail to address",
            "not mentioned", "aside from"
        ]
        
        # Keywords that indicate contradictions
        contradiction_keywords = [
            "however", "but", "whereas", "on the contrary",
            "disagree", "conflict"
        ]
        
        # Analyze each turn
        for i, turn in enumerate(turns):
            speaker = turn.get("speaker", "Unknown")
            content = turn.get("content", "")
            
            content_lower = content.lower()
            
            # Check for assumptions
            for keyword in assumption_keywords:
                if keyword in content_lower:
                    # Find the sentence containing the keyword
                    sentences = content.split(".")
                    for sentence in sentences:
                        if keyword in sentence.lower():
                            findings.append({
                                "expert": speaker,
                                "type": "assumption",
                                "description": f"Uses '{keyword}' - may be assuming: {sentence[:100]}",
                                "question": f"What if this assumption is wrong, {speaker}?"
                            })
                            break
            
            # Check for contradictions (compare with other turns)
            for keyword in contradiction_keywords:
                if keyword in content_lower:
                    # Find the other speaker
                    other_speakers = [s for s in speakers if s != speaker]
                    other = other_speakers[0] if other_speakers else "another expert"
                    findings.append({
                        "expert": speaker,
                        "type": "contradiction",
                        "description": f"Expresses contrast with '{keyword}' - may contradict {other}'s position",
                        "question": f"How does this reconcile with {other}'s position?"
                    })
        
        # Deduplicate and limit
        unique_findings = Aporia._deduplicate(findings)
        
        return Aporia._format_aporia_response(unique_findings, len(turns), speakers)
    
    @staticmethod
    def _deduplicate(findings: List[Dict]) -> List[Dict]:
        """Remove duplicate findings."""
        seen = set()
        unique = []
        
        for f in findings:
            key = (f["expert"], f["type"], f["description"][:50])
            if key not in seen:
                seen.add(key)
                unique.append(f)
        
        return unique[:6]  # Max 6 findings
    
    @staticmethod
    def _format_aporia_response(findings: List[Dict], turn_count: int, speakers: List[str] = None) -> Dict:
        """Format findings into a readable response."""
        
        if not speakers:
            speakers = []
        
        if not findings:
            return {
                "role": "plato",
                "type": "aporia",
                "content": """Aporia Analysis

The dialogue is still developing. More turns will reveal 
more nuances and potential limitations.

Return later for a deeper analysis.""",
                "findings": [],
                "guidance": "Continue the dialogue to gather more material for analysis."
            }
        
        # Group by type
        by_type = {"assumption": [], "blind_spot": [], "contradiction": [], "unanswered": []}
        for f in findings:
            t = f["type"]
            if t in by_type:
                by_type[t].append(f)
        
        # Build response
        content = "Aporia Analysis\n\n"
        content += f"Based on {turn_count} turns of dialogue between "
        if len(speakers) >= 2:
            content += f"{speakers[0]} and {speakers[1]}"
        elif len(speakers) == 1:
            content += speakers[0]
        content += ".\n\n"
        
        content += "Hidden Assumptions\n"
        if by_type["assumption"]:
            for f in by_type["assumption"][:2]:
                content += f"{f['expert']}: {f['description']}\n\n"
        else:
            content += "No clear assumptions detected yet.\n\n"
        
        content += "Contradictions\n"
        if by_type["contradiction"]:
            for f in by_type["contradiction"][:2]:
                content += f"{f['expert']}: {f['description']}\n\n"
        else:
            content += "No direct contradictions detected yet.\n\n"
        
        content += "Blind Spots\n"
        if by_type["blind_spot"]:
            for f in by_type["blind_spot"][:2]:
                content += f"{f['expert']}: {f['description']}\n\n"
        else:
            content += "No clear blind spots identified yet.\n\n"
        
        content += "---\n\n"
        content += """Aporia is not a weakness. It is the beginning of wisdom.
        
Recognizing the limits of each argument is the first step 
to forming your own judgment."""
        
        return {
            "role": "plato",
            "type": "aporia",
            "content": content,
            "findings": findings,
            "speakers": speakers,
            "guidance": "Use these findings to probe deeper or form your own opinion."
        }
    
    # ==================
    # TEMPLATE FOR LLM-POWERED ANALYSIS (Future)
    # ==================
    
    @staticmethod
    def get_deep_prompt(turns: List[Dict]) -> str:
        """
        Returns a prompt for LLM-powered analysis.
        Use this when user clicks button and mode="deep".
        
        Args:
            turns: List of debate turns
            
        Returns:
            Prompt string to send to LLM
        """
        turns_text = "\n".join([
            f"{t.get('speaker', 'Unknown')}: {t.get('content', '')[:200]}..."
            for t in turns
        ])
        
        return f"""Analyze this Socratic dialogue and identify the limitations 
of each expert's arguments. For each expert:

1. What unstated assumption do they make?
2. What do they not account for?
3. Where do they contradict another expert?
4. What question do they leave unanswered?

Dialogue:
{turns_text}

Provide a structured analysis of the limitations revealed."""
    
    # ==================
    # BUTTON TEXT
    # ==================
    
    @staticmethod
    def get_button_info() -> Dict:
        """
        Returns information about the Aporia button for the UI.
        """
        return {
            "label": "Aporia",
            "description": "Expose the assumptions and blind spots in the experts' arguments",
            "tooltip": "Aporia: Examine what the experts didn't address or took for granted",
            "icon": "A"
        }


# Helper function for easy calling
def analyze_debate(turns: List[Dict], mode: str = "simple") -> Dict:
    """Convenience function to analyze debate."""
    return Aporia.analyze(turns, mode)