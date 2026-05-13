"""Plato as facilitator - template-based"""

from typing import List, Dict, Optional
from dataclasses import dataclass


@dataclass
class TurnContext:
    """Context for a single turn in the debate."""
    turn_number: int
    topic: str
    speakers: List[str]
    current_speaker: str
    previous_speaker: Optional[str] = None


class Plato:
    """
    Plato as the facilitator of Socratic discourse.
    
    Role: Moderates the discussion between experts without being
    an agent himself. Uses pre-defined templates to guide the dialogue.
    
    Key functions:
    - Opening: Introduce the topic
    - Transitions: Move between speakers with Socratic prompts
    - Summarize: Highlight tensions between views
    - Invite user: Encourage participation
    - Close: End with reflective questions
    """
    
    # ==================
    # OPENING
    # ==================
    
    @staticmethod
    def opening(topic: str, speakers: List[str]) -> Dict:
        """
        Generate the opening of a Socratic dialogue.
        
        Args:
            topic: The question being debated
            speakers: List of expert names participating
            
        Returns:
            Dict with Plato's opening message and metadata
        """
        speaker_names = ", ".join(speakers[:-1]) + f", and {speakers[-1]}"
        
        return {
            "role": "plato",
            "type": "opening",
            "content": f""" *The Academy gathers...*

The question before us is: **{topic}**

We have before us {speaker_names} — each a thinker of distinction, each with their own way of seeing the world.

Let us examine this matter together, as Socrates would have wished. 
Each of you, speak your truth. And let us test these truths through questioning.

*Remember: we seek understanding, not victory.*""",
            "guidance": "Begin the dialogue with your perspective on this question."
        }
    
    # ==================
    # TRANSITIONS
    # ==================
    
    @staticmethod
    def transition(context: TurnContext, previous_content: str) -> Dict:
        """
        Generate a Socratic transition between speakers.
        
        Args:
            context: Current turn context
            previous_content: What the previous speaker said
            
        Returns:
            Dict with Plato's transition message
        """
        prev = context.previous_speaker or "the previous speaker"
        curr = context.current_speaker
        
        # Socratic questioning templates
        socratic_prompts = [
            f"""🜵 *Plato's question to {curr}:*

{prev} has presented their view. But I must ask: 
What assumptions lie beneath their argument? 
Are these assumptions justified, or do they contain hidden flaws?""",
            
            f"""*Plato probes further:*

{prev} makes a compelling point. Yet consider:
What if their reasoning rests on a foundation that does not hold?
{curr}, you are known for your critical mind — where are the cracks in this argument?""",
            
            f""" *Plato challenges {curr}:*

{prev} claims much, but Socrates taught us to examine every claim.
{curr}, you have heard their argument. Now test it:
What do they take for granted that cannot be taken for granted?
What have they overlooked?""",
        ]
        
        # Rotate through prompts based on turn number
        prompt_index = (context.turn_number - 1) % len(socratic_prompts)
        
        return {
            "role": "plato",
            "type": "transition",
            "content": socratic_prompts[prompt_index],
            "guidance": f"Respond to {prev}'s argument by identifying its weaknesses or building upon it."
        }
    
    # ==================
    # SUMMARIZE
    # ==================
    
    @staticmethod
    def summarize(turns: List[Dict]) -> Dict:
        """
        Generate a summary of the discourse thus far.
        
        Args:
            turns: List of all turns in the debate
            
        Returns:
            Dict with Plato's summary
        """
        # Extract speaker positions
        positions = []
        for turn in turns:
            if turn.get("speaker") and turn.get("content"):
                # Get first sentence as their position
                content = turn["content"]
                first_sentence = content.split(".")[0] if "." in content else content[:100]
                positions.append(f"**{turn['speaker']}**: {first_sentence}...")
        
        if len(positions) < 2:
            return {
                "role": "plato",
                "type": "summary",
                "content": "We have only just begun our inquiry...",
                "guidance": "Continue the dialogue."
            }
        
        # Build summary
        summary_text = " *Plato takes stock:*\n\n"
        summary_text += "We have heard competing views:\n\n"
        
        for pos in positions[-4:]:  # Last 4 positions
            summary_text += f"- {pos}\n\n"
        
        summary_text += """*The tension between these views is the heart of our inquiry.*
        
Not in declaring a winner, but in understanding why they disagree,
do we find wisdom."""
        
        return {
            "role": "plato",
            "type": "summary",
            "content": summary_text,
            "guidance": "Continue the dialogue, building on or challenging what has been said."
        }
    
    # ==================
    # INVITE USER
    # ==================
    
    @staticmethod
    def invite_user(context: Optional[TurnContext] = None) -> Dict:
        """
        Invite the user to participate in the dialogue.
        
        Args:
            context: Optional turn context
            
        Returns:
            Dict with Plato's invitation
        """
        return {
            "role": "plato",
            "type": "invite_user",
            "content": """ *Plato turns to you:*

You have listened with patience. Now speak.

Do you find one argument more convincing than the other?
Or have you noticed something the experts have missed?

Remember: the unexamined life is not worth living.
Your thinking is as valuable as any expert's.

*What is your view?*""",
            "guidance": "Wait for the user's input before continuing."
        }
    
    # ==================
    # CLOSING
    # ==================
    
    @staticmethod
    def closing(topic: str, turns: List[Dict]) -> Dict:
        """
        Generate the closing of a Socratic dialogue.
        
        Args:
            topic: The original question
            turns: All turns in the debate
            
        Returns:
            Dict with Plato's closing
        """
        # Count positions
        unique_speakers = len(set(t.get("speaker") for t in turns if t.get("speaker")))
        
        return {
            "role": "plato",
            "type": "closing",
            "content": f""" *The Academy disperses...*

We have examined **{topic}** from many angles.

{unique_speakers} voices have spoken. Many truths, many challenges, many questions.

*What have we learned?*

Perhaps that the question is more complex than any single answer.
Perhaps that wisdom lies not in certainty, but in knowing how little we know.

> *"The unexamined life is not worth living."* — Socrates

**What questions remain for you?**

The dialogue ends, but your thinking should continue.""",
            "guidance": "Offer to start a new dialogue or explore related topics."
        }
    
    # ==================
    # ERROR HANDLING
    # ==================
    
    @staticmethod
    def redirect(topic: str, issue: str) -> Dict:
        """
        Handle when the dialogue goes off track.
        
        Args:
            topic: Original topic
            issue: What went wrong
            
        Returns:
            Dict with Plato redirecting
        """
        return {
            "role": "plato",
            "type": "redirect",
            "content": f"""*Plato intervenes:*

We have strayed from our question: **{topic}**

{issue}

Let us return to what we were examining. 
What is the essential matter we were exploring?""",
            "guidance": "Bring the dialogue back to the original topic."
        }


# Helper function for creating context
def create_context(
    turn_number: int,
    topic: str,
    speakers: List[str],
    current_speaker: str
) -> TurnContext:
    """Create a TurnContext object."""
    previous = speakers[turn_number - 2] if turn_number > 1 else None
    return TurnContext(
        turn_number=turn_number,
        topic=topic,
        speakers=speakers,
        current_speaker=current_speaker,
        previous_speaker=previous
    )