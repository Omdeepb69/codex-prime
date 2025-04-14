```python
# executor.py

import subprocess
import logging
import tempfile
import os
import shutil
import sys
from typing import Tuple, Optional

# Configure logging
# Consider configuring logging more robustly in a central place (e.g., main.py)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Security Warning ---
# Executing arbitrary commands or scripts received from an LLM or external source
# is EXTREMELY DANGEROUS and can lead to severe security vulnerabilities,
# including data loss, system compromise, and unauthorized access.
#
# The implementations below using `subprocess` provide basic execution capabilities
# but LACK ROBUST SANDBOXING. They execute commands/scripts with the same
# permissions as the 'Codex Prime' application itself.
#
# FOR PRODUCTION OR ANY ENVIRONMENT HANDLING UNTRUSTED CODE, YOU *MUST*
# IMPLEMENT STRONG SANDBOXING using technologies like:
#   - Docker containers (`docker-py` library): Isolate execution in a container.
#   - Virtual machines: Higher overhead but stronger isolation.
#   - gVisor: Application kernel providing container sandboxing.
#   - Dedicated sandboxing libraries (e.g., nsjail, firejail - platform-specific).
#
# DO NOT use this code in production without implementing proper security measures.
# Consider adding user confirmation steps before any execution.
# --- End Security Warning ---

DEFAULT_TIMEOUT = 120 # Default timeout for subprocess execution in seconds

def execute_command(command_string: str, working_directory: Optional[str] = None, timeout: int = DEFAULT_TIMEOUT) -> Tuple[Optional[str], Optional[str], Optional[int]]:
    """
    Executes a shell command string directly.

    Args:
        command_string: The command to execute (e.g., "git status", "ls -la").
        working_directory: The directory from which to execute the command.
                           Defaults to the current working directory if None.
        timeout: Maximum execution time in seconds.

    Returns:
        A tuple containing (stdout, stderr, return_code).
        - stdout (str | None): Standard output of the command, or None on pre-execution error.
        - stderr (str | None): Standard error of the command, or an error message on failure.
        - return_code (int | None): The exit code of the process, or None if the process
                                    didn't complete (timeout, pre-execution error).

    *** SECURITY WARNING: Executing arbitrary commands is highly insecure. Use with extreme caution. ***
    """
    logger.warning(f"Executing potentially unsafe command in '{working_directory or os.getcwd()}': {command_string}")
    if not command_string:
        logger.error("execute_command received an empty command string.")
        return None, "Error: Empty command string provided.", None

    try:
        # Use shell=True cautiously. It's needed for complex commands/pipelines/redirects
        # but increases security risks if command_string contains untrusted input.
        # Consider splitting the command using shlex if shell=False is feasible and safer.
        process = subprocess.run(
            command_string,
            shell=True,
            capture_output=True,
            text=True,
            cwd=working_directory, # Execute in the specified directory
            timeout=timeout,
            check=False # Don't raise CalledProcessError automatically, check returncode manually
        )
        stdout = process.stdout.strip() if process.stdout else ""
        stderr = process.stderr.strip() if process.stderr else ""
        logger.info(f"Command '{command_string}' executed with return code {process.returncode}")
        if stdout:
            logger.debug(f"Command stdout:\n{stdout}")
        if stderr:
            # Log stderr as warning, as it often indicates non-fatal issues or verbose errors
            logger.warning(f"Command stderr:\n{stderr}")
        return stdout, stderr, process.returncode

    except subprocess.TimeoutExpired:
        error_msg = f"Error: Command '{command_string}' timed out after {timeout} seconds."
        logger.error(error_msg)
        # Consider returning partial output if available: process.stdout, process.stderr
        return None, error_msg, None # Indicate timeout specifically
    except FileNotFoundError:
        # This error typically means the shell or the command itself wasn't found
        error_msg = f"Error executing command: Command or shell not found for '{command_string}'."
        logger.error(error_msg)
        return None, error_msg, None
    except OSError as e:
        # Catch other OS-level errors, e.g., permission denied to access working_directory
        error_msg = f"Error executing command '{command_string}': {e}"
        logger.error(error_msg)
        return None, error_msg, None
    except Exception as e:
        logger.exception(f"An unexpected error occurred during command execution: {command_string}")
        return None, f"An unexpected error occurred: {str(e)}", None


def execute_script(script_content: str, language: str = 'python', working_directory: Optional[str] = None, timeout: int = DEFAULT_TIMEOUT) -> Tuple[Optional[str], Optional[str], Optional[int]]:
    """
    Executes a script provided as a string by saving it to a temporary file.

    Args:
        script_content: The string content of the script.
        language: The language of the script (e.g., 'python', 'bash', 'sh').
                  Determines the interpreter used. Case-insensitive.
        working_directory: The directory from which to execute the script.
                           Defaults to the current working directory if None.
        timeout: Maximum execution time in seconds.

    Returns:
        A tuple containing (stdout, stderr, return_code).
        - stdout (str | None): Standard output of the script, or None on pre-execution error.
        - stderr (str | None): Standard error of the script, or an error message on failure.
        - return_code (int | None): The exit code of the script process, or None if the process
                                    didn't complete (timeout, setup error, pre-execution error).

    *** SECURITY WARNING: Executing arbitrary scripts is highly insecure. Use with extreme caution. ***
    """
    logger.warning(f"Executing potentially unsafe {language} script in '{working_directory or os.getcwd()}'.")
    if not script_content:
        logger.error("execute_script received empty script content.")
        return None, "Error: Empty script content provided.", None

    # Map language names to interpreter executables
    # Use sys.executable for Python to ensure it uses the same environment
    interpreter_map = {
        'python': sys.executable,
        'bash': 'bash', # Rely on PATH lookup
        'sh': 'sh',     # Rely on PATH lookup
        # Add other interpreters as needed (e.g., 'node': 'node', 'perl': 'perl')
    }

    lang_lower = language.lower()
    interpreter_cmd = interpreter_map.get(lang_lower)

    if not interpreter_cmd:
        error_msg = f"Error: Unsupported script language: {language}. Supported: {list(interpreter_map.keys())}"
        logger.error(error_msg)
        return None, error_msg, None

    # Find the full path of the interpreter
    interpreter_path = shutil.which(interpreter_cmd)
    if not interpreter_path:
         error_msg = f"Error: Interpreter command '{interpreter_cmd}' for language '{language}' not found in PATH."
         logger.error(error_msg)
         return None, error_msg, None

    temp_file_path = None
    try:
        # Create a temporary file to hold the script content
        # Suffix helps identify the file type, delete=False needed on Windows
        # and generally safer to manage deletion manually in `finally`.
        with tempfile.NamedTemporaryFile(mode='w', suffix=f'.{lang_lower}', delete=False, encoding='utf-8') as temp_script:
            temp_file_path = temp_script.name
            temp_script.write(script_content)
            # Ensure content is written before execution
            temp_script.flush()
            os.fsync(temp_script.fileno()) # Force write to disk

        logger.info(f"Executing {language} script from temporary file: {temp_file_path} using interpreter {interpreter_path}")

        # Execute the script using the determined interpreter
        process = subprocess.run(
            [interpreter_path, temp_file_path],
            capture_output=True,
            text=True,
            cwd=working_directory, # Execute in the specified directory
            timeout=timeout,
            check=False # Check returncode manually
        )

        stdout = process.stdout.strip() if process.stdout else ""
        stderr = process.stderr.strip() if process.stderr else ""
        logger.info(f"Script '{temp_file_path}' executed with return code {process.returncode}")
        if stdout:
            logger.debug(f"Script stdout:\n{stdout}")
        if stderr:
            logger.warning(f"Script stderr:\n{stderr}")
        return stdout, stderr, process.returncode

    except subprocess.TimeoutExpired:
        error_msg = f"Error: Script execution timed out after {timeout} seconds: {temp_file_path}"
        logger.error(error_msg)
        # Consider returning partial output if available
        return None, error_msg, None
    except FileNotFoundError:
        # This might happen if the interpreter path becomes invalid between check and execution,
        # or if the temporary file is somehow removed prematurely.
         error_msg = f"Error: Interpreter or script file not found during execution: {interpreter_path} or {temp_file_path}"
         logger.error(error_msg)
         return None, error_msg, None
    except OSError as e:
        # Catch other OS-level errors, e.g., permission denied
        error_msg = f"Error executing script '{temp_file_path}': {e}"
        logger.error(error_msg)
        return None, error_msg, None
    except Exception as e:
        logger.exception(f"An unexpected error occurred during script execution: {temp_file_path}")
        return None, f"An unexpected error occurred during script execution: {str(e)}", None
    finally:
        # Ensure the temporary file is always deleted
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
                logger.debug(f"Temporary script file deleted: {temp_file_path}")
            except OSError as e:
                # Log error but don't raise, as the primary operation might have succeeded/failed already
                logger.error(f"Error deleting temporary script file {temp_file_path}: {e}")


# Example Usage (Illustrative - Run cautiously)
if __name__ == '__main__':
    print("--- Executor Module Examples ---")
    print("*** WARNING: Running example code execution. Ensure you understand the commands/scripts. ***")

    # Create a temporary directory for testing execution context
    test_dir = tempfile.mkdtemp(prefix="codex_prime_executor_test_")
    print(f"\nCreated temporary directory for tests: {test_dir}")

    try:
        print("\n--- Testing execute_command ---")

        # Example 1: Simple command (platform-dependent listing)
        list_command = "ls -la" if os.name != 'nt' else "dir"
        print(f"\nExecuting: '{list_command}' in {test_dir}")
        stdout, stderr, retcode = execute_command(list_command, working_directory=test_dir)
        print(f"Return Code: {retcode}")
        print(f"Stdout:\n{stdout or '[No stdout]'}")
        print(f"Stderr:\n{stderr or '[No stderr]'}")

        # Example 2: Command writing to a file
        file_write_command = f"echo 'Hello from command' > test_output.txt"
        if os.name == 'nt': # Windows echo needs different handling for redirection sometimes
             file_write_command = f'cmd /c "echo Hello from command > test_output.txt"'
        print(f"\nExecuting: '{file_write_command}' in {test_dir}")
        stdout, stderr, retcode = execute_command(file_write_command, working_directory=test_dir)
        print(f"Return Code: {retcode}")
        print(f"Stdout:\n{stdout or '[No stdout]'}")
        print(f"Stderr:\n{stderr or '[No stderr]'}")
        # Verify file creation
        file_path = os.path.join(test_dir, "test_output.txt")
        if os.path.exists(file_path):
            with open(file_path, 'r') as f:
                print(f"Content of {file_path}: {f.read().strip()}")
        else:
            print(f"File {file_path} was not created.")


        # Example 3: Command with error
        print("\nExecuting: 'non_existent_command_123'")
        stdout, stderr, retcode = execute_command("non_existent_command_123", working_directory=test_dir)
        print(f"Return Code: {retcode}")
        print(f"Stdout:\n{stdout or '[No stdout]'}")
        print(f"Stderr:\n{stderr or '[No stderr]'}") # Should show an error

        # Example 4: Command timeout
        sleep_command = "sleep 3" if os.name != 'nt' else "timeout /t 3 /nobreak > NUL"
        print(f"\nExecuting: '{sleep_command}' (with 1s timeout)")
        stdout, stderr, retcode = execute_command(sleep_command, working_directory=test_dir, timeout=1)
        print(f"Return Code: {retcode}") # Should be None
        print(f"Stdout:\n{stdout or '[No stdout]'}")
        print(f"Stderr:\n{stderr or '[No stderr]'}") # Should indicate timeout

        print("\n--- Testing execute_script ---")

        # Example 5: Simple Python script
        python_code = """
import sys
import os
print(f"Hello from Python script in {os.getcwd()}!")
print(f"Python version: {sys.version_info.major}.{sys.version_info.minor}")
# Create a file in the execution directory
with open('python_script_output.txt', 'w') as f:
    f.write('Written by Python script.')
# Example of stderr output
# sys.stderr.write("This is a test error message from Python\\n")
"""
        print("\nExecuting Python script:")
        stdout, stderr, retcode = execute_script(python_code, language='python', working_directory=test_dir)
        print(f"Return Code: {retcode}")
        print(f"Stdout:\n{stdout or '[No stdout]'}")
        print(f"Stderr:\n{stderr or '[No stderr]'}")
        # Verify file creation by script
        script_file_path = os.path.join(test_dir, "python_script_output.txt")
        if os.path.exists(script_file_path):
            with open(script_file_path, 'r') as f:
                print(f"Content of {script_file_path}: {f.read().strip()}")
        else:
            print(f"File {script_file_path} was not created by script.")


        # Example 6: Simple Bash script (if on Linux/macOS)
        if os.name != 'nt':
            bash_code = """
#!/bin/bash
echo "Hello from Bash script in $(pwd)!"
echo "Current user: $(whoami)"
echo "Bash version: $BASH_VERSION"
echo "Written by Bash script." > bash_script_output.txt
# exit 1 # Uncomment to test non-zero exit code
"""
            print("\nExecuting Bash script:")
            stdout, stderr, retcode = execute_script(bash_code, language='bash', working_directory=test_dir)
            print(f"Return Code: {retcode}")
            print(f"Stdout:\n{stdout or '[No stdout]'}")
            print(f"Stderr:\n{stderr or '[No stderr]'}")
            # Verify file creation by script
            bash_script_file_path = os.path.join(test_dir, "bash_script_output.txt")
            if os.path.exists(bash_script_file_path):
                with open(bash_script_file_path, 'r') as f:
                    print(f"Content of {bash_script_file_path}: {f.read().strip()}")
            else:
                print(f"File {bash_script_file_path} was not created by script.")
        else:
            print("\nSkipping Bash script test on Windows.")

        # Example 7: Script timeout
        python_timeout_code = """
import time
print("Starting sleep...")
time.sleep(5)
print("Sleep finished (should not be reached).")
"""
        print("\nExecuting Python script (with 2s timeout):")
        stdout, stderr, retcode = execute_script(python_timeout_code, language='python', working_directory=test_dir, timeout=2)
        print(f"Return Code: {retcode}") # Should be None
        print(f"Stdout:\n{stdout or '[No stdout]'}")
        print(f"Stderr:\n{stderr or '[No stderr]'}") # Should indicate timeout

        # Example 8: Script with runtime error
        python_error_code = """
import sys
print("About to raise an error...")
sys.stderr.write("Error message to stderr before raising.\\n")
raise ValueError("This is a deliberate error from Python script")
"""
        print("\nExecuting Python script with runtime error:")
        stdout, stderr, retcode = execute_script(python_error_code, language='python', working_directory=test_dir)
        print(f"Return Code: {retcode}") # Should be non-zero (usually 1 for Python uncaught exceptions)
        print(f"Stdout:\n{stdout or '[No stdout]'}")
        print(f"Stderr:\n{stderr or '[No stderr]'}") # Should contain the Python traceback

        # Example 9: Unsupported language
        print("\nExecuting script with unsupported language:")
        stdout, stderr, retcode = execute_script