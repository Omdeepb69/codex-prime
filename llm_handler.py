# llm_handler.py
# Description: Interfaces with the Google Gemini API for Codex Prime.
# Handles formatting requests, sending them to the LLM, and processing responses.

import os
import logging
import google.generativeai as genai
from google.generativeai.types import generation_types
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler() # Output logs to stderr
    ]
)
logger = logging.getLogger(__name__)

# --- Constants ---
# Consider using newer models like 'gemini-1.5-flash-latest' or 'gemini-1.5-pro-latest'
# if available and suitable for your use case and budget. 'gemini-pro' is a stable choice.
DEFAULT_MODEL_NAME = "gemini-pro"
# Stricter safety settings might block valid code generation/analysis.
# Adjust as needed based on testing and safety requirements.
DEFAULT_SAFETY_SETTINGS = {
    generation_types.HarmCategory.HARM_CATEGORY_HARASSMENT: generation_types.HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
    generation_types.HarmCategory.HARM_CATEGORY_HATE_SPEECH: generation_types.HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
    generation_types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: generation_types.HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
    generation_types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: generation_types.HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
}

# --- Initialization ---

def initialize_gemini(model_name: str = DEFAULT_MODEL_NAME) -> genai.GenerativeModel | None:
    """
    Initializes and configures the Google Gemini API client.

    Loads the API key from environment variables (.env file is supported).

    Args:
        model_name (str): The name of the Gemini model to use (e.g., 'gemini-pro').

    Returns:
        genai.GenerativeModel | None: An initialized GenerativeModel instance
                                      if successful, otherwise None.
    """
    try:
        load_dotenv()  # Load environment variables from .env file if present
        api_key = os.getenv("GOOGLE_API_KEY")

        if not api_key:
            logger.error("❌ GOOGLE_API_KEY not found in environment variables.")
            print("\nError: GOOGLE_API_KEY environment variable not set.")
            print("Please create a .env file in the project root with:")
            print("GOOGLE_API_KEY='YOUR_API_KEY'")
            print("Or set the environment variable directly.")
            return None

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(model_name)
        logger.info(f"✅ Gemini model '{model_name}' initialized successfully.")

        # Optional: Perform a quick test call to verify API key and connectivity
        try:
             # A simple, low-cost prompt to check connectivity
            model.generate_content("test", generation_config=genai.types.GenerationConfig(candidate_count=1))
            logger.info("✅ Gemini API connectivity test successful.")
        except Exception as test_e:
            logger.error(f"❌ Gemini API connectivity test failed: {test_e}", exc_info=False)
            print(f"\nWarning: Failed to connect to Gemini API with the provided key ({str(test_e)}).")
            print("Please ensure your API key is valid and has the Generative Language API enabled.")
            # Decide if you want to return None here or let subsequent calls fail
            # return None # Uncomment to enforce successful test call for initialization

        return model

    except ImportError:
        logger.error("❌ Failed to import google.generativeai. Is it installed (`pip install google-generativeai`)?")
        print("\nError: `google-generativeai` library not found.")
        print("Please install it using: pip install google-generativeai")
        return None
    except Exception as e:
        logger.error(f"❌ Unexpected error during Gemini initialization: {e}", exc_info=True)
        print(f"\nError: An unexpected error occurred during Gemini initialization: {e}")
        return None

# --- Core LLM Interaction ---

def _send_prompt(model: genai.GenerativeModel, prompt: str, safety_settings: dict = DEFAULT_SAFETY_SETTINGS) -> str | None:
    """
    Helper function to send a prompt to the Gemini model and handle responses/errors.

    Args:
        model (genai.GenerativeModel): The initialized Gemini model instance.
        prompt (str): The complete prompt string to send.
        safety_settings (dict): Safety settings for the generation request.

    Returns:
        str | None: The text content of the LLM's response, or None if an error
                    occurred or the response was blocked/empty.
    """
    if not model:
        logger.error("❌ Attempted to send prompt, but Gemini model is not initialized.")
        return None
    try:
        logger.debug(f"Sending prompt to Gemini:\n---PROMPT START---\n{prompt}\n---PROMPT END---")
        response = model.generate_content(
            prompt,
            safety_settings=safety_settings,
            # generation_config=genai.types.GenerationConfig(temperature=0.7) # Optional: Adjust generation parameters
        )
        logger.debug(f"Received raw response from Gemini: {response}")

        # Check for blocked content or lack of candidates
        if not response.candidates:
            block_reason = "Unknown"
            try:
                # Attempt to get the block reason if available
                block_reason = response.prompt_feedback.block_reason.name
            except Exception:
                pass # Ignore if feedback or reason is not available
            logger.warning(f"⚠️ LLM response was blocked or empty. Reason: {block_reason}")
            if response.prompt_feedback:
                 logger.warning(f"Prompt Feedback: {response.prompt_feedback}")
            return f"Error: The response was blocked due to safety settings (Reason: {block_reason}). You might need to adjust the safety levels or rephrase your request."

        # Extract text from the first candidate
        if response.candidates[0].content and response.candidates[0].content.parts:
            response_text = response.candidates[0].content.parts[0].text
            logger.debug(f"Extracted text from response: {response_text[:100]}...") # Log beginning of response
            return response_text
        else:
            # This case might occur if the model generates empty content despite having a candidate
            logger.warning("⚠️ LLM response candidate exists but contains no text parts.")
            return "" # Return empty string for valid but empty content

    except generation_types.StopCandidateException as e:
        # This can happen if the model stops generation prematurely (e.g., max tokens)
        # We might still have partial content.
        logger.warning(f"⚠️ LLM generation stopped unexpectedly: {e}")
        try:
            # Attempt to return partial content if available
            partial_text = e.response.candidates[0].content.parts[0].text
            logger.debug(f"Returning partial text due to StopCandidateException: {partial_text[:100]}...")
            return partial_text + "\n[Warning: Output may be truncated]"
        except (AttributeError, IndexError, Exception):
            logger.error("❌ Could not extract partial text after StopCandidateException.")
            return "Error: Generation stopped prematurely, and no partial output could be retrieved."
    except Exception as e:
        # Catch other potential API errors (network, authentication, etc.)
        logger.error(f"❌ An error occurred during the Gemini API call: {e}", exc_info=True)
        return f"Error: Failed to communicate with the LLM API ({e})"


def analyze_code(model: genai.GenerativeModel, code_context: str, user_query: str) -> str | None:
    """
    Asks the LLM to analyze the provided code context based on a user query.

    Args:
        model (genai.GenerativeModel): The initialized Gemini model instance.
        code_context (str): A string containing relevant code snippets, file structure,
                            or other contextual information about the repository.
        user_query (str): The specific question the user is asking about the code.

    Returns:
        str | None: The LLM's analysis as a string, or None if an error occurred.
    """
    prompt = f"""
You are Codex Prime, an AI assistant helping a user understand a GitHub repository via the terminal.
Your task is to analyze the provided code context based on the user's query.
Provide a clear, concise, and accurate analysis directly addressing the query.
Focus on explaining the relevant parts of the code and their relationship to the user's question.

# Continuing from where llm_handler.py left off

{code_context}

**User Query:** {user_query}
"""
    return _send_prompt(model, prompt)


def suggest_code_improvements(model: genai.GenerativeModel, code_snippet: str, improvement_goal: str = None) -> str | None:
    """
    Asks the LLM to suggest improvements for the provided code snippet.

    Args:
        model (genai.GenerativeModel): The initialized Gemini model instance.
        code_snippet (str): The code to be improved.
        improvement_goal (str, optional): Specific aspect to improve (e.g., "performance",
                                          "readability", "error handling").

    Returns:
        str | None: The LLM's suggestions as a string, or None if an error occurred.
    """
    goal_text = f"Specifically focus on improving {improvement_goal}." if improvement_goal else ""
    
    prompt = f"""
You are Codex Prime, an AI assistant helping a user improve their code.
Please suggest improvements for the following code.
{goal_text}
Provide clear, actionable suggestions and explain why they improve the code.
If appropriate, include code examples of your suggested improvements.

**Code to Improve:**
```
{code_snippet}
```
"""
    return _send_prompt(model, prompt)


def explain_error(model: genai.GenerativeModel, code_snippet: str, error_message: str) -> str | None:
    """
    Asks the LLM to explain an error message in the context of the provided code.

    Args:
        model (genai.GenerativeModel): The initialized Gemini model instance.
        code_snippet (str): The code that produced the error.
        error_message (str): The error message or traceback.

    Returns:
        str | None: The LLM's explanation as a string, or None if an error occurred.
    """
    prompt = f"""
You are Codex Prime, an AI assistant helping a user understand code errors.
Please explain the error message below in the context of the provided code.
Focus on:
1. What the error means in simple terms
2. What part of the code is causing the error
3. How to fix the issue

**Code:**
```
{code_snippet}
```

**Error Message:**
```
{error_message}
```
"""
    return _send_prompt(model, prompt)


def generate_unit_tests(model: genai.GenerativeModel, code_to_test: str, language: str = "python") -> str | None:
    """
    Asks the LLM to generate unit tests for the provided code.

    Args:
        model (genai.GenerativeModel): The initialized Gemini model instance.
        code_to_test (str): The code to generate tests for.
        language (str, optional): The programming language of the code.

    Returns:
        str | None: The LLM's generated unit tests as a string, or None if an error occurred.
    """
    prompt = f"""
You are Codex Prime, an AI assistant helping a user write unit tests.
Please generate comprehensive unit tests for the following {language} code.
Focus on:
1. Testing both typical and edge cases
2. Testing expected failures/exceptions
3. Testing with different input values
4. Following best practices for {language} unit testing

**Code to Test:**
```
{code_to_test}
```
"""
    return _send_prompt(model, prompt)


def explain_code_section(model: genai.GenerativeModel, code_section: str, specific_question: str = None) -> str | None:
    """
    Asks the LLM to explain a specific section of code.

    Args:
        model (genai.GenerativeModel): The initialized Gemini model instance.
        code_section (str): The code section to explain.
        specific_question (str, optional): A specific question about the code.

    Returns:
        str | None: The LLM's explanation as a string, or None if an error occurred.
    """
    question_text = f"\nPlease focus specifically on answering this question: {specific_question}" if specific_question else ""
    
    prompt = f"""
You are Codex Prime, an AI assistant helping a user understand code.
Please provide a clear explanation of the following code section.
Break down the logic, describe what it does, and explain any complex or non-obvious parts.{question_text}

**Code Section:**
```
{code_section}
```
"""
    return _send_prompt(model, prompt)


def process_user_request(model: genai.GenerativeModel, user_query: str, repo_context: dict, repo_name: str) -> dict:
    """
    Processes a general user request about code, determining the intent and providing
    an appropriate response structure.

    Args:
        model (genai.GenerativeModel): The initialized Gemini model instance.
        user_query (str): The user's question or request.
        repo_context (dict): Context about the repository structure and contents.
        repo_name (str): The name of the current repository.

    Returns:
        dict: A structured response containing:
            - 'action': The type of action to take (explain, modify, execute, etc.)
            - Additional fields based on the action type
    """
    # First, determine the user's intent using the LLM
    context_summary = f"Repository: {repo_name}\n"
    if "structure" in repo_context:
        context_summary += f"Structure: {repo_context['structure'][:500]}...\n"  # Truncate if very large
    
    intent_prompt = f"""
You are Codex Prime, an AI assistant helping with code repositories.
Based on the user's query and repository context, classify what the user wants to do.

**Repository Context:**
{context_summary}

**User Query:**
{user_query}

Identify the most appropriate action category:
1. explain - User wants information, explanation, or analysis
2. modify - User wants to change code or create new code
3. execute - User wants to run code or commands
4. git_commit - User wants to commit changes
5. git_push - User wants to push changes
6. git_branch - User wants to create or switch branches
7. git_pull - User wants to pull changes
8. git_status - User wants to see repository status
9. clarify - User's request is unclear and needs clarification
10. error - User's request cannot be fulfilled

Return ONLY a JSON object with:
- action: One of the above action categories
- additional fields specific to that action (e.g., file path for modify, command for execute)
- reason: Brief explanation of your classification
"""

    intent_response = _send_prompt(model, intent_prompt)
    
    # Parse the intent response to get JSON
    try:
        import json
        import re
        
        # Extract JSON from the response (it might be wrapped in markdown code blocks)
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', intent_response)
        json_str = json_match.group(1) if json_match else intent_response
        
        # Try to parse the JSON
        action_dict = json.loads(json_str)
        
        # For safety, ensure the action is one of our expected values
        valid_actions = ['explain', 'modify', 'execute', 'git_commit', 'git_push', 
                         'git_branch', 'git_pull', 'git_status', 'clarify', 'error']
        if 'action' not in action_dict or action_dict['action'] not in valid_actions:
            return {
                'action': 'error',
                'content': f"Could not determine appropriate action from LLM response. Got: {action_dict.get('action', 'unknown')}"
            }
        
        # For explain and clarify actions, we need to get detailed content
        if action_dict['action'] in ['explain', 'clarify']:
            content_prompt = f"""
You are Codex Prime, an AI assistant helping with code repositories.
Please provide a detailed and helpful response to the user's query.

**Repository Context:**
{context_summary}

**User Query:**
{user_query}

Provide a clear, concise, and informative response that addresses the user's question
or request. Include code examples where appropriate.
"""
            content_response = _send_prompt(model, content_prompt)
            action_dict['content'] = content_response
        
        # For modify action, we need to get the code changes
        elif action_dict['action'] == 'modify':
            if 'file' not in action_dict:
                # If file path wasn't specified in the intent, try to determine it
                action_dict['file'] = action_dict.get('file', "")  # Default to empty string if not present
            
            # Get the current file content if it exists in the repo context
            current_content = repo_context.get('file_contents', {}).get(action_dict['file'], "")
            
            modify_prompt = f"""
You are Codex Prime, an AI assistant helping with code repositories.
The user wants to modify code based on this query: "{user_query}"

**Current File Content:**
```
{current_content}
```

Please provide the complete new content for the file.
Return ONLY the code with no explanations or markdown formatters.
"""
            new_code = _send_prompt(model, modify_prompt)
            
            # Remove any markdown code blocks if present
            code_match = re.search(r'```(?:\w+)?\s*([\s\S]*?)\s*```', new_code)
            action_dict['code'] = code_match.group(1) if code_match else new_code
        
        # For execute action, we need to get the command to run
        elif action_dict['action'] == 'execute':
            if 'command' not in action_dict:
                execute_prompt = f"""
You are Codex Prime, an AI assistant helping with code repositories.
The user wants to execute code based on this query: "{user_query}"

Based on the repository context and user query, provide:
1. A specific command or script to execute
2. The language of the script (e.g., "python", "bash", "shell")
3. A brief explanation of what the command/script does

Format your response as a JSON object with fields:
- command: The command or script content
- language: The language of the script
- reason: Explanation of what it does
"""
                execute_response = _send_prompt(model, execute_prompt)
                
                # Extract JSON from the response
                json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', execute_response)
                execute_json_str = json_match.group(1) if json_match else execute_response
                
                try:
                    execute_dict = json.loads(execute_json_str)
                    action_dict.update(execute_dict)
                except json.JSONDecodeError:
                    # If we can't parse JSON, extract command using regex
                    command_match = re.search(r'command["\s:]+([^"\n]+)', execute_response)
                    if command_match:
                        action_dict['command'] = command_match.group(1)
                    else:
                        action_dict['command'] = "echo 'Could not parse command from LLM response'"
                    action_dict['reason'] = "Command extracted from non-JSON response"
        
        # Return the final action dictionary
        return action_dict
        
    except Exception as e:
        logger.error(f"Error processing user request: {e}", exc_info=True)
        return {
            'action': 'error',
            'content': f"An error occurred while processing your request: {str(e)}"
        }


class LLMHandler:
    """
    Main class for handling interactions with the LLM.
    Provides a unified interface for the main application to use.
    """
    
    def __init__(self, model: genai.GenerativeModel):
        """
        Initialize the LLM handler with a configured model.
        
        Args:
            model (genai.GenerativeModel): An initialized Gemini model instance
        """
        self.model = model
        logger.info("LLM handler initialized")
    
    def process_user_request(self, user_query: str, repo_context: dict, repo_name: str) -> dict:
        """
        Process a user request and return a structured response.
        
        Args:
            user_query (str): The user's question or request
            repo_context (dict): Context about the repository
            repo_name (str): Name of the current repository
            
        Returns:
            dict: A structured response with action and content
        """
        return process_user_request(self.model, user_query, repo_context, repo_name)
    
    def analyze_code(self, code_context: str, user_query: str) -> str:
        """
        Analyze code based on a user query.
        
        Args:
            code_context (str): The code context to analyze
            user_query (str): The specific question about the code
            
        Returns:
            str: The LLM's analysis
        """
        return analyze_code(self.model, code_context, user_query)
    
    def suggest_improvements(self, code_snippet: str, improvement_goal: str = None) -> str:
        """
        Suggest improvements for code.
        
        Args:
            code_snippet (str): The code to improve
            improvement_goal (str, optional): Focus area for improvements
            
        Returns:
            str: Suggested improvements
        """
        return suggest_code_improvements(self.model, code_snippet, improvement_goal)
    
    def explain_error(self, code_snippet: str, error_message: str) -> str:
        """
        Explain an error in the context of code.
        
        Args:
            code_snippet (str): The code that produced the error
            error_message (str): The error message
            
        Returns:
            str: Explanation of the error
        """
        return explain_error(self.model, code_snippet, error_message)
    
    def generate_unit_tests(self, code_to_test: str, language: str = "python") -> str:
        """
        Generate unit tests for code.
        
        Args:
            code_to_test (str): The code to test
            language (str, optional): The programming language
            
        Returns:
            str: Generated unit tests
        """
        return generate_unit_tests(self.model, code_to_test, language)
    
    def explain_code_section(self, code_section: str, specific_question: str = None) -> str:
        """
        Explain a specific section of code.
        
        Args:
            code_section (str): The code to explain
            specific_question (str, optional): A specific question about the code
            
        Returns:
            str: Explanation of the code
        """
        return explain_code_section(self.model, code_section, specific_question)


# For testing the module directly
if __name__ == "__main__":
    print("Initializing LLM handler for testing...")
    model = initialize_gemini()
    
    if model:
        handler = LLMHandler(model)
        
        # Test code analysis
        test_code = """
def factorial(n):
    if n <= 1:
        return 1
    return n * factorial(n-1)
        """
        
        print("\nTest 1: Code Analysis")
        result = handler.analyze_code(test_code, "What does this function do and are there any potential issues?")
        print(result)
        
        print("\nTest 2: Code Improvement Suggestions")
        result = handler.suggest_improvements(test_code, "performance and safety")
        print(result)
        
        print("\nTest 3: Processing User Request")
        mock_repo_context = {
            "structure": "factorial.py",
            "file_contents": {"factorial.py": test_code}
        }
        result = handler.process_user_request("Can you explain the factorial function and suggest how to handle negative inputs?", 
                                              mock_repo_context, "test-repo")
        print(f"Action: {result.get('action')}")
        print(f"Content: {result.get('content', '')[:200]}...")  # Show just the beginning
        
    else:
        print("Failed to initialize LLM model. Check your API key and connectivity.")
