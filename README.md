# waifu-desktop-assistant

Trợ lý ảo kiểu "waifu" sống ở góc màn hình Windows. Mình làm để có một cô bạn đồng hành trên máy: nói chuyện bằng giọng, mở/đóng app giúp, nhớ chuyện cũ, thỉnh thoảng liếc màn hình rồi hỏi han. Nhân vật mặc định là Remielle (Zenless Zone Zero), nhưng đổi sang nhân vật khác chỉ cần một thư mục persona + ảnh.

- Nói bằng **tiếng Nhật** (giọng tự train, chạy local), hiện chữ **tiếng Việt**
- Nghe bằng mic: giữ **Ctrl phải** để nói, hoặc bấm vào nhân vật để gõ
- **Làm việc trên máy:** mở/đóng app, mở web, tìm Google, chỉnh âm lượng, nhạc, khoá máy… (lệnh nguy hiểm luôn hỏi lại)
- **Nhìn màn hình:** tự liếc định kỳ rồi bình luận đúng tính cách, hoặc nhìn khi được nhờ. Ảnh chụp chỉ đưa cho model local, không rời máy
- **Trí nhớ dài hạn:** nhớ sở thích, thói quen của bạn (SQLite + embedding local)
- **Chế độ luyện tiếng Anh:** bạn nói tiếng Anh, nhân vật vẫn trả lời Việt + Nhật và chỉ chỗ nói sai
- Giọng đổi theo cảm xúc (vui, ngại, dỗi, lo, buồn, quyết tâm)
- **Alt phải:** bật/tắt chế độ luôn nằm trên mọi cửa sổ

Chi phí: chỉ phần "bộ não" gọi API (mặc định DeepSeek, vài USD/tháng). Giọng, nghe, trí nhớ, nhìn màn hình đều chạy trên máy. Muốn hoàn toàn offline thì đổi `llm.active: ollama`.

## Cấu trúc

| Phần | File | Công nghệ |
|---|---|---|
| Giao diện | `waifu/ui.py` | PySide6, cửa sổ trong suốt không viền |
| Bộ não | `waifu/llm.py`, `waifu/chat.py`, `waifu/persona.py` | API kiểu OpenAI (DeepSeek / OpenAI / Ollama), trả lời dạng JSON từng dòng |
| Giọng nói | `waifu/tts.py`, `waifu/speaker.py` | [Style-Bert-VITS2](https://github.com/litagin02/Style-Bert-VITS2) |
| Nghe | `waifu/stt.py`, `waifu/audio.py` | faster-whisper `large-v3-turbo` |
| Trí nhớ | `waifu/memory.py` | SQLite + `bge-m3` qua Ollama |
| Hành động | `waifu/actions.py` | Win32, PowerShell |
| Nhìn màn hình | `waifu/vision.py` | `gemma4:e4b` qua Ollama |

## Cài đặt

Cần Windows 10/11, Python 3.12, GPU NVIDIA (~6 GB VRAM trở lên), [Ollama](https://ollama.com).

```powershell
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
ollama pull bge-m3
ollama pull gemma4:e4b
copy .env.example .env      # rồi điền DEEPSEEK_API_KEY
```

**Ảnh nhân vật** không có trong repo (bản quyền). Tự bỏ ảnh PNG nền trong suốt vào `characters/remielle/images/`, tên theo cảm xúc: `normal.png`, `happy.png`, `shy.png`, `worried.png`, `pout.png`, `determined.png`, `sad.png` (thêm `happy_2.png`… để đổi ngẫu nhiên).

**Giọng nói** cũng không có sẵn: cài Style-Bert-VITS2 vào `vendor/Style-Bert-VITS2`, train một model tên `remielle` từ dữ liệu giọng của bạn (`scripts/prepare_voice_dataset.py` chuyển mp3 + kịch bản thành bộ dữ liệu train), rồi chạy `scripts/make_voice_styles.py` để tạo các kiểu giọng theo cảm xúc. App tự bật server giọng (`scripts/start_tts.bat`) khi mở.

## Chạy

```powershell
pythonw remielle.pyw          # dùng Python cài trên máy, KHÔNG dùng .venv\Scripts\pythonw
```

Python của venv không mở được app Microsoft Store, nên `remielle.pyw` chạy bằng Python gốc và tự nạp thư viện từ `.venv`. Muốn bật cùng máy thì tạo một tác vụ "At log on" trong Task Scheduler chạy lệnh trên.

Bản dòng lệnh để thử nhanh: `.venv\Scripts\python -m waifu.cli --mic`.

## Cách dùng

- **Giữ Ctrl phải** để nói, thả ra để gửi
- **Bấm trái** vào nhân vật: hiện/ẩn ô chat. **Kéo** để di chuyển
- **Chuột phải:** chế độ tiếng Anh, bật/tắt nhìn màn hình, nhìn ngay, thoát
- **Alt phải:** luôn ở trên / lùi xuống dưới

Mọi tuỳ chỉnh nằm trong `config.yaml` (phím, chu kỳ liếc màn hình, danh sách cửa sổ riêng tư không liếc, độ đậm cảm xúc của giọng…).

## Đổi nhân vật

Tạo `characters/<tên>/persona.md` (tính cách, cách xưng hô) và `characters/<tên>/images/`, rồi sửa `character: <tên>` trong `config.yaml`.

## Test

```powershell
.venv\Scripts\python -m pytest tests -q
```
