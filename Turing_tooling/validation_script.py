"""
Validation Script for OSWorld Task Deliveries.

Validates schema compliance, directory structure, and evaluation artefacts for a task delivery.
"""

import os
import json
import shutil
import argparse
from pathlib import Path

from jsonschema import validate, ValidationError

def load_schema(schema_path):
    with open(schema_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def validate_json_structure(task_json_path, schema):
    try:
        with open(task_json_path, 'r', encoding='utf-8') as f:
            task_data = json.load(f)
        validate(instance=task_data, schema=schema)
        print('✅ JSON structure validation: PASSED')
        return True, task_data
    except ValidationError as exc:
        print(f"❌ JSON validation error: {exc.message}")
        return False, None
    except Exception as exc:
        print(f"❌ Error loading JSON: {exc}")
        return False, None

def _collect_enum_values(node):
    enums = set()
    if not isinstance(node, dict):
        return enums
    enum_values = node.get('enum')
    if isinstance(enum_values, list):
        enums.update(enum_values)
    for keyword in ('oneOf', 'anyOf', 'allOf'):
        options = node.get(keyword, [])
        if isinstance(options, list):
            for option in options:
                enums.update(_collect_enum_values(option))
    items = node.get('items')
    if isinstance(items, dict):
        enums.update(_collect_enum_values(items))
    return enums

def _get_schema_evaluator_funcs(schema):
    evaluator_schema = schema.get('properties', {}).get('evaluator', {})
    func_schema = evaluator_schema.get('properties', {}).get('func', {})
    return _collect_enum_values(func_schema)


def _parse_binary_score(raw_value: str, context: str) -> int:
    value_str = (raw_value or "").strip()
    if not value_str:
        raise ValueError(f"{context}: value is empty.")
    try:
        numeric = float(value_str)
    except ValueError as exc:
        raise ValueError(f"{context}: '{value_str}' is not numeric.") from exc
    if abs(numeric) < 1e-6:
        return 0
    if abs(numeric - 1) < 1e-6:
        return 1
    raise ValueError(f"{context}: {numeric} must be 0 or 1.")




def _extract_domain_candidates(task_data):
    candidates = []
    if isinstance(task_data, dict):
        for key in ('snapshot', 'domain'):
            value = task_data.get(key)
            if isinstance(value, str):
                candidates.append(value)
        related = task_data.get('related_apps')
        if isinstance(related, list):
            candidates.extend(item for item in related if isinstance(item, str))
    seen = []
    for item in candidates:
        if item and item not in seen:
            seen.append(item)
    return seen


def _derive_domain_candidates(sft_dir: Path, task_data):
    candidates = _extract_domain_candidates(task_data)
    seen = []
    for value in candidates:
        if value and value not in seen:
            seen.append(value)
    try:
        sft_path = Path(sft_dir)
        for child in sft_path.iterdir():
            if child.is_dir() and child.name not in ('Trajectory and Screenshot', 'Colab'):
                if child.name not in seen:
                    seen.append(child.name)
    except (FileNotFoundError, NotADirectoryError):
        pass
    return seen

def _locate_sft_score_file(sft_dir: Path, task_id: str, domain_candidates=None):
    sft_dir = Path(sft_dir)
    if not sft_dir.exists():
        return None

    candidate_domains = []
    for domain in domain_candidates or []:
        if domain and domain not in candidate_domains:
            candidate_domains.append(domain)

    for domain in candidate_domains:
        candidate = sft_dir / domain / task_id / 'evaluation_score.txt'
        if candidate.exists():
            return candidate

    for subdir in sft_dir.iterdir():
        if subdir.is_dir():
            candidate = subdir / task_id / 'evaluation_score.txt'
            if candidate.exists():
                return candidate

    legacy_candidates = [
        sft_dir / 'Trajectory and Screenshot' / 'evaluation_score.txt',
        sft_dir / 'Trajectory and Screenshot' / task_id / 'evaluation_score.txt',
    ]
    for candidate in legacy_candidates:
        if candidate.exists():
            return candidate

    matches = [p for p in sft_dir.rglob('evaluation_score.txt') if p.is_file()]
    if not matches:
        return None
    matches.sort(key=lambda p: len(p.parts))
    return matches[0]



def _ensure_expected_path(base_path, relative_parts, rearrange=False, search_patterns=None, must_be_dir=False, candidate_filter=None):
    base_path = Path(base_path)
    expected_path = base_path.joinpath(*relative_parts)
    if expected_path.exists():
        return expected_path
    patterns = search_patterns or [relative_parts[-1]]
    matches = []
    for pattern in patterns:
        for candidate in base_path.rglob(pattern):
            if candidate == expected_path:
                return expected_path
            if must_be_dir and not candidate.is_dir():
                continue
            if not must_be_dir and candidate.is_dir():
                continue
            if candidate_filter and not candidate_filter(candidate):
                continue
            matches.append(candidate)
    if not matches:
        return None
    matches = sorted(matches, key=lambda p: len(p.parts))
    selected = matches[0]
    if not rearrange:
        kind = 'directory' if must_be_dir else 'file'
        print(f"❌ Structure check: Expected {kind} {expected_path} missing (found at {selected}). Use --rearrange to repair.")
        return None
    target_parent = expected_path.parent
    target_parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.move(str(selected), str(expected_path))
        print(f"🔁 Structure check: Moved {selected} to {expected_path}.")
        return expected_path
    except Exception as exc:
        print(f"❌ Structure check: Failed to move {selected} to {expected_path}: {exc}")
        return None

def _normalize_run_name(name):
    """Normalize run directory names to run_X format (no leading zeros)."""
    import re
    # Extract number from various formats: run_1, run_01, Run_1, Run_01, etc.
    match = re.match(r'(?i)^run_?(\d+)$', name.strip())
    if match:
        num = int(match.group(1))  # This removes leading zeros
        return f'run_{num}'
    return name

def _normalize_annotator_name(name):
    """Normalize annotator directory names to annotator_X format (no leading zeros)."""
    import re
    # Extract number from various formats: annotator1, annotator_1, Annotator1, etc.
    match = re.match(r'(?i)^annotator_?(\d+)$', name.strip())
    if match:
        num = int(match.group(1))  # This removes leading zeros
        return f'annotator_{num}'
    return name

def _normalize_directory_names(base_path, rearrange=False):
    """Normalize directory names in the given path."""
    if not rearrange:
        return
    
    base_path = Path(base_path)
    if not base_path.exists():
        return
    
    # Normalize run directories in claude folder
    claude_dir = _locate_claude_folder(base_path)
    if claude_dir:
        # First, collect all directories and their normalized names
        dirs_to_process = []
        for child in claude_dir.iterdir():
            if child.is_dir():
                normalized_name = _normalize_run_name(child.name)
                dirs_to_process.append((child, normalized_name))
        
        # Process directories, handling conflicts
        for child, normalized_name in dirs_to_process:
            if normalized_name != child.name:
                target_path = claude_dir / normalized_name
                if not target_path.exists():
                    try:
                        shutil.move(str(child), str(target_path))
                        print(f"🔁 Name normalization: Renamed {child.name} to {normalized_name}")
                    except Exception as exc:
                        print(f"❌ Name normalization: Failed to rename {child.name}: {exc}")
                else:
                    # Target exists - check if it's the same directory (case-insensitive filesystem)
                    try:
                        # Check if they're the same directory by comparing inodes
                        child_stat = child.stat()
                        target_stat = target_path.stat()
                        if child_stat.st_ino == target_stat.st_ino:
                            # Same directory - try to rename to normalize the name
                            try:
                                # Create a temporary name to avoid conflict
                                temp_name = f"{normalized_name}_temp_{child_stat.st_ino}"
                                temp_path = child.parent / temp_name
                                shutil.move(str(child), str(temp_path))
                                shutil.move(str(temp_path), str(target_path))
                                print(f"🔁 Name normalization: Renamed {child.name} to {normalized_name} (case-insensitive filesystem)")
                            except Exception as exc:
                                print(f"ℹ️ Name normalization: {child.name} and {normalized_name} are the same directory (case-insensitive filesystem)")
                        else:
                            # Different directories - merge contents or report conflict
                            print(f"⚠️ Name normalization: Cannot rename {child.name} to {normalized_name} (target exists)")
                            print(f"   Consider manually merging contents from {child} into {target_path}")
                    except (OSError, FileNotFoundError):
                        # Fallback to path comparison
                        if child.resolve() == target_path.resolve():
                            try:
                                # Create a temporary name to avoid conflict
                                temp_name = f"{normalized_name}_temp"
                                temp_path = child.parent / temp_name
                                shutil.move(str(child), str(temp_path))
                                shutil.move(str(temp_path), str(target_path))
                                print(f"🔁 Name normalization: Renamed {child.name} to {normalized_name} (case-insensitive filesystem)")
                            except Exception as exc:
                                print(f"ℹ️ Name normalization: {child.name} and {normalized_name} are the same directory (case-insensitive filesystem)")
                        else:
                            print(f"⚠️ Name normalization: Cannot rename {child.name} to {normalized_name} (target exists)")
                            print(f"   Consider manually merging contents from {child} into {target_path}")
    
    # Normalize annotator directories
    annot_root = _locate_annotator_root(base_path)
    if annot_root:
        # First, collect all directories and their normalized names
        dirs_to_process = []
        for child in annot_root.iterdir():
            if child.is_dir():
                normalized_name = _normalize_annotator_name(child.name)
                dirs_to_process.append((child, normalized_name))
        
        # Process directories, handling conflicts
        for child, normalized_name in dirs_to_process:
            if normalized_name != child.name:
                target_path = annot_root / normalized_name
                if not target_path.exists():
                    try:
                        shutil.move(str(child), str(target_path))
                        print(f"🔁 Name normalization: Renamed {child.name} to {normalized_name}")
                    except Exception as exc:
                        print(f"❌ Name normalization: Failed to rename {child.name}: {exc}")
                else:
                    # Target exists - check if it's the same directory (case-insensitive filesystem)
                    try:
                        # Check if they're the same directory by comparing inodes
                        child_stat = child.stat()
                        target_stat = target_path.stat()
                        if child_stat.st_ino == target_stat.st_ino:
                            # Same directory - try to rename to normalize the name
                            try:
                                # Create a temporary name to avoid conflict
                                temp_name = f"{normalized_name}_temp_{child_stat.st_ino}"
                                temp_path = child.parent / temp_name
                                shutil.move(str(child), str(temp_path))
                                shutil.move(str(temp_path), str(target_path))
                                print(f"🔁 Name normalization: Renamed {child.name} to {normalized_name} (case-insensitive filesystem)")
                            except Exception as exc:
                                print(f"ℹ️ Name normalization: {child.name} and {normalized_name} are the same directory (case-insensitive filesystem)")
                        else:
                            # Different directories - merge contents or report conflict
                            print(f"⚠️ Name normalization: Cannot rename {child.name} to {normalized_name} (target exists)")
                            print(f"   Consider manually merging contents from {child} into {target_path}")
                    except (OSError, FileNotFoundError):
                        # Fallback to path comparison
                        if child.resolve() == target_path.resolve():
                            try:
                                # Create a temporary name to avoid conflict
                                temp_name = f"{normalized_name}_temp"
                                temp_path = child.parent / temp_name
                                shutil.move(str(child), str(temp_path))
                                shutil.move(str(temp_path), str(target_path))
                                print(f"🔁 Name normalization: Renamed {child.name} to {normalized_name} (case-insensitive filesystem)")
                            except Exception as exc:
                                print(f"ℹ️ Name normalization: {child.name} and {normalized_name} are the same directory (case-insensitive filesystem)")
                        else:
                            print(f"⚠️ Name normalization: Cannot rename {child.name} to {normalized_name} (target exists)")
                            print(f"   Consider manually merging contents from {child} into {target_path}")

def _has_run_dirs(path):
    try:
        return any(child.is_dir() and child.name.lower().startswith('run_') for child in Path(path).iterdir())
    except (FileNotFoundError, PermissionError):
        return False

def _validate_trajectory_assets(folder, description):
    if folder is None:
        return False
    folder = Path(folder)
    if not folder.exists():
        print(f"❌ Structure check: {description} not found.")
        return False
    png_files = list(folder.glob('*.png'))
    xml_files = list(folder.glob('*.xml'))
    if not png_files:
        print(f"❌ Structure check: {description} has no PNG screenshots.")
        return False
    if not xml_files:
        print(f"❌ Structure check: {description} has no XML accessibility trees.")
        return False
    if len(png_files) != len(xml_files):
        print(f"❌ Structure check: {description} has {len(png_files)} PNG files and {len(xml_files)} XML files; counts must match.")
        return False
    return True


def _prepare_trajectory_folder(folder, description, rearrange, expected_child=None):
    folder = Path(folder)
    png_files = list(folder.glob('*.png'))
    xml_files = list(folder.glob('*.xml'))
    if png_files or xml_files:
        return True

    subdirs = [child for child in folder.iterdir() if child.is_dir() and child.name != 'Colab']
    target_dir = None
    if expected_child:
        for child in subdirs:
            if child.name == expected_child:
                target_dir = child
                break
    if target_dir is None and len(subdirs) == 1:
        target_dir = subdirs[0]

    if target_dir is None:
        if not subdirs:
            print(f"❌ Structure check: {description} has no trajectory assets.")
        else:
            print(f"❌ Structure check: {description} files are nested in unexpected subdirectories: {[d.name for d in subdirs]}.")
        return False

    if not rearrange:
        print(f"❌ Structure check: {description} assets are nested in {target_dir.name}; use --rearrange to normalize.")
        return False

    moved_any = False
    for item in target_dir.iterdir():
        destination = folder / item.name
        if destination.exists():
            try:
                if destination.is_dir():
                    shutil.rmtree(destination)
                else:
                    destination.unlink()
            except Exception as exc:
                print(f"❌ Structure check: Failed to replace {destination}: {exc}")
                return False
        shutil.move(str(item), str(destination))
        moved_any = True

    if moved_any:
        print(f"🔁 Structure check: Flattened contents from {target_dir} into {folder}.")

    try:
        target_dir.rmdir()
    except OSError:
        pass

    return True


def _locate_claude_folder(task_folder):
    base = Path(task_folder)
    expected = base / 'claude-4-sonnet-20250514'
    if expected.exists():
        return expected
    candidates = [child for child in base.iterdir() if child.is_dir() and child.name.startswith('claude-4-sonnet') and _has_run_dirs(child)]
    if candidates:
        return sorted(candidates, key=lambda p: len(p.parts))[0]
    search_patterns = [
        'claude-4-sonnet-20250514',
        'claude-4-sonnet-20250514*',
        '*claude-4-sonnet-20250514*',
    ]
    for pattern in search_patterns:
        matches = [candidate for candidate in base.rglob(pattern) if candidate.is_dir() and _has_run_dirs(candidate)]
        if matches:
            return sorted(matches, key=lambda p: len(p.parts))[0]
    return None

def _locate_annotator_root(task_folder):
    base = Path(task_folder)
    for name in ('Annotator Trajectory', 'Annotator_trajectory', 'Annotator trajectory'):
        candidate = base / name
        if candidate.exists():
            return candidate
    matches = []
    for pattern in ('Annotator Trajectory', 'Annotator_trajectory', 'Annotator trajectory'):
        matches.extend(candidate for candidate in base.rglob(pattern) if candidate.is_dir())
    if matches:
        return sorted(matches, key=lambda p: len(p.parts))[0]
    return None

def check_evaluator_diff(task_data, task_folder, schema_funcs):
    evaluator_funcs = task_data.get('evaluator', {}).get('func', [])
    if isinstance(evaluator_funcs, str):
        evaluator_funcs = [evaluator_funcs]
    schema_funcs = set(schema_funcs or [])
    if not schema_funcs:
        print('❌ Evaluator diff check: No evaluator functions defined in schema.')
        return False
    new_funcs = [func for func in evaluator_funcs if func not in schema_funcs]
    if new_funcs:
        diff_path = Path(task_folder) / 'SFT' / 'evaluator.diff'
        if not diff_path.exists():
            print(f"❌ Evaluator diff check: New evaluator functions {new_funcs} found, but evaluator.diff not present.")
            return False
        diff_content = diff_path.read_text(encoding='utf-8', errors='ignore')
        for func in new_funcs:
            if func not in diff_content:
                print(f"❌ Evaluator diff check: Function {func} not defined in evaluator.diff.")
                return False
    print('✅ Evaluator diff check: PASSED')
    return True

def validate_pass_k(task_folder, task_id, rearrange=False):
    claude_dir = _locate_claude_folder(task_folder)
    if not claude_dir:
        print('❌ Pass@k validation: claude-4-sonnet-20250514 folder not found.')
        return False

    results = []
    for i in range(1, 17):
        run_dir = None
        for name in (f"run_{i:02d}", f"run_{i}"):
            candidate = Path(claude_dir) / name
            if candidate.exists():
                run_dir = candidate
                break
        if run_dir is None:
            expected_path = Path(claude_dir) / f"run_{i:02d}"
            print(f"❌ Pass@k validation: Run folder {expected_path} not found.")
            return False

        traj_dir = run_dir / 'Trajectory and Screenshot'
        if not traj_dir.exists():
            print(f"❌ Pass@k validation: 'Trajectory and Screenshot' missing in {run_dir}.")
            return False

        expected_file = traj_dir / 'result.txt'
        located_file = None
        if expected_file.exists():
            located_file = expected_file
        else:
            nested_candidate = traj_dir / task_id / 'result.txt'
            if nested_candidate.exists():
                located_file = nested_candidate
            else:
                matches = [p for p in traj_dir.rglob('result.txt') if p.is_file()]
                if not matches:
                    print(f"❌ Pass@k validation: result.txt not found under {traj_dir}.")
                    return False
                if len(matches) > 1:
                    relative_matches = [str(match.relative_to(run_dir)) for match in matches]
                    print(f"❌ Pass@k validation: Multiple result.txt files found in {traj_dir}: {relative_matches}")
                    return False
                located_file = matches[0]

        if located_file != expected_file:
            if not rearrange:
                print(f"❌ Pass@k validation: result.txt located at {located_file} instead of {expected_file}. Use --rearrange to repair.")
                return False
            try:
                expected_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(located_file), str(expected_file))
                print(f'🔁 Pass@k validation: Moved {located_file} to {expected_file}.')
                nested_parent = expected_file.parent / task_id
                if nested_parent.exists() and nested_parent.is_dir():
                    try:
                        nested_parent.rmdir()
                    except OSError:
                        pass
            except Exception as exc:
                print(f"❌ Pass@k validation: Failed to move {located_file} to {expected_file}: {exc}")
                return False

        raw_value = expected_file.read_text(encoding='utf-8')
        try:
            val = _parse_binary_score(raw_value, f"Pass@k result in {expected_file}")
        except ValueError as exc:
            print(f"❌ Pass@k validation: {exc}")
            return False
        results.append(val)

    num_runs = len(results)
    print(f'📊 Pass@k validation: Found {num_runs} runs.')
    if num_runs != 16:
        print('❌ Pass@k validation: Not exactly 16 runs.')
        return False

    avg = sum(results) / num_runs if num_runs else 0
    if avg == 0 or avg == 1:
        print(f'❌ Pass@k validation: Average is {avg}, which is invalid (must be between 0 and 1).')
        return False

    print(f'✅ Pass@k validation: PASSED with average {avg:.2f}')
    return True


def check_file_structure(task_folder, task_id, rearrange=False, task_data=None):
    base = Path(task_folder)
    all_good = True
    
    # Normalize directory names if rearrange is enabled
    if rearrange:
        _normalize_directory_names(base, rearrange)
    json_path = _ensure_expected_path(base, [f'{task_id}.json'], rearrange, search_patterns=[f'{task_id}.json'])
    if json_path is None or not json_path.exists():
        print(f'❌ Structure check: Required JSON {task_id}.json missing.')
        all_good = False
    sft_dir = _ensure_expected_path(base, ['SFT'], rearrange, search_patterns=['SFT'], must_be_dir=True)
    if not sft_dir:
        print('❌ Structure check: SFT/ directory missing.')
        all_good = False
    else:
        domain_candidates = _derive_domain_candidates(sft_dir, task_data)
        evaluator_diff = _ensure_expected_path(sft_dir, ['evaluator.diff'], rearrange, search_patterns=['evaluator.diff'])
        if evaluator_diff is None or not evaluator_diff.exists():
            print('❌ Structure check: SFT/evaluator.diff missing.')
            all_good = False
        colab_dir = _ensure_expected_path(sft_dir, ['Colab'], rearrange, search_patterns=['Colab'], must_be_dir=True)
        if not colab_dir:
            if rearrange:
                colab_dir = sft_dir / 'Colab'
                colab_dir.mkdir(parents=True, exist_ok=True)
                print(f"🔁 Structure check: Created {colab_dir}.")
            else:
                print('❌ Structure check: SFT/Colab directory missing.')
                all_good = False
        if colab_dir:
            colab_dir = Path(colab_dir)
            notebook_groups = {}
            for nb_path in sft_dir.rglob('*.ipynb'):
                if not nb_path.is_file():
                    continue
                if colab_dir in nb_path.parents or nb_path.parent == colab_dir:
                    continue
                try:
                    relative_parent = nb_path.parent.relative_to(sft_dir)
                    context_label = relative_parent.as_posix() or '.'
                except ValueError:
                    context_label = nb_path.parent.name
                notebook_groups.setdefault(context_label, []).append(nb_path)

            def _relocate_notebook_group(paths, context_label):
                nonlocal all_good
                if not paths:
                    return
                label = f"SFT/{context_label}" if context_label != '.' else 'SFT'
                if not rearrange:
                    print(f"\u274c Structure check: {label} contains notebook files outside SFT/Colab/. Use --rearrange to relocate them.")
                    all_good = False
                    return
                moved_any = False
                for nb_path in paths:
                    target = colab_dir / nb_path.name
                    try:
                        if target.exists():
                            if target.is_dir():
                                shutil.rmtree(target)
                            else:
                                target.unlink()
                        shutil.move(str(nb_path), str(target))
                        moved_any = True
                    except Exception as exc:
                        print(f"\u274c Structure check: Failed to move {nb_path} to {target}: {exc}")
                        all_good = False
                        moved_any = False
                        break
                if moved_any:
                    print(f"\U0001f501 Structure check: Moved notebook files from {label} into SFT/Colab/.")
                    for nb_path in paths:
                        parent = nb_path.parent
                        while parent not in (colab_dir, sft_dir) and parent.exists() and not any(parent.iterdir()):
                            try:
                                parent.rmdir()
                            except OSError:
                                break
                            parent = parent.parent

            for context_label, paths in notebook_groups.items():
                _relocate_notebook_group(paths, context_label)
        traj_dir = _ensure_expected_path(
            sft_dir,
            ['Trajectory and Screenshot'],
            rearrange,
            search_patterns=['Trajectory and Screenshot', 'Trajectory_and_Screenshot'],
            must_be_dir=True,
        )
        if not traj_dir:
            all_good = False
        else:
            if not _prepare_trajectory_folder(traj_dir, 'SFT/Trajectory and Screenshot', rearrange, expected_child=task_id):
                all_good = False
            elif not _validate_trajectory_assets(traj_dir, 'SFT/Trajectory and Screenshot'):
                all_good = False
        score_path = _locate_sft_score_file(sft_dir, task_id, domain_candidates)
        score_path_obj = Path(score_path) if score_path else None
        if score_path_obj is None or not score_path_obj.exists():
            print('\u274c Structure check: SFT evaluation_score.txt missing.')
            all_good = False
        elif rearrange:
            candidate_paths = []
            seen = set()

            def add_candidate(path):
                if path is None:
                    return
                candidate = Path(path)
                key = candidate.as_posix()
                if key not in seen:
                    seen.add(key)
                    candidate_paths.append(candidate)

            for domain in domain_candidates:
                add_candidate(sft_dir / domain / task_id / 'evaluation_score.txt')
            try:
                for child in Path(sft_dir).iterdir():
                    if child.is_dir() and child.name not in ('Trajectory and Screenshot', 'Colab'):
                        add_candidate(child / task_id / 'evaluation_score.txt')
            except (FileNotFoundError, NotADirectoryError):
                pass
            add_candidate(sft_dir / task_id / 'evaluation_score.txt')
            add_candidate(score_path_obj)

            if score_path_obj and traj_dir and (score_path_obj.parent == traj_dir or (score_path_obj.parent.name == task_id and score_path_obj.parent.parent == traj_dir)):
                expected_score = sft_dir / task_id / 'evaluation_score.txt'
            else:
                expected_score = next((cand for cand in candidate_paths if cand != score_path_obj), score_path_obj)

            if expected_score and score_path_obj != expected_score:
                try:
                    expected_score.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(score_path_obj), str(expected_score))
                    print(f'\U0001f501 Structure check: Moved {score_path_obj} to {expected_score}.')
                    score_path_obj = expected_score
                except Exception as exc:
                    print(f'\u274c Structure check: Failed to move {score_path_obj} to {expected_score}: {exc}')
                    all_good = False
    claude_dir = _ensure_expected_path(
        base,
        ['claude-4-sonnet-20250514'],
        rearrange,
        search_patterns=['claude-4-sonnet-20250514', 'claude-4-sonnet-20250514*', '*claude-4-sonnet-20250514*'],
        must_be_dir=True,
        candidate_filter=_has_run_dirs,
    )
    if not claude_dir:
        print('❌ Structure check: claude-4-sonnet-20250514/ directory missing.')
        all_good = False
    else:
        for i in range(1, 17):
            expected_run = f'run_{i:02d}'
            run_dir = None
            for candidate_name in (expected_run, f'run_{i}'):
                candidate = Path(claude_dir) / candidate_name
                if candidate.exists():
                    run_dir = candidate
                    break
            if run_dir is None:
                run_dir = _ensure_expected_path(
                    claude_dir,
                    [expected_run],
                    rearrange,
                    search_patterns=[expected_run, f'run_{i}'],
                    must_be_dir=True,
                )
            if not run_dir:
                print(f'❌ Structure check: Missing Claude run folder {expected_run}.')
                all_good = False
                continue
            traj_dir = _ensure_expected_path(
                run_dir,
                ['Trajectory and Screenshot'],
                rearrange,
                search_patterns=['Trajectory and Screenshot', 'Trajectory_and_Screenshot'],
                must_be_dir=True,
            )
            if not traj_dir:
                print(f'❌ Structure check: Missing Trajectory and Screenshot for {Path(run_dir).name}.')
                all_good = False
                continue
            if not _prepare_trajectory_folder(
                traj_dir,
                f"{Path(claude_dir).name}/{Path(run_dir).name}/Trajectory and Screenshot",
                rearrange,
                expected_child=task_id,
            ):
                all_good = False
                continue
            if not _validate_trajectory_assets(traj_dir, f"{Path(claude_dir).name}/{Path(run_dir).name}/Trajectory and Screenshot"):
                all_good = False
    annot_root = _ensure_expected_path(
        base,
        ['Annotator Trajectory'],
        rearrange,
        search_patterns=['Annotator Trajectory', 'Annotator_trajectory', 'Annotator trajectory'],
        must_be_dir=True,
    )
    if not annot_root:
        print('❌ Structure check: Annotator Trajectory/ directory missing.')
        all_good = False
    else:
        for idx in range(1, 4):
            canonical = f'annotator{idx}'
            annot_dir = None
            for variant in (canonical, f'annotator_{idx}', f'annotaor_{idx}', f'annotaor{idx}', f'annotator{idx:02d}'):
                candidate = Path(annot_root) / variant
                if candidate.exists():
                    annot_dir = candidate
                    break
            if annot_dir is None:
                annot_dir = _ensure_expected_path(
                    annot_root,
                    [canonical],
                    rearrange,
                    search_patterns=[canonical, f'annotator_{idx}', f'annotaor_{idx}', f'annotaor{idx}', f'annotator{idx:02d}'],
                    must_be_dir=True,
                )
            if not annot_dir:
                print(f'❌ Structure check: Missing annotator folder for annotator {idx}.')
                all_good = False
                continue
            colab_dir = _ensure_expected_path(
                annot_dir,
                ['Colab'],
                rearrange,
                search_patterns=['Colab'],
                must_be_dir=True,
            )
            if not colab_dir:
                print(f"❌ Structure check: {Path(annot_root).name}/{Path(annot_dir).name} missing Colab/ directory.")
                all_good = False

            eval_file = _ensure_expected_path(
                annot_dir,
                ['evaluation_score.txt'],
                rearrange,
                search_patterns=['evaluation_score.txt'],
            )
            if eval_file is None or not eval_file.exists():
                print(f'❌ Structure check: evaluation_score.txt missing for annotator {idx}.')
                all_good = False
            traj_dir = _ensure_expected_path(
                annot_dir,
                ['Trajectory and Screenshot'],
                rearrange,
                search_patterns=['Trajectory and Screenshot', 'Trajectory_and_Screenshot'],
                must_be_dir=True,
            )
            if not traj_dir:
                print(f'❌ Structure check: Trajectory and Screenshot missing for annotator {idx}.')
                all_good = False
                continue
            if not _prepare_trajectory_folder(
                traj_dir,
                f"{Path(annot_root).name}/{Path(annot_dir).name}/Trajectory and Screenshot",
                rearrange,
                expected_child=task_id,
            ):
                all_good = False
                continue
            if not _validate_trajectory_assets(
                traj_dir,
                f"{Path(annot_root).name}/{Path(annot_dir).name}/Trajectory and Screenshot",
            ):
                all_good = False
    if all_good:
        print('✅ File structure check: PASSED')
    return all_good

def check_sft_eval_score(task_folder, task_id, task_data=None):
    sft_dir = Path(task_folder) / 'SFT'
    domain_candidates = _derive_domain_candidates(sft_dir, task_data)
    score_path = _locate_sft_score_file(sft_dir, task_id, domain_candidates)
    score_path_obj = Path(score_path) if score_path else None
    if score_path_obj is None or not score_path_obj.exists():
        print('❌ SFT eval score check: evaluation_score.txt not found in SFT.')
        return False

    raw_value = score_path_obj.read_text(encoding='utf-8')
    try:
        val = _parse_binary_score(raw_value, f"SFT eval score ({score_path_obj})")
    except ValueError as exc:
        print(f'❌ SFT eval score check: {exc}')
        return False

    if val != 1:
        print(f'❌ SFT eval score check: Score is {val}, not 1.')
        return False
    print('✅ SFT eval score check: PASSED')
    return True


def check_annotator_scores(task_folder):
    annot_root = _locate_annotator_root(task_folder)
    if not annot_root:
        print('❌ Annotator scores check: Annotator Trajectory directory not found.')
        return False

    scores = []
    for idx in range(1, 4):
        annot_dir = None
        for variant in (f'annotator{idx}', f'annotator_{idx}', f'annotaor_{idx}', f'annotaor{idx}', f'annotator{idx:02d}'):
            candidate = Path(annot_root) / variant
            if candidate.exists():
                annot_dir = candidate
                break
        if annot_dir is None:
            print(f'❌ Annotator scores check: Annotator folder for annotator {idx} not found.')
            return False

        score_file = annot_dir / 'evaluation_score.txt'
        if not score_file.exists():
            print(f'❌ Annotator scores check: evaluation_score.txt not found for annotator {idx}.')
            return False

        raw_value = score_file.read_text(encoding='utf-8')
        try:
            val = _parse_binary_score(raw_value, f"Annotator {idx} score ({score_file})")
        except ValueError as exc:
            print(f'❌ Annotator scores check: {exc}')
            return False
        scores.append(val)

    count_1 = scores.count(1)
    count_0 = scores.count(0)
    print(f'📊 Annotator scores check: {count_1} passed (1), {count_0} failed (0).')
    if 1 not in scores or 0 not in scores:
        print('❌ Annotator scores check: Scores do not include both 1 and 0.')
        return False
    print('✅ Annotator scores check: PASSED')
    return True


def check_notebook_assistant_cells(task_folder):
    task_path = Path(task_folder)
    notebooks = list(task_path.rglob('*.ipynb'))
    if not notebooks:
        print('ℹ️ Notebook assistant check: No notebooks found.')
        return True

    all_good = True
    for notebook in notebooks:
        try:
            data = json.loads(notebook.read_text(encoding='utf-8'))
        except Exception as exc:
            print(f"❌ Notebook assistant check: Failed to read {notebook}: {exc}")
            all_good = False
            continue

        cells = data.get('cells', [])
        for idx, cell in enumerate(cells):
            source = cell.get('source', [])
            if isinstance(source, list):
                text = ''.join(source)
            elif isinstance(source, str):
                text = source
            else:
                text = ''
            stripped = text.lstrip()
            if stripped.startswith('**[assistant]') and 'Executing step' in text:
                rel_path = notebook.relative_to(task_path)
                print(f"❌ Notebook assistant check: Disallowed 'Executing step' in cell {idx} of {rel_path}.")
                all_good = False

    if all_good:
        print('✅ Notebook assistant check: PASSED')
    return all_good


def check_no_args_json(task_folder):
    for root, _dirs, files in os.walk(task_folder):
        if 'args.json' in files:
            print(f'❌ No args.json check: args.json found in {root}')
            return False
    print('✅ No args.json check: PASSED')
    return True

def main(delivery_folder, task_id, selected_checks, rearrange):
    schema_path = Path(delivery_folder).parent / 'osworld_updated_schema.json'
    if not schema_path.exists():
        print('❌ Schema file not found.')
        return
    schema = load_schema(schema_path)
    schema_evaluator_funcs = _get_schema_evaluator_funcs(schema)
    task_folder = Path(delivery_folder) / task_id
    if not task_folder.exists():
        print(f'❌ Task folder {task_folder} not found.')
        return
    task_json_path = task_folder / f'{task_id}.json'
    if not task_json_path.exists():
        print(f'❌ Task JSON {task_json_path} not found.')
        return
    valid, task_data = validate_json_structure(task_json_path, schema) if 'json' in selected_checks else (True, None)
    if not valid and 'json' in selected_checks:
        return
    if any(check in selected_checks for check in ['evaluator_diff', 'passk', 'structure', 'sft_score', 'annotator_scores', 'no_args']):
        if task_data is None:
            try:
                task_data = json.loads(task_json_path.read_text(encoding='utf-8'))
            except Exception as exc:
                print(f'❌ Error loading task JSON: {exc}')
                return
    if rearrange and 'structure' not in selected_checks:
        if task_data is None:
            try:
                task_data = json.loads(task_json_path.read_text(encoding='utf-8'))
            except Exception as exc:
                print(f'❌ Error loading task JSON: {exc}')
                return
        # Normalize directory names first
        _normalize_directory_names(task_folder, rearrange)
        check_file_structure(task_folder, task_id, rearrange, task_data)
    check_entries = [
        ('structure', lambda: check_file_structure(task_folder, task_id, rearrange, task_data)),
        ('evaluator_diff', lambda: check_evaluator_diff(task_data, task_folder, schema_evaluator_funcs)),
        ('passk', lambda: validate_pass_k(task_folder, task_id, rearrange)),
        ('sft_score', lambda: check_sft_eval_score(task_folder, task_id, task_data)),
        ('annotator_scores', lambda: check_annotator_scores(task_folder)),
        ('notebook_assistant', lambda: check_notebook_assistant_cells(task_folder)),
        ('no_args', lambda: check_no_args_json(task_folder)),
    ]
    results = []
    passed_count = 0
    total_checks = len(selected_checks)
    if 'json' in selected_checks:
        results.append(valid)
        if valid:
            passed_count += 1
    for check_name, check_func in check_entries:
        if check_name in selected_checks:
            result = check_func()
            results.append(result)
            if result:
                passed_count += 1
    if all(results):
        print('🎉 All selected validations PASSED!')
    else:
        print('⚠️ Some selected validations FAILED.')
    print(f'📈 Validation Summary: {passed_count}/{total_checks} checks passed.')

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Validate OSWorld task delivery')
    parser.add_argument('delivery_folder', help='Path to the Deliverable folder')
    parser.add_argument('task_id', help='The task ID')
    parser.add_argument('--checks', default='all', help='Comma-separated list of checks to run (default: all)')
    parser.add_argument('--rearrange', action='store_true', help='Move misplaced files into the expected directory layout before validation')
    args = parser.parse_args()
    if args.checks == 'all':
        selected_checks = ['json', 'evaluator_diff', 'passk', 'structure', 'sft_score', 'annotator_scores', 'notebook_assistant', 'no_args']
    else:
        selected_checks = [check.strip() for check in args.checks.split(',')]
        available_checks = ['json', 'evaluator_diff', 'passk', 'structure', 'sft_score', 'annotator_scores', 'notebook_assistant', 'no_args']
        invalid_checks = [check for check in selected_checks if check not in available_checks]
        if invalid_checks:
            print(f'❌ Invalid checks: {invalid_checks}')
            print(f'ℹ️ Available checks: {available_checks}')
            raise SystemExit(1)
    main(args.delivery_folder, args.task_id, selected_checks, args.rearrange)
