from pathlib import Path

from vflow.actions import _parse_range_pattern, _matches_pattern, list_duplicates


def test_parse_range_pattern_handles_various_prefix_forms():
    # Classic prefix on both sides
    assert _parse_range_pattern("C3317-C3366") == ("C", 3317, 3366)
    # Prefix only on first
    assert _parse_range_pattern("C3317-3366") == ("C", 3317, 3366)
    # No prefix at all
    assert _parse_range_pattern("3317-3366") == (None, 3317, 3366)
    # Invalid / descending range
    assert _parse_range_pattern("C3366-C3317") == (None, None, None)
    # Not a range
    assert _parse_range_pattern("C3317") == (None, None, None)


def test_matches_pattern_range_selects_correct_count():
    """
    Build a fake list of filenames and ensure a numeric range pattern hits the
    expected contiguous span (50 files).
    """
    # C3300..C3349 (50 clips), plus some out-of-range noise
    filenames = [f"C{n:04d}.MP4" for n in range(3280, 3370)]
    pattern = "C3300-C3349"

    matched = [name for name in filenames if _matches_pattern(pattern, name)]
    assert len(matched) == 50
    assert matched[0] == "C3300.MP4"
    assert matched[-1] == "C3349.MP4"


def test_matches_pattern_ignores_extension_and_case():
    """
    Pattern should match based on numeric range and prefix, regardless of case
    and extension differences.
    """
    files = [
        "c0100.mp4",
        "C0100.MOV",
        "C0101.MP4",
        "X0100.MP4",
        "C9999.MP4",
    ]

    # Range over 100..101 with C prefix
    pattern = "c0100-c0101"

    matched = [f for f in files if _matches_pattern(pattern, f)]
    # Both C0100.* and C0101.MP4 should match, X0100 and C9999 should not
    assert "c0100.mp4" in matched
    assert "C0100.MOV" in matched
    assert "C0101.MP4" in matched
    assert "X0100.MP4" not in matched
    assert "C9999.MP4" not in matched


def test_list_duplicates_respects_name_and_size(tmp_path):
    """
    list_duplicates groups by (filename, size). The same content under the same
    name should be treated as duplicates; different sizes or different names 
    should not be grouped.
    """
    root = tmp_path / "archive"
    (root / "A").mkdir(parents=True)
    (root / "B").mkdir(parents=True)

    # True duplicates: same filename and same bytes in two places
    dup1 = root / "A" / "C1000.MP4"
    dup2 = root / "B" / "C1000.MP4"
    dup1.write_bytes(b"same-content")
    dup2.write_bytes(b"same-content")

    # Same name but different bytes -> should NOT be treated as duplicate
    variant = root / "A" / "C1001.MP4"
    variant_other = root / "B" / "C1001.MP4"
    variant.write_bytes(b"one-version")
    variant_other.write_bytes(b"another-version")

    # Different name, same size -> also not a duplicate because name differs
    same_size_1 = root / "A" / "C2000.MP4"
    same_size_2 = root / "B" / "C2001.MP4"
    same_size_1.write_bytes(b"x" * 1234)
    same_size_2.write_bytes(b"x" * 1234)

    groups = list_duplicates(root)

    # There should be exactly one duplicate group for C1000.MP4
    dup_groups = [g for g in groups if g[0][0] == "C1000.MP4"]
    assert len(dup_groups) == 1
    (name, size), paths = dup_groups[0]
    assert name == "C1000.MP4"
    assert len(paths) == 2
    assert set(p.name for p in paths) == {"C1000.MP4"}

    # Ensure C1001.MP4 and C2000/C2001 are not reported as duplicates
    bad_names = {key[0] for key, _ in groups if key[0] in {"C1001.MP4", "C2000.MP4", "C2001.MP4"}}
    assert not bad_names


def test_matches_pattern_with_common_camera_naming():
    """
    Ensure that patterns work sensibly with typical camera naming schemes:
    - Canon: MVI_0001.MOV
    - Nikon: DSC_0001.MOV
    - Fuji: DSCF0001.MOV
    - iOS: IMG_0001.MOV / IMG_0001.MP4
    """
    names = [
        "MVI_0001.MOV",
        "MVI_0002.MOV",
        "DSC_0001.MOV",
        "DSCF0001.MOV",
        "IMG_0001.MOV",
        "IMG_0002.MP4",
        "RANDOM.MOV",
    ]

    # Simple prefix filter
    mvi = [n for n in names if _matches_pattern("MVI_", n)]
    assert mvi == ["MVI_0001.MOV", "MVI_0002.MOV"]

    # Nikon prefix
    dsc = [n for n in names if _matches_pattern("DSC_", n)]
    assert dsc == ["DSC_0001.MOV"]

    # Fuji prefix
    dscf = [n for n in names if _matches_pattern("DSCF", n)]
    assert dscf == ["DSCF0001.MOV"]

    # iOS prefix
    img = [n for n in names if _matches_pattern("IMG_", n)]
    assert "IMG_0001.MOV" in img and "IMG_0002.MP4" in img


def test_matches_pattern_with_phone_and_android_naming():
    """
    Mirrorless workflows often mix in phone footage. Ensure we can target
    common phone naming patterns with simple patterns.
    """
    names = [
        "IMG_1234.MOV",               # iOS
        "IMG_1234.HEIC",              # iOS photo (non-video)
        "VID_20260305_123456.MP4",    # Android
        "PXL_20260305_123456789.MP4", # Pixel
        "random.mov",
    ]

    # Target only iOS video by prefix and extension
    ios_video = [n for n in names if n.lower().endswith(".mov") and _matches_pattern("IMG_", n)]
    assert ios_video == ["IMG_1234.MOV"]

    # Android standard video prefix
    android = [n for n in names if _matches_pattern("VID_", n)]
    assert android == ["VID_20260305_123456.MP4"]

    # Pixel-style naming
    pixel = [n for n in names if _matches_pattern("PXL_", n)]
    assert pixel == ["PXL_20260305_123456789.MP4"]

