import os
import json
import shutil
import tempfile
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

    if os.path.exists(output_file):
        print(f"Tìm thấy tệp '{output_file}' đã có, sẽ cập nhật.")
        with open(output_file, 'r', encoding='utf-8') as f:
            existing_courses_list = json.load(f)
            courses_by_code = {course.get('course_code'): course for course in existing_courses_list}
    else:
        print(f"Không tìm thấy tệp '{output_file}', sẽ tạo mới.")
        courses_by_code = {}

    print("Xử lí các thư mục course trong repo:")
    for course_folder_name in os.listdir(repo_path):
        course_path = os.path.join(repo_path, course_folder_name)
        if os.path.isdir(course_path) and not course_folder_name.startswith('.'):
            course_code = course_folder_name
            print(f"  -> Tìm thấy course: {course_code}")

            # Nếu course này chưa có trong dữ liệu, tạo một mục mới từ template.
            if course_code not in courses_by_code:
                print(f"     - Course mới, tạo template.")
                new_course_data = json.loads(json.dumps(COURSE_TEMPLATE))
                new_course_data['course_code'] = course_code
                courses_by_code[course_code] = new_course_data
            else:
                print(f"     - Course đã tồn tại, cập nhật danh sách.")

            current_course_data = courses_by_code[course_code]
            
            # Reset lại metadata để quét lại từ đầu
            files_metadata = {
                "syllabus": None, "chapters": [],
                "books": [], "assignments": [], "exams": []
            }

            # Quét tất cả các tệp và thư mục con bên trong thư mục của course.
            for root, dirs, files in os.walk(course_path):
                for file in files:
                    relative_path = os.path.relpath(os.path.join(root, file), course_path)
                    lower_file = file.lower()

                    # Phân loại tệp dựa trên tên
                    if "syllabus" in lower_file and lower_file.endswith(('.pdf', '.md', '.doc', 'docx')):
                        files_metadata["syllabus"] = relative_path
                    elif "chapter" in lower_file and lower_file.endswith(('.pptx', '.pdf')):
                        files_metadata["chapters"].append(relative_path)
                    elif lower_file.endswith('.pdf') and "book" in lower_file:
                        files_metadata["books"].append(relative_path)
                    elif "assignment" in lower_file:
                        files_metadata["assignments"].append(relative_path)
                    elif "exam" in lower_file or "midterm" in lower_file or "final" in lower_file:
                        files_metadata["exams"].append(relative_path)
            
            # Sắp xếp danh sách files theo thứ tự như template
            for key in ['chapters', 'books', 'assignments', 'exams']:
                files_metadata[key].sort()
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
        repo = None
        shutil.rmtree(temp_dir, ignore_errors=True)

if __name__ == "__main__":
    repo_to_scan = input("Nhập link to repo or đường dẫn trên máy đã clone: ")
    extract_course_metadata(repo_to_scan)