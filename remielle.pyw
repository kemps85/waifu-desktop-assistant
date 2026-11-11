"""Mở Remielle. Chạy bằng pythonw GỐC (không phải .venv\\Scripts): Python của venv không mở được app Store
(shell:AppsFolder báo Access is denied), nên nạp thư viện của venv bằng site.addsitedir."""
import os
import site
import sys

root = os.path.dirname(os.path.abspath(__file__))
site.addsitedir(os.path.join(root, ".venv", "Lib", "site-packages"))
sys.path.insert(0, root)

from waifu.ui import main  # noqa: E402

main()
