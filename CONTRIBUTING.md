# Hướng dẫn đóng góp (Contributing Guide)

Cảm ơn bạn đã quan tâm đóng góp cho dự án **AegisTrans**! Dự án được phát triển nhằm cung cấp giải pháp dịch thuật tài liệu học thuật và sách Y khoa chuyên sâu từ tiếng Anh sang tiếng Việt, bảo toàn cấu trúc dàn trang PDF, hỗ trợ giữ nguyên thuật ngữ quốc tế song ngữ `Thuật ngữ tiếng Việt (English term)` và cơ chế lưu vết dịch ngắt quãng (checkpoint resumption) cho các bộ sách Y học dài hàng trăm trang.

---

## 1. Nguồn gốc & Tôn trọng bản quyền (Lineage & Ethics)

AegisTrans được phát triển dựa trên việc kế thừa và học hỏi các dự án mã nguồn mở xuất sắc:
- **[PDFMathTranslate-next](https://github.com/PDFMathTranslate/PDFMathTranslate-next)**: Ý tưởng khởi nguồn khi tham khảo *GoodAIList* của tác giả Chip Huyen.
- **[VI-Translate](https://github.com/breslee1707/VI-Translate)**: Phát triển và đóng góp bởi tác giả `breslee1707`, phục vụ dịch thuật tài liệu đa ngữ có giao diện tiếng Việt.
- **Mục đích cộng đồng & Phi thương mại**: Dự án được tác giả (`tunah72`) xây dựng hoàn toàn vì mục đích học tập, nghiên cứu và hỗ trợ cộng đồng y khoa Việt Nam tiếp cận tri thức y học thế giới. Toàn bộ mã nguồn phát hành miễn phí theo giấy phép **GNU AGPLv3**.
- **Chính sách liên hệ & Takedown**: Chúng tôi luôn tôn trọng bản quyền của các tác giả gốc và nhà xuất bản. Nếu quý tác giả hoặc nhà xuất bản có bất kỳ thắc mắc, yêu cầu ghi nhận hoặc gỡ bỏ tài liệu mẫu nào, xin vui lòng tạo Issue hoặc liên hệ trực tiếp với maintainer qua GitHub ([@tunah72](https://github.com/tunah72)) để được xử lý ngay lập tức.

---

## 2. Thiết lập môi trường phát triển (Development Setup)

### Yêu cầu hệ thống
- **Python**: 3.10 – 3.12 (khuyến nghị Python 3.12).
- **Hệ điều hành**: macOS (Apple Silicon / Intel) để đóng gói ứng dụng Desktop; hoặc Linux / Windows đối với việc phát triển CLI và thuật toán dịch.

### Cài đặt
```bash
# Clone repository
git clone https://github.com/tunah72/aegistrans.git
cd aegistrans

# Khởi tạo virtual environment
python3 -m venv .venv

# Kích hoạt virtual environment
source .venv/bin/activate

# Cài đặt dependencies (bao gồm core, desktop app và công cụ đóng gói)
pip install -r requirements-app.txt
```

---

## 3. Kiểm thử tự động (Running Tests)

Trước khi gửi pull request hoặc commit, hãy đảm bảo toàn bộ bộ test suite chạy thành công:

```bash
python -m unittest discover tests
```

Tất cả các module cốt lõi đều có unit test tương ứng trong thư mục `tests/`:
- `test_openai_translator.py`: Kiểm thử bộ dịch LLM (OpenAI, Gemini, 9router).
- `test_checkpoint.py`: Kiểm thử cơ chế lưu vết dịch ngắt quãng SQLite.
- `test_glossary.py`: Kiểm thử nạp và đối soát thuật ngữ chuyên ngành Y khoa.
- `test_validation.py`: Kiểm thử bảo vệ công thức toán học `<b0></b0>`.
- `test_app_gui.py`: Kiểm thử các hàm logic của giao diện desktop.

---

## 4. Đóng gói ứng dụng Desktop trên macOS (`build.sh`)

Do môi trường phát triển chính của tác giả là macOS, ứng dụng desktop AegisTrans hiện được đóng gói, tối ưu và kiểm thử chính thức trên **macOS**:

```bash
# Đóng gói tạo dist/AegisTrans.app và nén thành dist/AegisTrans-macos.zip
./build.sh
```

*Tùy chọn hữu ích:*
```bash
# Bỏ qua tải lại model ONNX nếu đã có trong app/assets/
./build.sh --skip-assets

# Dọn dẹp cache và thư mục dist/
./build.sh --clean
```

> **Lưu ý về tính trung thực và các nền tảng khác:**
> Để đảm bảo tính trung thực và chất lượng sản phẩm công bố, dự án không tạo bản phát hành desktop tự động cho Windows nếu chưa được kiểm thử thực tế trên máy vật lý Windows. Người dùng trên Windows và Linux hoàn toàn có thể sử dụng đầy đủ sức mạnh của AegisTrans thông qua giao diện dòng lệnh Python CLI (`scripts/translate_pdf.py`, `scripts/translate_book.py`) hoặc chạy trực tiếp `python -m app.gui`.

---

## 5. Đóng góp Profile chuyên khoa Y học mới (Medical Profiles)

AegisTrans sử dụng kiến trúc profile mở tại thư mục `medical-translation/profiles/`:

```
medical-translation/profiles/
├── dental/                      # Răng Hàm Mặt, Khớp cắn, Rối loạn TMD
│   ├── system_prompt.txt
│   └── glossary_base.jsonl
└── general_medicine/            # Nội khoa, Ngoại khoa, Sinh lý, Dược lý
    ├── system_prompt.txt
    └── glossary_base.jsonl
```

### Cách tạo thêm chuyên khoa mới (ví dụ: Tim mạch - `cardiology`):
1. Tạo thư mục `medical-translation/profiles/cardiology/`.
2. Định nghĩa `system_prompt.txt`: Mô tả phong cách học thuật, quy tắc chuẩn hóa thuật ngữ và phong cách song ngữ `Thuật ngữ tiếng Việt (English term)`.
3. Bổ sung `glossary_base.jsonl`: Danh mục thuật ngữ chuẩn dạng JSON Lines:
   ```json
   {"en": "myocardial infarction", "vi": "nhồi máu cơ tim", "notes": "MI"}
   {"en": "heart failure", "vi": "suy tim", "notes": "HF"}
   ```
4. Chạy kiểm thử dịch với profile mới:
   ```bash
   python scripts/translate_book.py input.pdf --output-dir output/book --profile cardiology
   ```

---

## 6. Quy trình phát hành phiên bản (Release Process)

1. Cập nhật số phiên bản trong `app/update.py`:
   ```python
   APP_VERSION = "0.2.1"
   ```
2. Cập nhật `README.md` hoặc changelog.
3. Tạo git tag trùng khớp với `APP_VERSION`:
   ```bash
   git tag v0.2.1
   ```
4. Workflow `.github/workflows/release.yml` sẽ tự động đóng gói bản macOS native (`AegisTrans-macos.zip`) và xuất bản GitHub Release.
