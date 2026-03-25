import os
import re

# Define the expected path to the configuration file
CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.py')

# The incorrect line currently in config.py
OLD_LINE = "    'sqlite:///' + os.path.join(basedir, 'app.db')"

# The corrected line that includes the 'app' directory
NEW_LINE = "    'sqlite:///' + os.path.join(basedir, 'app', 'app.db')"

def patch_config_file():
    """Reads config.py, replaces the old database path with the correct one, and saves the file."""
    if not os.path.exists(CONFIG_PATH):
        print(f"Error: Could not find config.py at {CONFIG_PATH}")
        return

    try:
        with open(CONFIG_PATH, 'r') as f:
            content = f.read()

        if NEW_LINE in content:
            print("✅ config.py is already patched. Skipping file modification.")
            return

        # Use regex to find and replace the path, ignoring potential whitespace differences
        # Escaping special characters in OLD_LINE for regex
        old_pattern = re.escape(OLD_LINE)
        
        new_content = re.sub(old_pattern, NEW_LINE, content)

        if new_content == content:
            print("⚠️ Warning: Database URI line not found in config.py. Please verify manually.")
        else:
            with open(CONFIG_PATH, 'w') as f:
                f.write(new_content)
            print(f"✅ Successfully patched {CONFIG_PATH}.")
            print(f"   Database URI now points to the correct location: 'sqlite:///' + os.path.join(basedir, 'app', 'app.db')")

    except Exception as e:
        print(f"An error occurred during file patching: {e}")

if __name__ == "__main__":
    patch_config_file()
