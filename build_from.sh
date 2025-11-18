#!/bin/bash

SOURCE_FILE="$1"
SCRIPT_DIR="$(dirname "$0")"

# prompt if no file provided
if [ $# -eq 0 ]; then
    while [ -z "$SOURCE_FILE" ]; do
        echo "Please enter the filename:"
        read -p "Filename: " SOURCE_FILE
    done
fi

find_file() {
    local file="$1"
    
    # abs path
    if [[ "$file" == /* ]]; then
        if [ -f "$file" ]; then
            echo "$file"
            return 0
        fi
    else
        # relative path
        if [ -f "$SCRIPT_DIR/$file" ]; then
            echo "$SCRIPT_DIR/$file"
            return 0
        fi
    fi
    
    return 1
}

# resolve file to abs path (doesn't care if abs or relative)
RESOLVED_FILE=$(find_file "$SOURCE_FILE")

if [ -z "$RESOLVED_FILE" ]; then
    echo "Error: File '$SOURCE_FILE' not found!"
    echo "For relative paths, it should be here: $SCRIPT_DIR"
    echo "For absolute paths, man... do better? Like, why are you linking me an absolute path that isn't real? C'mon."
    exit 1
fi

echo "Found file at: $RESOLVED_FILE"

# ensure targets.json't then copy source to targets.json
if [ -f "targets.json" ]; then
    rm targets.json
    echo "Removed existing targets.json"
fi

cp "$RESOLVED_FILE" targets.json
echo "Copied $RESOLVED_FILE to targets.json"

# python tiem~
echo "Running funky.py..."
python3 funky.py || {
    echo "Error: funky.py failed!"
    exit 1
}

echo "Running tatoclip.py..."
python3 tatoclip.py || {
    echo "Error: tatoclip.py failed!"
    exit 1
}

echo "Build completed successfully!"
