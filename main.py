# main.py
# Main application entry point for Codex Prime.

import os
import sys
import logging
import subprocess
from dotenv import load_dotenv

# Third-party libraries
import google.generativeai as genai
from github import Github, GithubException
from git import Repo, GitCommandError
# Choose one UI library: prompt_toolkit is generally more powerful
from prompt_toolkit import PromptSession, print_formatted_text
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.styles import Style
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.validation import Validator, ValidationError
from prompt_toolkit.shortcuts import radiolist_dialog, message_dialog, button_dialog, input_dialog, yes_no_dialog

# Project modules (ensure these files exist in the specified structure)
try:
    from ui import TerminalUI # Assuming ui.py provides a TerminalUI class
    from repo_handler import RepoHandler
    from llm_handler import LLMHandler
    from executor import Executor
except ImportError as e:
    print(f"Error importing project modules: {e}", file=sys.stderr)
    print("Please ensure ui.py, repo_handler.py, llm_handler.py, and executor.py exist.", file=sys.stderr)
    sys.exit(1)

# --- Configuration ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
# Suppress noisy logs from libraries if needed
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("github").setLevel(logging.WARNING)

# --- Constants ---
DEFAULT_CLONE_DIR = os.path.join(os.path.expanduser("~"), "codex_prime_repos")
CONFIG_KEYS = ["GITHUB_TOKEN", "GEMINI_API_KEY"]

# --- Helper Functions ---

def load_config():
    """Loads configuration from .env file."""
    logging.info("Loading configuration from .env file...")
    load_dotenv()
    config = {}
    missing_keys = []
    for key in CONFIG_KEYS:
        value = os.getenv(key)
        if not value:
            missing_keys.append(key)
        config[key.lower()] = value # Store keys in lowercase

    if missing_keys:
        logging.error(f"Missing required environment variables: {', '.join(missing_keys)}")
        print(f"Error: Missing required environment variables in .env: {', '.join(missing_keys)}", file=sys.stderr)
        sys.exit(1)

    config['clone_dir'] = os.getenv("CLONE_DIR", DEFAULT_CLONE_DIR)
    os.makedirs(config['clone_dir'], exist_ok=True) # Ensure clone directory exists

    logging.info("Configuration loaded successfully.")
    return config

def initialize_services(config):
    """Initializes API clients and handlers."""
    logging.info("Initializing services...")
    try:
        # GitHub
        github_client = Github(config['github_token'])
        # Test connection
        _ = github_client.get_user().login
        logging.info("GitHub client initialized successfully.")

        # Gemini
        genai.configure(api_key=config['gemini_api_key'])
        # Adjust safety settings and generation config as needed
        safety_settings = [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
        ]
        generation_config = {
            "temperature": 0.7, # Adjust creativity/determinism
            "top_p": 1.0,
            "top_k": 32,
            "max_output_tokens": 8192, # Adjust based on model limits and needs
        }
        gemini_model = genai.GenerativeModel(
            model_name="gemini-1.5-flash", # Or choose another appropriate model
            generation_config=generation_config,
            safety_settings=safety_settings
        )
        logging.info(f"Gemini client initialized successfully (Model: {gemini_model.model_name}).")

        # Handlers
        repo_handler = RepoHandler(github_client, config['clone_dir'])
        llm_handler = LLMHandler(gemini_model)
        executor = Executor() # Consider passing config if needed (e.g., Docker settings)
        ui = TerminalUI() # Initialize the UI handler

        logging.info("All services initialized.")
        return ui, repo_handler, llm_handler, executor

    except GithubException as e:
        logging.error(f"GitHub initialization failed: {e.status} - {e.data.get('message', 'Unknown error')}")
        print(f"Error: Failed to initialize GitHub client. Check your GITHUB_TOKEN. Details: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        # Catch potential Gemini API errors or other issues
        logging.error(f"Service initialization failed: {e}", exc_info=True)
        print(f"Error: Failed to initialize services. Details: {e}", file=sys.stderr)
        sys.exit(1)

def run_interaction_loop(ui: TerminalUI, repo_handler: RepoHandler, llm_handler: LLMHandler, executor: Executor):
    """Runs the main interaction loop with the user."""
    logging.info("Starting interaction loop.")
    ui.display_welcome_message()

    current_repo_path = None
    current_repo_name = None

    while True: # Main loop
        try:
            # --- Repository Selection Phase ---
            if not current_repo_path:
                repo_name, repo_path = select_repository(ui, repo_handler)
                if not repo_name: # User chose to exit
                    break
                current_repo_name = repo_name
                current_repo_path = repo_path
                ui.display_message(f"Switched context to repository: {current_repo_name}")

            # --- Command Input Phase ---
            user_input = ui.get_user_input(f"CodexPrime ({current_repo_name})> ")

            if not user_input:
                continue # Handle empty input

            if user_input.lower() in ["exit", "quit", "q"]:
                logging.info("Exit command received. Shutting down.")
                break

            if user_input.lower() in ["change repo", "switch repo", "select repo"]:
                current_repo_path = None # Trigger repo selection again
                continue

            # --- Processing Phase ---
            ui.display_message("Processing your request...", style="italic #aaaaaa")

            # 1. Gather Context (can be optimized to do this only when needed)
            try:
                context = repo_handler.get_repository_context(current_repo_path)
                if not context or not context.get("structure"):
                     ui.display_warning("Could not gather repository context. Analysis might be limited.")
                     context = context or {} # Ensure context is a dict
            except Exception as e:
                logging.error(f"Failed to get repository context for {current_repo_path}: {e}", exc_info=True)
                ui.display_error(f"Error getting repository context: {e}")
                context = {} # Proceed with empty context

            # 2. Process with LLM
            try:
                llm_response = llm_handler.process_user_request(user_input, context, current_repo_name)
                # llm_response should be a structured dictionary, e.g.:
                # {'action': 'explain', 'content': 'Explanation text...'}
                # {'action': 'modify', 'file': 'path/to/file.py', 'code': 'new code...', 'reason': '...'}
                # {'action': 'execute', 'command': 'python script.py', 'reason': '...'}
                # {'action': 'git_commit', 'message': 'Commit message', 'files': ['file1.py']}
                # {'action': 'git_push'}
                # {'action': 'git_branch', 'name': 'feature/new-thing'}
                # {'action': 'error', 'content': 'Could not understand...'}
                # {'action': 'clarify', 'content': 'Need more info...'}

            except Exception as e:
                logging.error(f"LLM processing failed: {e}", exc_info=True)
                ui.display_error(f"Error processing request with LLM: {e}")
                continue # Ask for new input

            # 3. Dispatch Action
            action = llm_response.get('action', 'error')
            content = llm_response.get('content', '') # General content/explanation/error message

            if action == 'explain' or action == 'clarify':
                ui.display_llm_response(content)
            elif action == 'error':
                 ui.display_error(content or "Sorry, I couldn't process that request.")
            elif action == 'modify':
                handle_code_modification(ui, repo_handler, llm_response, current_repo_path)
            elif action == 'execute':
                handle_code_execution(ui, executor, llm_response, current_repo_path)
            elif action.startswith('git_'):
                handle_git_operation(ui, repo_handler, llm_response, current_repo_path)
            else:
                ui.display_error(f"Unknown action received from LLM: {action}")
                logging.warning(f"Received unknown action '{action}' from LLM.")

        except KeyboardInterrupt:
            logging.info("Keyboard interrupt received. Exiting.")
            break
        except EOFError: # Handle Ctrl+D
             logging.info("EOF detected. Exiting.")
             break
        except Exception as e:
            logging.error(f"An unexpected error occurred in the main loop: {e}", exc_info=True)
            ui.display_error(f"An unexpected error occurred: {e}")
            # Decide whether to continue or exit on unexpected errors
            # continue

    ui.display_message("Exiting Codex Prime. Goodbye!")
    logging.info("Interaction loop finished.")


def select_repository(ui: TerminalUI, repo_handler: RepoHandler):
    """Handles the repository selection process."""
    while True:
        try:
            ui.display_message("Fetching your repositories...", style="italic #aaaaaa")
            repos = repo_handler.list_repositories() # Returns list of repo names or dicts
            if not repos:
                ui.display_error("Could not find any repositories or failed to fetch them.")
                if ui.ask_yes_no("Retry fetching repositories?"):
                    continue
                else:
                    return None, None # Indicate exit

            # Format for radiolist_dialog: list of (value, text) tuples
            repo_choices = [(repo_name, repo_name) for repo_name in repos]
            repo_choices.append(("__exit__", "[ Exit Codex Prime ]")) # Add exit option

            selected_repo_name = ui.select_repository(repo_choices)

            if not selected_repo_name or selected_repo_name == "__exit__":
                return None, None # User chose to exit

            ui.display_message(f"Cloning or updating '{selected_repo_name}'...", style="italic #aaaaaa")
            repo_path = repo_handler.clone_or_update_repo(selected_repo_name)
            if repo_path:
                ui.display_message(f"Repository ready at: {repo_path}", style="fg:green")
                return selected_repo_name, repo_path
            else:
                # Error handled within clone_or_update_repo, message displayed by UI
                if not ui.ask_yes_no("Failed to prepare repository. Try selecting another one?"):
                     return None, None # Exit

        except GithubException as e:
            logging.error(f"GitHub error during repository listing: {e}", exc_info=True)
            ui.display_error(f"GitHub error: {e.data.get('message', 'Failed to fetch repositories')}")
            if not ui.ask_yes_no("Retry fetching repositories?"):
                return None, None # Exit
        except GitCommandError as e:
             logging.error(f"Git error during clone/update: {e}", exc_info=True)
             ui.display_error(f"Git error: {e.stderr}")
             if not ui.ask_yes_no("Retry repository operation?"):
                 return None, None # Exit
        except Exception as e:
            logging.error(f"Error during repository selection: {e}", exc_info=True)
            ui.display_error(f"An unexpected error occurred: {e}")
            if not ui.ask_yes_no("An error occurred. Try again?"):
                return None, None # Exit


def handle_code_modification(ui: TerminalUI, repo_handler: RepoHandler, llm_response: dict, repo_path: str):
    """Handles the 'modify' action from the LLM."""
    file_path = llm_response.get('file')
    new_code = llm_response.get('code')
    reason = llm_response.get('reason', 'No reason provided.')

    if not file_path or new_code is None: # new_code can be empty string
        ui.display_error("LLM response for modification is incomplete (missing file path or code).")
        logging.warning(f"Incomplete modification response: {llm_response}")
        return

    full_file_path = os.path.join(repo_path, file_path)

    # Show diff or summary before asking for confirmation (optional but recommended)
    try:
        current_content = ""
        if os.path.exists(full_file_path):
             with open(full_file_path, 'r', encoding='utf-8') as f:
                 current_content = f.read()
        diff = repo_handler.generate_diff(current_content, new_code, file_path)
        ui.display_diff(diff, file_path)
        ui.display_message(f"Reason for change: {reason}")

    except Exception as e:
        logging.error(f"Error generating diff for {file_path}: {e}")
        ui.display_warning(f"Could not generate diff for {file_path}. Displaying full proposed code.")
        ui.display_code(new_code, file_path)
        ui.display_message(f"Reason for change: {reason}")


    if ui.ask_yes_no(f"Apply proposed changes to '{file_path}'?"):
        try:
            success = repo_handler.apply_code_changes(repo_path, file_path, new_code)
            if success:
                ui.display_message(f"Successfully modified '{file_path}'.", style="fg:green")
                # Suggest committing changes
                if ui.ask_yes_no("Do you want to commit this change now?"):
                     commit_message = ui.get_text_input(
                         title="Commit Message",
                         text=f"Modified {file_path} based on AI suggestion" # Default message
                     )
                     if commit_message:
                         handle_git_operation(ui, repo_handler, {
                             'action': 'git_commit',
                             'message': commit_message,
                             'files': [file_path] # Commit only the changed file
                         }, repo_path)
                     else:
                         ui.display_message("Commit cancelled.")

            else:
                # Error message should be displayed by apply_code_changes via UI
                pass
        except Exception as e:
            logging.error(f"Failed to apply changes to {file_path}: {e}", exc_info=True)
            ui.display_error(f"Error applying changes: {e}")
    else:
        ui.display_message("Modification cancelled.")


def handle_code_execution(ui: TerminalUI, executor: Executor, llm_response: dict, repo_path: str):
    """Handles the 'execute' action from the LLM."""
    command = llm_response.get('command')
    reason = llm_response.get('reason', 'No reason provided.')
    language = llm_response.get('language', 'shell') # e.g., python, shell

    if not command:
        ui.display_error("LLM response for execution is incomplete (missing command).")
        logging.warning(f"Incomplete execution response: {llm_response}")
        return

    ui.display_warning("Code execution can be dangerous. Review the command carefully.")
    ui.display_message(f"Command to execute (in context of {repo_path}):")
    ui.display_code(command, f"Language: {language}")
    ui.display_message(f"Reason: {reason}")

    if ui.ask_yes_no("Execute this command?"):
        ui.display_message("Executing command...", style="italic #aaaaaa")
        try:
            # Execute within the repository's directory
            # SECURITY: Ensure executor uses sandboxing (Docker, restricted env, etc.)
            # The current Executor implementation might use subprocess directly, which is RISKY.
            # This needs a robust sandboxing mechanism for production.
            exit_code, stdout, stderr = executor.execute_code(command, cwd=repo_path, language=language)

            ui.display_message(f"Execution finished with exit code: {exit_code}")
            if stdout:
                ui.display_output("Standard Output:", stdout)
            if stderr:
                ui.display_output("Standard Error:", stderr, style="fg:ansired") # Use red for errors

        except NotImplementedError as e:
             ui.display_error(f"Execution failed: {e}")
             logging.error(f"Execution attempt failed: {e}")
        except Exception as e:
            logging.error(f"Failed to execute command '{command}': {e}", exc_info=True)
            ui.display_error(f"Error during execution: {e}")
    else:
        ui.display_message("Execution cancelled.")


def handle_git_operation(ui: TerminalUI, repo_handler: RepoHandler, llm_response: dict, repo_path: str):
    """Handles various 'git_*' actions from the LLM."""
    action = llm_response.get('action')

    try:
        if action == 'git_commit':
            message = llm_response.get('message')
            files_to_add = llm_response.get('files') # Optional: LLM might suggest specific files
            if not message:
                ui.display_error("Commit message missing.")
                return

            # Always confirm Git actions
            if ui.ask_yes_no(f"Commit changes with message: '{message}'?"):
                success, output = repo_handler.commit_changes(repo_path, message, files_to_add)
                if success:
                    ui.display_message(f"Commit successful.\n{output}", style="fg:green")
                    # Ask if user wants to push
                    if ui.ask_yes_no("Push the commit(s) now?"):
                         handle_git_operation(ui, repo_handler, {'action': 'git_push'}, repo_path)
                else:
                    ui.display_error(f"Commit failed:\n{output}")
            else:
                ui.display_message("Commit cancelled.")

        elif action == 'git_push':
            if ui.ask_yes_no("Push changes to the remote repository?"):
                success, output = repo_handler.push_changes(repo_path)
                if success:
                    ui.display_message(f"Push successful.\n{output}", style="fg:green")
                else:
                    ui.display_error(f"Push failed:\n{output}")
            else:
                ui.display_message("Push cancelled.")

        elif action == 'git_branch':
            branch_name = llm_response.get('name')
            if not branch_name:
                ui.display_error("Branch name missing.")
                return
            if ui.ask_yes_no(f"Create and switch to new branch: '{branch_name}'?"):
                 success, output = repo_handler.create_branch(repo_path, branch_name, checkout=True)
                 if success:
                     ui.display_message(f"Switched to new branch '{branch_name}'.\n{output}", style="fg:green")
                 else:
                     ui.display_error(f"Failed to create/switch branch:\n{output}")
            else:
                 ui.display_message("Branch creation cancelled.")

        elif action == 'git_pull':
             if ui.ask_yes_no("Pull changes from the remote repository?"):
                 success, output = repo_handler.pull_changes(repo_path)
                 if success:
                     ui.display_message(f"Pull successful.\n{output}", style="fg:green")
                 else:
                     ui.display_error(f"Pull failed:\n{output}")
             else:
                 ui.display_message("Pull cancelled.")

        elif action == 'git_status':
             # No confirmation needed for status
             success, output = repo_handler.get_status(repo_path)
             if success:
                 ui.display_message("Git Status:", style="bold")
                 ui.display_message(output)
             else:
                 ui.display_error(f"Failed to get status:\n{output}")

        # Add more Git actions as needed (e.g., git_checkout, git_merge, git_pr)

        else:
            ui.display_error(f"Unsupported Git action: {action}")
            logging.warning(f"Unsupported Git action received: {action}")

    except GitCommandError as e:
        logging.error(f"Git command failed ({action}): {e}", exc_info=True)
        ui.display_error(f"Git error during '{action}':\n{e.stderr}")
    except Exception as e:
        logging.error(f"Error handling Git operation '{action}': {e}", exc_info=True)
        ui.display_error(f"An unexpected error occurred during '{action}': {e}")


# --- Main Execution ---
def main():
    """Main function to run the application."""
    try:
        config = load_config()
        ui, repo_handler, llm_handler, executor = initialize_services(config)
        run_interaction_loop(ui, repo_handler, llm_handler, executor)
    except SystemExit:
        # Raised by sys.exit() on config/init errors, already printed message.
        pass
    except Exception as e:
        # Catch-all for unexpected errors during startup before the main loop
        logging.critical(f"A critical error occurred during startup: {e}", exc_info=True)
        print(f"Critical Error: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        logging.info("Codex Prime finished.")

if __name__ == "__main__":
    main()