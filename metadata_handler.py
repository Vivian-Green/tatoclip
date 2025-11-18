# todo: imported from cinnamon plugin, may not function?
from common import TARGETS


def get_effective_index(data, raw_index):
    """Convert raw index to effective index considering offsets"""
    if not data or not isinstance(data, list) or len(data) == 0:
        return raw_index

    metadata = data[0]
    offsets = metadata.get("offsets", {})

    # Convert offsets to sorted list of (effective_threshold, shift)
    offset_points = []
    for k, v in offsets.items():
        try:
            offset_points.append((int(k), int(v)))
        except (ValueError, TypeError):
            continue

    # Sort by effective threshold
    offset_points.sort(key=lambda x: x[0])

    # Calculate how many videos are skipped before this raw index
    total_skipped = 0
    for effective_threshold, shift in offset_points:
        # The raw index where this offset starts applying
        raw_threshold = effective_threshold + total_skipped
        if raw_index >= raw_threshold:
            total_skipped += shift
        else:
            break

    return raw_index - total_skipped

# todo: precalculate-
def get_raw_index(data, effective_index):
    """Convert effective index to raw index considering offsets"""
    if not data or not isinstance(data, list) or len(data) == 0:
        return effective_index

    metadata = data[0]
    offsets = metadata.get("offsets", {})

    # Handle negative effective indices (skipped videos)
    if effective_index < 0:
        # Build list of all skipped raw indices
        skipped_indices = []
        current_raw = 1
        current_effective = 1

        # Convert offsets to sorted list and process
        offset_points = []
        for k, v in offsets.items():
            try:
                offset_points.append((int(k), int(v)))
            except (ValueError, TypeError):
                continue
        offset_points.sort(key=lambda x: x[0])

        for effective_threshold, shift in offset_points:
            # Add all videos up to this threshold
            while current_effective < effective_threshold:
                current_raw += 1
                current_effective += 1

            # Skip the specified number of videos
            for i in range(shift):
                skipped_indices.append(current_raw + i)

            current_raw += shift

        # Return the corresponding skipped index for negative effective
        idx = -effective_index - 1
        return skipped_indices[idx] if idx < len(skipped_indices) else None

    # For positive effective indices, calculate the corresponding raw index
    offset_points = []
    for k, v in offsets.items():
        try:
            offset_points.append((int(k), int(v)))
        except (ValueError, TypeError):
            continue
    offset_points.sort(key=lambda x: x[0])

    raw_index = effective_index
    total_shift = 0

    for effective_threshold, shift in offset_points:
        if effective_index >= effective_threshold:
            total_shift += shift
        else:
            break

    return effective_index + total_shift


def resolve_alias_to_effective_index(data, alias) -> (int, bool):
    if not data or len(data) < 1:
        try:
            return int(alias), False  # Fallback to direct index if no metadata
        except ValueError:
            return None, False

    metadata = data[0]
    aliases = metadata.get("aliases", {})

    # Find index by alias
    for index, al in aliases.items():
        if al == alias:
            return int(index), True

    # Try to parse as direct index
    try:
        return int(alias), False
    except ValueError:
        return None, False

def get_alias_for_index(data, index) -> str:
    """Get the alias for a given raw index if it exists"""
    if not data or len(data) < 1:
        return None

    metadata = data[0]
    aliases = metadata.get("aliases", {})
    return aliases.get(str(index))

