import os
import json
import shutil
import tempfile
import re
from urllib.parse import unquote
from git import Repo

# Sau này chỉnh vô đây để chỉnh template chung
COURSE_TEMPLATE = {
  "course_code": "",
  "title": "",
  "credits": 0,
  "prerequisites": [],
  "instructor": "",
  "description": "",
  "learning_outcomes": [],
  "term": "",
  "classes": [],
  "grading_policy": "",
  "textbooks": [],
  "reference_materials": [],
  "exam_dates": {},
  "contact": "",
  "files": {
    "syllabus": None,
    "chapters": [],
    "books": [],
    "assignments": [],
    "exams": []
  }
}

def parse_course_table_from_readme(readme_content):
    """
    Parses the Markdown table in the README to extract course details.
    
    Returns:
        A dictionary mapping the primary course code to its details.
        e.g., {"CS-2220": {"title": "Numerical Methods...", "credits": 3, "prerequisites": "MTH 1112 with C"}}
    """
    print("-> Parsing course table from README.md...")
    courses = {}
    # Regex to capture a valid table row with course data.
    # It captures Code, Title, Credits, and Prerequisite columns.
    table_row_regex = re.compile(r"\|\s*\d+\s*\|\s*\[?([^\]]+?)\]?\s*\|([^|]+)\|([^|]+)\|([^|]+)\|")
    
    for line in readme_content.splitlines():
        match = table_row_regex.search(line)
        if match:
            # Clean up the captured data
            code_raw = match.group(1).strip()
            title = match.group(2).strip()
            credits_str = match.group(3).strip()
            prereqs = match.group(4).strip()

            # The primary code is usually the first part if there are slashes
            primary_code = code_raw.split('/')[0]

            courses[primary_code] = {
                "full_code": code_raw, # Store the original code string for link mapping
                "title": title,
                "credits": int(credits_str) if credits_str.isdigit() else 0,
                "prerequisites": [p.strip() for p in prereqs.split('and')] if prereqs else []
            }
    print(f"   - Found {len(courses)} courses in the README table.")
    return courses

def parse_link_references_from_readme(readme_content):
    """
    Parses Markdown link references to map course codes to folder names.
    e.g. `[CS-2220]: ./CS2220/` -> {"CS-2220": "CS2220"}
    """
    print("-> Parsing link references from README.md to find folder paths...")
    link_map = {}
    # Regex to capture [Link Label]: ./path/
    link_ref_regex = re.compile(r"\[([^\]]+)\]:\s*\./([^/]+?)/?$")

    for line in readme_content.splitlines():
        match = link_ref_regex.search(line)
        if match:
            code_ref = match.group(1).strip()
            folder_path = match.group(2).strip()
            # Decode URL-encoded characters like '%20' for folder names
            folder_name = unquote(folder_path)
            link_map[code_ref] = folder_name
    print(f"   - Found {len(link_map)} code-to-folder mappings.")
    return link_map

def extract_course_metadata(repo_url_or_path, output_file='course.json'):
    temp_dir = None # Track thư mục temp nếu dùng clone về temp
    
    # Nếu đầu vào là một URL, clone repo vào một thư mục temp.
    if repo_url_or_path.startswith(('http', 'git@')):
        temp_dir = tempfile.mkdtemp() # Tạo một thư mục temp
        print(f"Đang clone repo vào thư mục temp: {temp_dir}")
        try:
            Repo.clone_from(repo_url_or_path, temp_dir)
            repo_path = temp_dir
        except Exception as e:
            print(f"Lỗi khi clone repo: {e}")
            # Dọn sạch temp nếu không clone được
            shutil.rmtree(temp_dir, ignore_errors=True)
            return
    else:
        repo_path = repo_url_or_path

    # read README file
    readme_path = os.path.join(repo_path, 'README.md')
    if not os.path.exists(readme_path):
        print(f"Lỗi: Không tìm thấy tệp README.md trong repo tại '{repo_path}'")
        if temp_dir:
            shutil.rmtree(temp_dir, ignore_errors=True)
        return
        
    with open(readme_path, 'r', encoding='utf-8') as f:
        readme_content = f.read()

    # parse README for course data and folder mappings
    course_details_map = parse_course_table_from_readme(readme_content)
    folder_map = parse_link_references_from_readme(readme_content)

    if os.path.exists(output_file):
        print(f"Tìm thấy tệp '{output_file}' đã có, sẽ cập nhật.")
        with open(output_file, 'r', encoding='utf-8') as f:
            existing_courses_list = json.load(f)
            courses_by_code = {course.get('course_code'): course for course in existing_courses_list}
    else:
        print(f"Không tìm thấy tệp '{output_file}', sẽ tạo mới.")
        courses_by_code = {}

        print("\nXử lí các course dựa trên thông tin từ README.md:")
        # iterate through the courses found in the README, not directories
        for course_code, details in course_details_map.items():
            # find the corresponding folder name from the link map
            course_folder_name = folder_map.get(details['full_code'])
            
            if not course_folder_name:
                print(f"  -> Cảnh báo: Không tìm thấy link đến folder cho course '{course_code}'. Bỏ qua.")
                continue

            course_path = os.path.join(repo_path, course_folder_name)
            if not os.path.isdir(course_path):
                print(f"  -> Cảnh báo: Folder '{course_folder_name}' cho course '{course_code}' không tồn tại. Bỏ qua.")
                continue

            print(f"  -> Xử lí course: {course_code} (Folder: {course_folder_name})")

            # Nếu course này chưa có trong dữ liệu, tạo một mục mới từ template.
            if course_code not in courses_by_code:
                print(f"     - Course mới, tạo template và điền thông tin từ README.")
                current_course_data = json.loads(json.dumps(COURSE_TEMPLATE))
                courses_by_code[course_code] = current_course_data
            else:
                print(f"     - Course đã tồn tại, cập nhật danh sách.")

            current_course_data = courses_by_code[course_code]

            # pre-populate metadata from README
            current_course_data['course_code'] = course_code
            current_course_data['title'] = details['title']
            current_course_data['credits'] = details['credits']
            current_course_data['prerequisites'] = details['prerequisites']
            
            # Reset lại metadata để quét lại từ đầu
            files_metadata = current_course_data.get('files', {})
            for key in ['chapters', 'books', 'assignments', 'exams']:
                files_metadata[key] = []

            # Quét tất cả các tệp và thư mục con bên trong thư mục của course.
            for root, dirs, files in os.walk(course_path):
                for file in files:
                    relative_path = os.path.relpath(os.path.join(root, file), course_path).replace('\\', '/')
                    lower_file = file.lower()

                    # Phân loại tệp dựa trên tên
                    if "syllabus" in lower_file and lower_file.endswith(('.pdf', '.md', '.doc', 'docx')):
                        files_metadata["syllabus"] = relative_path
                    elif "chapter" in lower_file and lower_file.endswith(('.pptx', '.pdf')):
                        files_metadata["chapters"].append(relative_path)
                    elif lower_file.endswith('.pdf') and "book" in lower_file:
                        files_metadata["books"].append(relative_path)
                    elif "assignment" in lower_file or "prj" in lower_file:
                        files_metadata["assignments"].append(relative_path)
                    elif "exam" in lower_file or "midterm" in lower_file or "final" in lower_file:
                        files_metadata["exams"].append(relative_path)
            # Sắp xếp danh sách files theo thứ tự như template
            for key in ['chapters', 'books', 'assignments', 'exams']:
                files_metadata[key] = sorted(list(set(files_metadata[key]))) # sort and remove duplicates
            current_course_data['files'] = files_metadata

    final_course_list = list(courses_by_code.values())

    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(final_course_list, f, indent=2, ensure_ascii=False)
        print(f"\nOK, Metadata của các course đã được ghi vào: {output_file}")
    except Exception as e:
        print(f"Lỗi khi ghi tệp JSON: {e}")

    # Xoá thư mục temp đã được tạo để clone repo.
    if temp_dir:
        print(f"Đang dọn dẹp thư mục temp: {temp_dir}")
        shutil.rmtree(temp_dir, ignore_errors=True)

if __name__ == "__main__":
    repo_to_scan = input("Nhập link to repo or đường dẫn trên máy đã clone: ")
    extract_course_metadata(repo_to_scan)