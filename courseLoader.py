import os
import json
import shutil
import tempfile
import re
from urllib.parse import unquote, quote
from git import Repo
from typing import Dict, List, Optional

# ============================
# New COURSE TEMPLATE (flat)
# ============================
COURSE_TEMPLATE = {
    "course_code": "",
    "title": "",
    "credits": 0,
    "prerequisites": [],
    # Multiple instructors possible
    "instructors": [],  # <— changed from single string to list
    "description": "",

    # The backend/operator will set these manually as needed
    "current_term": False,   # default False, we won't change it in code
    "classes": [],           # e.g., ["A", "B", "C"] — left untouched
    "grading_policy": "",   # arbitrary string; not determined in this script

    # Content lists
    # NOTE: items in modules / reference_materials / syllabi include raw GitHub link + (empty) processed link
    "modules": [],              # list[ { filename, raw_link, link } ]
    "textbooks": [],            # left empty here
    "reference_materials": [],  # list[ { filename, raw_link, link } ]
    "exam_dates": {},           # left empty
    "syllabi": [],              # list[ { filename, raw_link, link } ]

    # Assignments & Exams from Assignments folder. (No link pairing requested.)
    "assignments": [],          # list[str] (relative paths inside the course folder)
    "exams": []                 # list[str]
}

# ----------------------------
# README parsing helpers
# ----------------------------

def parse_course_table_from_readme(readme_content: str) -> Dict[str, dict]:
    """
    Parses the Markdown table in the README to extract course details.

    Returns:
        A dictionary mapping the primary course code to its details.
        e.g., {"CS-2220": {"title": "Numerical Methods...", "credits": 3, "prerequisites": ["MTH 1112 with C"]}}
    """
    print("-> Parsing course table from README.md...")
    courses = {}
    table_row_regex = re.compile(r"\|\s*\d+\s*\|\s*\[?([^\]]+?)\]?\s*\|([^|]+)\|([^|]+)\|([^|]+)\|")

    for line in readme_content.splitlines():
        match = table_row_regex.search(line)
        if match:
            code_raw = match.group(1).strip()
            title = match.group(2).strip()
            credits_str = match.group(3).strip()
            prereqs = match.group(4).strip()

            primary_code = code_raw.split('/')[0]

            courses[primary_code] = {
                "full_code": code_raw,
                "title": title,
                "credits": int(credits_str) if credits_str.isdigit() else 0,
                "prerequisites": [p.strip() for p in prereqs.split('and')] if prereqs else []
            }
    print(f"   - Found {len(courses)} courses in the README table.")
    return courses


def parse_link_references_from_readme(readme_content: str) -> Dict[str, str]:
    """
    Parses Markdown link references to map course codes to folder names.
    e.g. `[CS-2220]: ./CS2220/` -> {"CS-2220": "CS2220"}
    """
    print("-> Parsing link references from README.md to find folder paths...")
    link_map = {}
    link_ref_regex = re.compile(r"\[([^\]]+)\]:\s*\./([^/]+?)/?$")

    for line in readme_content.splitlines():
        match = link_ref_regex.search(line)
        if match:
            code_ref = match.group(1).strip()
            folder_path = match.group(2).strip()
            folder_name = unquote(folder_path)
            link_map[code_ref] = folder_name
    print(f"   - Found {len(link_map)} code-to-folder mappings.")
    return link_map

# ----------------------------
# GitHub RAW URL helpers
# ----------------------------

def _extract_owner_repo(remote_url: str) -> Optional[str]:
    """Return 'owner/repo' from common HTTPS or SSH GitHub remote URLs."""
    if not remote_url:
        return None
    remote_url = remote_url.rstrip('.git')
    if remote_url.startswith('git@github.com:'):
        return remote_url.split(':', 1)[1]
    if remote_url.startswith('https://github.com/'):
        return remote_url.split('https://github.com/', 1)[1]
    return None


def _detect_default_branch(repo: Repo) -> str:
    """Attempt to detect default branch; fall back to 'main'."""
    try:
        # Try origin/HEAD -> refs/remotes/origin/main
        ref = repo.git.symbolic_ref('refs/remotes/origin/HEAD')
        # format: 'refs/remotes/origin/main'
        return ref.split('/')[-1]
    except Exception:
        try:
            return repo.active_branch.name
        except Exception:
            return 'main'


def _build_raw_url(owner_repo: str, branch: str, path_in_repo: str) -> str:
    # Ensure each segment is URL-encoded but keep slashes
    quoted = '/'.join(quote(seg) for seg in path_in_repo.split('/'))
    return f"https://raw.githubusercontent.com/{owner_repo}/{branch}/{quoted}"


# ----------------------------
# Core extraction
# ----------------------------

def extract_course_metadata(repo_url_or_path: str, output_file: str = 'course.json') -> None:
    # PREREQUISITE: check if git-lfs is installed (if cloning repos with large files)
    if repo_url_or_path.startswith(('http', 'git@')) and not shutil.which('git-lfs'):
        print("Lỗi: 'git-lfs' không được cài đặt hoặc không có trong PATH của hệ thống.")
        print("Vui lòng cài đặt Git LFS để có thể clone repo chứa các file lớn.")
        print("Hướng dẫn: https://git-lfs.github.com/")
        return

    temp_dir = None

    # Clone if input is a URL
    if repo_url_or_path.startswith(('http', 'git@')):
        temp_dir = tempfile.mkdtemp()
        print(f"Đang clone repo vào thư mục temp: {temp_dir}")
        try:
            Repo.clone_from(repo_url_or_path, temp_dir)
            repo_path = temp_dir
        except Exception as e:
            print(f"Lỗi khi clone repo: {e}")
            shutil.rmtree(temp_dir, ignore_errors=True)
            return
    else:
        repo_path = repo_url_or_path

    # Try to read git metadata to build raw links
    owner_repo = None
    branch = 'main'
    try:
        repo_obj = Repo(repo_path)
        remote_url = next(repo_obj.remote().urls, '') if repo_obj.remotes else ''
        owner_repo = _extract_owner_repo(remote_url)
        branch = _detect_default_branch(repo_obj) or 'main'
    except Exception:
        pass

    # Read README
    readme_path = os.path.join(repo_path, 'README.md')
    if not os.path.exists(readme_path):
        print(f"Lỗi: Không tìm thấy tệp README.md trong repo tại '{repo_path}'")
        if temp_dir:
            shutil.rmtree(temp_dir, ignore_errors=True)
        return

    with open(readme_path, 'r', encoding='utf-8') as f:
        readme_content = f.read()

    # Parse
    course_details_map = parse_course_table_from_readme(readme_content)
    folder_map = parse_link_references_from_readme(readme_content)

    # Load existing output if present (merge-by-course_code); else start fresh
    if os.path.exists(output_file):
        print(f"Tìm thấy tệp '{output_file}' đã có, sẽ cập nhật.")
        with open(output_file, 'r', encoding='utf-8') as f:
            existing_courses_list = json.load(f)
            courses_by_code = {course.get('course_code'): course for course in existing_courses_list}
    else:
        print(f"Không tìm thấy tệp '{output_file}', sẽ tạo mới.")
        courses_by_code = {}

    print("\nXử lí các course dựa trên thông tin từ README.md:")
    special_codes = {"MTH-1125", "HIS-1123", "HIS-1122", "MTH-1126"}

    for course_code, details in course_details_map.items():
        # Xử lý đặc biệt cho 4 course này
        if course_code in special_codes:
            if course_code in os.listdir(repo_path):
                course_folder_name = course_code
            else:
                print(f"  -> Cảnh báo: Không tìm thấy thư mục '{course_code}' cho course '{course_code}'. Bỏ qua.")
                continue
        else:
            course_folder_name = folder_map.get(details['full_code'])
            if not course_folder_name:
                print(f"  -> Cảnh báo: Không tìm thấy link đến folder cho course '{course_code}'. Bỏ qua.")
                continue

        course_path = os.path.join(repo_path, course_folder_name)
        if not os.path.isdir(course_path):
            print(f"  -> Cảnh báo: Folder '{course_folder_name}' cho course '{course_code}' không tồn tại. Bỏ qua.")
            continue

        print(f"  -> Xử lí course: {course_code} (Folder: {course_folder_name})")

        # Create or reuse existing record
        record = courses_by_code.get(course_code)
        if not record:
            record = json.loads(json.dumps(COURSE_TEMPLATE))
            courses_by_code[course_code] = record

        # Fill metadata from README
        record['course_code'] = course_code
        record['title'] = details['title']
        record['credits'] = details['credits']
        record['prerequisites'] = details['prerequisites']

        # DO NOT touch: current_term, classes, grading_policy, instructors, description

        # Reset content lists to rebuild from disk
        record['modules'] = []
        record['reference_materials'] = []
        record['syllabi'] = []
        record['assignments'] = []
        record['exams'] = []
        # textbooks, exam_dates left as-is (explicitly empty by default)

        # Helper to generate raw link if possible
        def make_raw(path_inside_course: str) -> str:
            if owner_repo:
                path_in_repo = f"{course_folder_name}/{path_inside_course}".replace('\\', '/')
                return _build_raw_url(owner_repo, branch, path_in_repo)
            # Fallback to relative path if we can't build a raw URL
            return path_inside_course.replace('\\', '/')

        # Walk course subfolders
        for root, dirs, files in os.walk(course_path):
            rel_dir_from_course = os.path.relpath(root, course_path).replace('\\', '/')
            top_level = rel_dir_from_course.split('/')[0] if rel_dir_from_course != '.' else '.'

            for fname in files:
                rel_path = os.path.relpath(os.path.join(root, fname), course_path).replace('\\', '/')
                base = os.path.basename(fname)

                # Route by the FIRST-LEVEL directory: Assignments / Modules / References / Syllabi
                if top_level.lower() == 'modules':
                    record['modules'].append({
                        'filename': rel_path,
                        'raw_link': make_raw(rel_path),
                        'link': ''
                    })
                elif top_level.lower() == 'references':
                    record['reference_materials'].append({
                        'filename': rel_path,
                        'raw_link': make_raw(rel_path),
                        'link': ''
                    })
                elif top_level.lower() == 'syllabi':
                    record['syllabi'].append({
                        'filename': rel_path,
                        'raw_link': make_raw(rel_path),
                        'link': ''
                    })
                elif top_level.lower() == 'assignments':
                    # Classify by filename prefix (case-insensitive)
                    if base.upper().startswith('EXAM'):
                        record['exams'].append(rel_path)
                    else:
                        record['assignments'].append(rel_path)
                else:
                    # Ignore any other folders/files at this time
                    pass

        # De-duplicate and sort
        def _dedup_sort_list(lst: List[str]) -> List[str]:
            return sorted(list(dict.fromkeys(lst)))

        def _dedup_sort_obj_list(lst: List[dict]) -> List[dict]:
            seen = set()
            out = []
            for item in lst:
                key = (item.get('filename'), item.get('raw_link'))
                if key not in seen:
                    seen.add(key)
                    out.append(item)
            # Sort by filename for stability
            out.sort(key=lambda x: x.get('filename', ''))
            return out

        record['modules'] = _dedup_sort_obj_list(record['modules'])
        record['reference_materials'] = _dedup_sort_obj_list(record['reference_materials'])
        record['syllabi'] = _dedup_sort_obj_list(record['syllabi'])
        record['assignments'] = _dedup_sort_list(record['assignments'])
        record['exams'] = _dedup_sort_list(record['exams'])

    # Write output
    final_course_list = list(courses_by_code.values())
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(final_course_list, f, indent=2, ensure_ascii=False)
        print(f"\nOK, Metadata của các course đã được ghi vào: {output_file}")
    except Exception as e:
        print(f"Lỗi khi ghi tệp JSON: {e}")

    # Cleanup temp clone
    if temp_dir:
        print(f"Đang dọn dẹp thư mục temp: {temp_dir}")
        shutil.rmtree(temp_dir, ignore_errors=True)


def run_course_loader(repo_url_or_path: str) -> list:
    """Convenience API for backend to run loader and return parsed JSON list."""
    output_file = "_temp_course.json"
    extract_course_metadata(repo_url_or_path, output_file=output_file)
    with open(output_file, "r", encoding="utf-8") as f:
        return json.load(f)


if __name__ == "__main__":
    repo_to_scan = input("Nhập link to repo or đường dẫn trên máy đã clone: ")
    extract_course_metadata(repo_to_scan)
