# -*- coding: utf-8 -*-
"""
repo_handler.py

Manages interactions with both the GitHub API (PyGithub) for fetching
repository data/content and local Git operations (gitpython) like
commit, push, branch creation.
Part of the 'Codex Prime' project.
"""

import os
import logging
from github import Github, GithubException, UnknownObjectException
from git import Repo, GitCommandError, InvalidGitRepositoryError, NoSuchPathError
from dotenv import load_dotenv

# --- Setup ---

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables from .env file
load_dotenv()
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

# Initialize GitHub client globally
g = None
if not GITHUB_TOKEN:
    logger.error("GITHUB_TOKEN not found in environment variables. Please set it in your .env file.")
    # Depending on application flow, might raise an error or exit here
else:
    try:
        g = Github(GITHUB_TOKEN)
        # Verify authentication by getting the user
        user = g.get_user()
        logger.info(f"Successfully authenticated with GitHub as user: {user.login}")
    except GithubException as e:
        logger.error(f"Failed to authenticate with GitHub using the provided token: {e}")
        g = None # Indicate failure
    except Exception as e:
        logger.error(f"An unexpected error occurred during GitHub authentication: {e}")
        g = None


# --- GitHub API Functions ---

def get_user_repos():
    """
    Fetches the authenticated user's repositories from GitHub.

    Returns:
        list[str]: A list of repository full names (e.g., 'username/repo_name')
                   Returns an empty list if authentication failed or an error occurred.
    """
    if not g:
        logger.error("GitHub client is not initialized. Cannot fetch repositories.")
        return []
    try:
        user = g.get_user()
        repos = user.get_repos()
        repo_full_names = [repo.full_name for repo in repos]
        logger.info(f"Found {len(repo_full_names)} repositories for user {user.login}.")
        return repo_full_names
    except GithubException as e:
        logger.error(f"Could not fetch repositories from GitHub: {e}")
        return []
    except Exception as e:
        logger.error(f"An unexpected error occurred while fetching repositories: {e}")
        return []

def get_repo_contents(repo_full_name, path=""):
    """
    Fetches the contents (files and directories) of a specific path within a GitHub repository.

    Args:
        repo_full_name (str): The full name of the repository (e.g., 'username/repo_name').
        path (str, optional): The path within the repository to fetch contents from.
                               Defaults to the root directory ("").

    Returns:
        list[dict] | None: A list of dictionaries, each representing a file or directory.
                           Returns None if the repository/path is not found or an error occurs.
                           Each dictionary contains keys like 'name', 'path', 'type', 'sha', 'size', 'url'.
    """
    if not g:
        logger.error("GitHub client is not initialized. Cannot fetch repository contents.")
        return None
    try:
        logger.info(f"Fetching contents for {repo_full_name} at path '{path or '/'}'...")
        repo = g.get_repo(repo_full_name)
        contents = repo.get_contents(path)

        content_list = []
        # If path points to a file, get_contents returns a single ContentFile object
        if not isinstance(contents, list):
            contents = [contents]

        for item in contents:
            content_list.append({
                "name": item.name,
                "path": item.path,
                "type": item.type,  # 'file' or 'dir'
                "sha": item.sha,
                "size": item.size,
                "url": item.html_url
            })
        logger.info(f"Successfully fetched {len(content_list)} items from {repo_full_name} at path '{path or '/'}'")
        return content_list
    except UnknownObjectException:
        logger.error(f"Path '{path or '/'}' not found in repository '{repo_full_name}'. It might be a file, try get_file_content.")
        return None
    except GithubException as e:
        logger.error(f"Could not fetch contents for {repo_full_name} at path '{path or '/'}': {e}")
        return None
    except Exception as e:
        logger.error(f"An unexpected error occurred fetching contents for {repo_full_name}: {e}")
        return None

def get_file_content(repo_full_name, file_path):
    """
    Fetches the content of a specific file within a GitHub repository.

    Args:
        repo_full_name (str): The full name of the repository (e.g., 'username/repo_name').
        file_path (str): The path to the file within the repository.

    Returns:
        str | None: The decoded content of the file as a string.
                    Returns None if the file is not found, is a directory, or an error occurs.
    """
    if not g:
        logger.error("GitHub client is not initialized. Cannot fetch file content.")
        return None
    try:
        logger.info(f"Fetching file content for {repo_full_name} at path '{file_path}'...")
        repo = g.get_repo(repo_full_name)
        file_content = repo.get_contents(file_path)

        # Ensure it's a file and not a directory listing
        if isinstance(file_content, list):
             logger.error(f"Path '{file_path}' in {repo_full_name} is a directory, not a file.")
             return None
        if file_content.type != 'file':
             logger.error(f"Path '{file_path}' in {repo_full_name} is not a file (type: {file_content.type}).")
             return None

        # Decode content (usually base64 encoded by GitHub API)
        decoded_content = file_content.decoded_content.decode('utf-8')
        logger.info(f"Successfully fetched content for file: {file_path}")
        return decoded_content
    except UnknownObjectException:
        logger.error(f"File path '{file_path}' not found in repository '{repo_full_name}'.")
        return None
    except GithubException as e:
        # Handle potential rate limiting or other API errors
        logger.error(f"Could not fetch file content for {file_path} in {repo_full_name}: {e}")
        return None
    except Exception as e:
        logger.error(f"An unexpected error occurred fetching file content for {file_path}: {e}")
        return None


# --- Local File System & Git Functions ---

def apply_file_modification(file_path, new_content):
    """
    Overwrites a local file with new content.

    Args:
        file_path (str): The absolute or relative path to the local file.
        new_content (str): The new content to write to the file.

    Returns:
        bool: True if the file was written successfully, False otherwise.
    """
    try:
        logger.info(f"Applying modification to local file: {file_path}")
        # Ensure directory exists if it's part of the path (optional, depends on use case)
        # dir_name = os.path.dirname(file_path)
        # if dir_name:
        #     os.makedirs(dir_name, exist_ok=True)

        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        logger.info(f"Successfully wrote new content to {file_path}")
        return True
    except IOError as e:
        logger.error(f"Failed to write to file {file_path}: {e}")
        return False
    except Exception as e:
        logger.error(f"An unexpected error occurred applying file modification to {file_path}: {e}")
        return False

def create_new_branch(repo_path, branch_name):
    """
    Creates a new local Git branch in the specified repository.

    Args:
        repo_path (str): The path to the local Git repository.
        branch_name (str): The name for the new branch.

    Returns:
        bool: True if the branch was created successfully, False otherwise.
    """
    try:
        repo = Repo(repo_path)
        if branch_name in repo.heads:
            logger.warning(f"Branch '{branch_name}' already exists in {repo_path}. Checking it out.")
            repo.heads[branch_name].checkout()
            return True # Or False depending on whether "creation" is strict

        logger.info(f"Creating new branch '{branch_name}' in repository: {repo_path}")
        new_branch = repo.create_head(branch_name)
        new_branch.checkout() # Switch to the new branch after creation
        logger.info(f"Successfully created and checked out branch '{branch_name}'.")
        return True
    except InvalidGitRepositoryError:
        logger.error(f"Path '{repo_path}' is not a valid Git repository.")
        return False
    except NoSuchPathError:
        logger.error(f"Repository path '{repo_path}' does not exist.")
        return False
    except GitCommandError as e:
        logger.error(f"Git command failed during branch creation in {repo_path}: {e}")
        return False
    except Exception as e:
        logger.error(f"An unexpected error occurred creating branch in {repo_path}: {e}")
        return False

def commit_and_push_changes(repo_path, message, branch_name):
    """
    Stages all changes, commits them, and pushes the specified branch to the 'origin' remote.

    Args:
        repo_path (str): The path to the local Git repository.
        message (str): The commit message.
        branch_name (str): The name of the branch to commit to and push.

    Returns:
        bool: True if the commit and push were successful, False otherwise.
    """
    try:
        repo = Repo(repo_path)
        # Ensure we are on the correct branch
        if repo.active_branch.name != branch_name:
            logger.warning(f"Not on branch '{branch_name}', checking it out first.")
            if branch_name not in repo.heads:
                 logger.error(f"Branch '{branch_name}' does not exist locally. Cannot commit.")
                 return False
            repo.heads[branch_name].checkout()
            logger.info(f"Switched to branch '{branch_name}'.")

        # Check for uncommitted changes before staging
        if not repo.is_dirty(untracked_files=True):
            logger.info("No changes detected to commit.")
            # Optionally push even if no changes were committed locally
            # pass # Continue to push attempt
            return True # Or indicate no action needed

        logger.info(f"Staging changes in repository: {repo_path}")
        # Stage all changes (tracked and untracked)
        repo.git.add(A=True) # Equivalent to git add -A

        logger.info(f"Committing changes with message: '{message}'")
        repo.index.commit(message)
        logger.info("Commit successful.")

        # Push the branch to the remote 'origin'
        logger.info(f"Pushing branch '{branch_name}' to remote 'origin'...")
        origin = repo.remote(name='origin')

        # Use --set-upstream for the first push of a branch if needed
        # Check if the upstream is already set
        try:
             upstream_branch = repo.active_branch.tracking_branch()
             if not upstream_branch:
                 logger.info(f"Setting upstream for branch '{branch_name}' to 'origin/{branch_name}'.")
                 push_result = origin.push(refspec=f'{branch_name}:{branch_name}', set_upstream=True)
             else:
                 push_result = origin.push(refspec=f'{branch_name}:{branch_name}')
        except AttributeError: # Handle cases where tracking_branch() might fail if no remote exists etc.
             logger.info(f"Setting upstream for branch '{branch_name}' to 'origin/{branch_name}'.")
             push_result = origin.push(refspec=f'{branch_name}:{branch_name}', set_upstream=True)


        # Check push results for errors (GitPython push returns list of PushInfo objects)
        push_failed = False
        for info in push_result:
            if info.flags & info.ERROR:
                logger.error(f"Failed to push branch '{branch_name}': {info.summary}")
                push_failed = True
            elif info.flags & info.REJECTED:
                 logger.error(f"Push for branch '{branch_name}' rejected: {info.summary}. Need to pull first?")
                 push_failed = True
            else:
                logger.info(f"Push summary for {info.local_ref} -> {info.remote_ref_string}: {info.summary}")

        if push_failed:
            return False

        logger.info(f"Successfully pushed branch '{branch_name}' to origin.")
        return True

    except InvalidGitRepositoryError:
        logger.error(f"Path '{repo_path}' is not a valid Git repository.")
        return False
    except NoSuchPathError:
        logger.error(f"Repository path '{repo_path}' does not exist.")
        return False
    except GitCommandError as e:
        logger.error(f"Git command failed during commit/push in {repo_path}: {e}")
        # Provide more specific feedback if possible
        if "nothing to commit" in str(e).lower():
             logger.info("Caught 'nothing to commit' error, proceeding as success (or push only).")
             # Decide if push should still happen
             # For now, let's return True if commit failed due to no changes
             return True # Or handle push separately
        return False
    except ValueError as e: # Can happen if remote 'origin' doesn't exist
        logger.error(f"Configuration error in {repo_path} (e.g., remote 'origin' not found): {e}")
        return False
    except Exception as e:
        logger.error(f"An unexpected error occurred during commit/push in {repo_path}: {e}")
        return False

# --- Example Usage (Optional - for testing) ---
if __name__ == "__main__":
    logger.info("Repo Handler - Example Usage")

    if not g:
        logger.warning("GitHub client not initialized. Skipping GitHub API examples.")
    else:
        print("\nFetching repositories...")
        my_repos = get_user_repos()
        if my_repos:
            print(f"Found repositories: {my_repos[:5]}...") # Print first 5
            test_repo_full_name = my_repos[0] # Use the first repo for further tests

            print(f"\nFetching root contents for: {test_repo_full_name}")
            contents = get_repo_contents(test_repo_full_name)
            if contents:
                print(f"Found {len(contents)} items in root.")
                # Find a file to test content fetching
                test_file = next((item for item in contents if item['type'] == 'file'), None)
                if test_file:
                    print(f"\nFetching content for file: {test_file['path']}")
                    file_content = get_file_content(test_repo_full_name, test_file['path'])
                    if file_content:
                        print(f"Content (first 100 chars):\n{file_content[:100]}...")
                    else:
                        print("Could not fetch file content.")
                else:
                    print("No files found in the root directory to test content fetching.")
            else:
                print("Could not fetch repository contents.")
        else:
            print("Could not fetch user repositories.")

    # --- Local Git Example (Requires a local repo setup) ---
    # IMPORTANT: Set this path to a real local Git repository for testing
    local_repo_path = "./test_repo" # CHANGE THIS PATH

    if os.path.exists(local_repo_path) and os.path.isdir(os.path.join(local_repo_path, '.git')):
        print(f"\nTesting local Git operations on: {local_repo_path}")

        # 1. Modify a file (create one if it doesn't exist)
        test_file_local_path = os.path.join(local_repo_path, "codex_prime_test.txt")
        modification_success = apply_file_modification(
            test_file_local_path,
            f"File modified by repo_handler.py at {__import__('datetime').datetime.now()}\n"
        )
        if modification_success:
            print(f"Successfully modified/created: {test_file_local_path}")

            # 2. Create a new branch
            new_branch = "codex-prime-test-branch"
            branch_created = create_new_branch(local_repo_path, new_branch)

            if branch_created:
                print(f"Successfully created and checked out branch: {new_branch}")

                # 3. Commit and Push
                commit_message = "Test commit from Codex Prime repo_handler"
                pushed = commit_and_push_changes(local_repo_path, commit_message, new_branch)

                if pushed:
                    print("Successfully committed and pushed changes.")
                else:
                    print("Commit and push failed.")
            else:
                print("Failed to create new branch.")
        else:
            print(f"Failed to modify file: {test_file_local_path}")

    else:
        print(f"\nSkipping local Git tests. Path '{local_repo_path}' is not a valid Git repository.")
        print("Please clone a repository to './test_repo' or change 'local_repo_path' to test.")