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

**Code Context:**