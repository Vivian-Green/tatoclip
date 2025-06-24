from urllib.request import urlopen
from packaging import version
import sys
import json

ensured_ytdlp = False
def ensure_ytdlp(): # fail on non-latest yt-dlp version
    global ensured_ytdlp
    if ensured_ytdlp: return

    # Hardcoded package name
    package_name = "yt-dlp"
    print("\n\n\n\n!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
    try:
        # Get installed version
        from yt_dlp.version import __version__ as installed_version

        # Get latest version from PyPI
        with urlopen(f"https://pypi.org/pypi/{package_name}/json") as response:
            latest_version = json.load(response)['info']['version']

        if version.parse(installed_version) < version.parse(latest_version):
            print(f"\nERROR: yt-dlp is outdated ({installed_version} < {latest_version})", file=sys.stderr)
            print(f"Please update with: python -m pip install --upgrade {package_name}\n", file=sys.stderr)
            sys.exit(1)

        print(f"yt-dlp is up-to-date ({installed_version})")
    except ImportError:
        print(f"\nERROR: {package_name} is not installed", file=sys.stderr)
        print(f"Please install with: python -m pip install {package_name}\n", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"\nERROR: Version check failed: {str(e)}", file=sys.stderr)
        sys.exit(1)
    print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!\n\n\n\n")
    ensured_ytdlp = True