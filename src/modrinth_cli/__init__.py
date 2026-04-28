import argparse
import os
import sys
import time

# Assuming these are part of your package structure
from .resolver import ModrinthResolver
from .exceptions import DependencyError


def parse_arguments() -> argparse.Namespace:
    """Defines the CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Resolve and download Modrinth dependencies for Minecraft.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )

    parser.add_argument(
        "-f", "--file", 
        type=str, 
        default="modrinth-projects.txt",
        help="Path to the text file containing project IDs (one per line)."
    )

    parser.add_argument(
        "-l", "--loader", 
        type=str, 
        default="fabric",
        help="Minecraft loader to use (e.g., fabric, forge, quilt)."
    )

    parser.add_argument(
        "-v", "--version", 
        type=str, 
        default="26.1.2",
        help="Minecraft version to target."
    )

    parser.add_argument(
        "-o", "--output", 
        type=str, 
        help="Directory to download files into. If not provided, a timestamped folder will be created."
    )

    parser.add_argument(
        "--debug", 
        action="store_true", 
        help="Print full stack traces on error."
    )

    return parser.parse_args()


def main() -> None:
    # TODO: use logging
    
    args = parse_arguments()
    
    # 1. Setup Configuration
    loader = args.loader
    version = args.version
    projects_file = args.file
    
    # Handle the dynamic output directory logic
    if args.output:
        downloads_folder = args.output
    else:
        timestamp = int(time.time() * 1000)
        downloads_folder = f"{loader}-{version}-{timestamp}"

    # 2. Read Projects File
    try:
        with open(projects_file, "r", encoding="utf-8") as f:
            # Read, strip whitespace, remove empty lines, and deduplicate
            lines = f.read().splitlines()
            projects = list(set(line.strip() for line in lines if line.strip()))
        
        if not projects:
            print(f"Error: No projects found in '{projects_file}'.")
            sys.exit(1)
            
    except FileNotFoundError:
        print(f"Error: File '{projects_file}' not found.")
        sys.exit(1)
    except Exception as e:
        print(f"Error: Unable to read '{projects_file}': {e}")
        sys.exit(1)

    resolver = ModrinthResolver()

    # 3. Resolve Dependencies
    try:
        print(f"Resolving dependencies for {version} ({loader})...")
        results = resolver.resolve(projects, version, loader)

        if not results:
            print("No dependencies found to resolve.")
            return

        print("\nSuccessfully resolved dependencies:")
        for mod in results:
            print(f"- {mod.project_id} ({mod.version_id}) -> {mod.filename}")
            print(f"  Download: {mod.file_url}")

    except DependencyError as e:
        print(f"Error: Resolving dependencies failed: {e}")
        if args.debug:
            import traceback
            traceback.print_exc()
        sys.exit(1)
    except Exception as e:
        print(f"Error: Unexpected error during resolution: {e}")
        if args.debug:
            import traceback
            traceback.print_exc()
        sys.exit(1)

    # 4. Download Files
    os.makedirs(downloads_folder, exist_ok=True)
    try:
        print(f"\nDownloading {len(results)} files to: {downloads_folder}")
        resolver.download(results, directory=downloads_folder)
    except Exception as e:
        print(f"Error: Unexpected error during download: {e}")
        if args.debug:
            import traceback
            traceback.print_exc()
        sys.exit(1)

    print("\nFinished!")


if __name__ == "__main__":
    main()