# ui.py
# Handles all interactive terminal UI elements for Codex Prime.

import os
import sys
from typing import List, Optional, Any

# Import prompt_toolkit components
from prompt_toolkit import prompt, print_formatted_text
from prompt_toolkit.shortcuts import radiolist_dialog, confirm, message_dialog
from prompt_toolkit.formatted_text import HTML, FormattedText
from prompt_toolkit.styles import Style

# --- UI Styling (Optional but Recommended) ---
# Define a basic style for prompts and outputs
# You can customize colors and attributes here
# See prompt_toolkit documentation for more options:
# https://python-prompt-toolkit.readthedocs.io/en/master/pages/styling.html
ui_style = Style.from_dict({
    'dialog':             'bg:#444444 #ffffff',
    'dialog frame.label': 'bg:#ffffff #000000',
    'dialog.body':        'bg:#888888 #000000',
    'dialog shadow':      'bg:#000000',
    'button':             'bg:#000000 #ffffff',
    'button.focused':     'bg:#ff0000 #000000 noinherit',
    'radiolist':          '#ffffff',
    'radiolist.current':  'bold underline #ffffff', # Highlight selected radio item
    'prompt':             '#00ff00 bold', # Green bold prompt
    'output':             '#ffffff',      # Default white output
    'error':              '#ff0000 bold', # Red bold error
    'info':               '#00ffff',      # Cyan info
    'warning':            '#ffff00',      # Yellow warning
})

# --- Core UI Functions ---

def display_repo_selection(repos: List[str]) -> Optional[str]:
    """
    Displays a list of repositories and allows the user to select one using arrow keys.

    Args:
        repos: A list of repository names (strings).

    Returns:
        The name of the selected repository, or None if the user cancels.
    """
    if not repos:
        message_dialog(
            title="No Repositories Found",
            text="Could not find any repositories to display.",
            style=ui_style
        ).run()
        return None

    # Format repositories for the radiolist_dialog: list of (value, text) tuples
    radio_options = [(repo_name, repo_name) for repo_name in repos]

    try:
        selected_repo = radiolist_dialog(
            title="Select Repository",
            text="Use arrow keys to navigate, Enter to select:",
            values=radio_options,
            style=ui_style
        ).run()
        return selected_repo
    except Exception as e:
        # Handle potential errors during dialog display gracefully
        print_formatted_text(HTML(f"<error>Error displaying repository selection: {e}</error>"), style=ui_style)
        return None

def get_user_command(prompt_message: str = "Codex Prime > ") -> Optional[str]:
    """
    Prompts the user for a natural language command.

    Args:
        prompt_message: The text to display before the user input cursor.

    Returns:
        The command entered by the user as a string, or None if input is interrupted (Ctrl+C/D).
    """
    try:
        # Use prompt_toolkit's prompt for potentially richer input experiences later
        user_input = prompt(HTML(f"<prompt>{prompt_message}</prompt>"), style=ui_style)
        return user_input.strip()
    except (EOFError, KeyboardInterrupt):
        # Handle Ctrl+D (EOFError) or Ctrl+C (KeyboardInterrupt) gracefully
        print_formatted_text(HTML("\n<warning>Input interrupted. Exiting command prompt.</warning>"), style=ui_style)
        return None
    except Exception as e:
        print_formatted_text(HTML(f"<error>Error getting user input: {e}</error>"), style=ui_style)
        return None

def display_output(text: Any, style_class: str = 'output'):
    """
    Displays text output to the terminal (e.g., responses, status updates, errors).

    Args:
        text: The text content to display. Can be a string or any object convertible to string.
        style_class: The style class to apply (e.g., 'output', 'error', 'info', 'warning').
                     Defaults to 'output'.
    """
    try:
        # Use print_formatted_text for consistent styling
        # Wrap the text in HTML tags corresponding to the style_class
        formatted_output = HTML(f"<{style_class}>{str(text)}</{style_class}>")
        print_formatted_text(formatted_output, style=ui_style)
    except Exception as e:
        # Fallback to basic print if formatting fails
        print(f"Error displaying output: {e}")
        print(str(text)) # Print the original text

def confirm_action(prompt_text: str = "Are you sure?") -> bool:
    """
    Asks the user a Yes/No question and returns the boolean result.

    Args:
        prompt_text: The question to ask the user (e.g., "Commit changes?").

    Returns:
        True if the user confirms (selects Yes), False otherwise (selects No or cancels).
    """
    try:
        # confirm returns True for Yes, False for No/Cancel
        result = confirm(
            title="Confirmation Needed",
            text=f"{prompt_text} (Y/N)",
            style=ui_style
        ).run()
        # Ensure we return False if result is None (e.g., user cancels dialog)
        return result if result is not None else False
    except Exception as e:
        print_formatted_text(HTML(f"<error>Error during confirmation prompt: {e}</error>"), style=ui_style)
        # Default to False (safer option) if confirmation fails
        return False

# --- Helper Functions (Optional) ---

def display_error(message: str):
    """Helper function to display error messages with consistent styling."""
    display_output(f"ERROR: {message}", style_class='error')

def display_info(message: str):
    """Helper function to display informational messages."""
    display_output(f"INFO: {message}", style_class='info')

def display_warning(message: str):
    """Helper function to display warning messages."""
    display_output(f"WARNING: {message}", style_class='warning')


# --- Example Usage (for testing purposes) ---
if __name__ == "__main__":
    # Clear screen for a cleaner demo (optional)
    # os.system('cls' if os.name == 'nt' else 'clear')

    print_formatted_text(HTML("<b>--- Codex Prime UI Test ---</b>"), style=ui_style)

    # 1. Test Repository Selection
    display_info("Testing Repository Selection...")
    mock_repos = ["my-awesome-project", "dotfiles", "ai-research-papers", "codex-prime-itself"]
    selected = display_repo_selection(mock_repos)
    if selected:
        display_output(f"You selected: {selected}")
    else:
        display_warning("Repository selection cancelled or failed.")

    print("-" * 20)

    # 2. Test User Command Input
    display_info("Testing User Command Input...")
    command = get_user_command("Enter your command: ")
    if command:
        display_output(f"You entered: '{command}'")
    else:
        display_warning("Command input cancelled or failed.")

    print("-" * 20)

    # 3. Test Output Display
    display_info("Testing Output Display Styles...")
    display_output("This is standard output.")
    display_info("This is an informational message.")
    display_warning("This is a warning message.")
    display_error("This is an error message.")

    print("-" * 20)

    # 4. Test Confirmation Prompt
    display_info("Testing Confirmation Prompt...")
    if confirm_action("Do you want to proceed with the test action?"):
        display_output("You confirmed the action.")
    else:
        display_warning("You cancelled the action.")

    print_formatted_text(HTML("<b>--- UI Test Complete ---</b>"), style=ui_style)